import io
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from pie import check, i18n, logger, storage
from pie.bot import Strawberry
import unidecode

from .database import WormholeChannel

_ = i18n.Translator("modules/wormhole").translate
bot_log = logger.Bot.logger()
guild_log = logger.Guild.logger()


class Wormhole(commands.Cog):
    """
    This Cog handles message relaying (a "wormhole") across multiple channels in different guilds.
    """

    wormhole_channels: list[int] = []

    wormhole: app_commands.Group = app_commands.Group(
        name="wormhole",
        description="Set of configuration for wormhole.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True,
    )

    wormhole_channel: app_commands.Group = app_commands.Group(
        name="channel",
        description="Configuration commands for wormhole channels.",
        parent=wormhole,
    )

    wormhole_slowmode: app_commands.Group = app_commands.Group(
        name="slowmode",
        description="Slowmode commands for wormhole.",
        parent=wormhole,
    )

    def __init__(self, bot: Strawberry):
        self.bot: Strawberry = bot
        self.wormhole_channels = WormholeChannel.get_channel_ids()
        self.restore_slowmode.start()

    # TASK INITIALIZATION
    @tasks.loop(seconds=2.0, count=1)
    async def restore_slowmode(self):
        """Restore slowmode in wormhole channels after bot starts."""
        delay = storage.get(self, 0, key="wormhole_slowmode")
        await self._set_slowmode(delay)

    @restore_slowmode.before_loop
    async def before_restore_slowmode(self):
        """Wait for bot readiness before restoring slowmode."""
        await self.bot.wait_until_ready()

    # HELPERS
    async def _message_formatter(self, message: discord.Message) -> tuple[str, Optional[str]]:
        """
        Format the message and determine a thumbnail.
        Returns (formatted_text, thumbnail_url).
        """
        guild = message.guild
        guild_name = guild.name if guild else "Unknown Server"

        # Normalize guild name for emoji matching
        norm = unidecode.unidecode(guild_name).lower().replace(" ", "_")

        # Find matching custom emoji
        emoji = None
        for e in await self.bot.fetch_application_emojis():
            if e.name == norm:
                emoji = e
                break

        # Fallback to guild icon if no emoji
        thumbnail = guild.icon.url if (not emoji and guild and guild.icon) else None

        # Sanitize mentions (user, role, channel, everyone/here)
        sanitized = re.sub(
            r"(<@!?[0-9]+>|<@&[0-9]+>|<#[0-9]+>|@everyone|@here)",
            "`[MENTIONS REMOVED]`",
            message.content,
        )

        display = str(emoji) if emoji else f"[{guild_name}]"
        formatted = f"**{display} {message.author.name}:** {sanitized}"
        return formatted, thumbnail

    async def _set_slowmode(
        self, delay: int, itx: Optional[discord.Interaction] = None
    ):
        """
        Apply slowmode to all wormhole channels.
        Sends interaction response if `itx` is provided.
        """
        forbidden = []
        for cid in self.wormhole_channels:
            ch = self.bot.get_channel(cid)
            if not ch:
                continue
            try:
                await ch.edit(slowmode_delay=delay)
            except discord.Forbidden:
                forbidden.append(f"{ch.name}({ch.id}) in {ch.guild.name}")

        if forbidden:
            await bot_log.warning(
                itx.user if itx else None,
                itx.channel if itx else None,
                f"Cannot set slowmode in {', '.join(forbidden)}",
            )
            if itx:
                await itx.response.send_message(
                    _(
                        itx,
                        "Lacking permissions to set slowmode in some channels.",
                    ),
                    ephemeral=True,
                )
        else:
            await bot_log.info(
                itx.user if itx else None,
                itx.channel if itx else None,
                f"Slowmode set to {delay}s.",
            )
            if itx:
                await itx.response.send_message(
                    _(itx, "Slowmode set to {delay}s.").format(delay=delay),
                    ephemeral=True,
                )

    # LISTENER
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Relay text and images to configured wormhole channels."""
        if message.author.bot or message.content.startswith(self.bot.command_prefix):
            return
        if message.channel.id not in self.wormhole_channels:
            return

        # Delete original message
        try:
            await message.delete()
        except discord.Forbidden:
            await bot_log.warning(
                message.author, message.channel, "Cannot delete message."
            )

        formatted, thumbnail = await self._message_formatter(message)

        # Prepare image attachments
        files: list[discord.File] = []
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                if att.size <= 5 * 1024 * 1024:  # 5MB cap
                    data = await att.read()
                    files.append(discord.File(io.BytesIO(data), att.filename))

        # Forward to each channel
        for cid in self.wormhole_channels:
            ch = self.bot.get_channel(cid)
            if not ch:
                continue
            try:
                if thumbnail:
                    embed = discord.Embed(description=formatted)
                    embed.set_thumbnail(url=thumbnail)
                    await ch.send(embed=embed, files=files)
                else:
                    await ch.send(formatted, files=files)
            except discord.HTTPException as e:
                await bot_log.error(
                    message.author, ch, f"Relay failed: {e}"
                )

    #  COMMANDS 
    
    # — Wormhole Channel Management —
    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole_channel.command(
        name="set",
        description="Register this channel as a wormhole endpoint.",
    )
    async def set_wormhole_channel(
        self, itx: discord.Interaction, channel: discord.TextChannel
    ):
        if WormholeChannel.check_existence(channel.id):
            await itx.response.send_message(
                _(itx, "Already a wormhole channel."), ephemeral=True
            )
            return

        delay = storage.get(self, 0, key="wormhole_slowmode")
        try:
            await channel.edit(slowmode_delay=delay)
        except discord.Forbidden:
            await bot_log.warning(
                itx.user, itx.channel, "Cannot set slowmode (missing perm)."
            )

        WormholeChannel.add(guild_id=itx.guild.id, channel_id=channel.id)
        self.wormhole_channels.append(channel.id)
        await itx.response.send_message(
            _(itx, "Channel `{channel}` added.").format(channel=channel.name),
            ephemeral=True,
        )
        await guild_log.info(
            itx.user, itx.channel, f"Added {channel.name} to wormhole."
        )

    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole_channel.command(
        name="remove",
        description="Unregister this channel from the wormhole.",
    )
    async def unset_wormhole_channel(
        self, itx: discord.Interaction, channel: discord.TextChannel
    ):
        if not WormholeChannel.check_existence(channel.id):
            await itx.response.send_message(
                _(itx, "Not a wormhole channel."), ephemeral=True
            )
            return

        try:
            await channel.edit(slowmode_delay=0)
        except discord.Forbidden:
            await bot_log.warning(
                itx.user, itx.channel, "Cannot remove slowmode (missing perm)."
            )

        WormholeChannel.remove(guild_id=itx.guild.id, channel_id=channel.id)
        self.wormhole_channels.remove(channel.id)
        await itx.response.send_message(
            _(itx, "Channel `{channel}` removed.").format(channel=channel.name),
            ephemeral=True,
        )
        await guild_log.info(
            itx.user, itx.channel, f"Removed {channel.name} from wormhole."
        )

    # — Wormhole Slowmode Management —
    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole_slowmode.command(
        name="set",
        description="Apply slowmode to all wormhole channels.",
    )
    @app_commands.describe(delay="Seconds of slowmode")
    async def set_wormhole_slowmode(self, itx: discord.Interaction, delay: int):
        if delay < 0:
            await itx.response.send_message(
                _(itx, "Delay must be ≥ 0."), ephemeral=True
            )
            return

        storage.set(self, 0, key="wormhole_slowmode", value=delay)
        await self._set_slowmode(delay, itx)

    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole_slowmode.command(
        name="remove",
        description="Disable slowmode in all wormhole channels.",
    )
    async def remove_wormhole_slowmode(self, itx: discord.Interaction):
        storage.set(self, 0, key="wormhole_slowmode", value=0)
        await self._set_slowmode(0, itx)


async def setup(bot: Strawberry) -> None:
    await bot.add_cog(Wormhole(bot))