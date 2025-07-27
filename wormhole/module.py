import re
import io
import unidecode
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from pie import check, i18n, logger, storage
from pie.bot import Strawberry

from .database import (  # Local database model for managing wormhole channels
    WormholeChannel,
)


# Setup for internationalization (i18n) and logging
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
        description="Set of configuration for wormhole channel.",
        parent=wormhole,
    )

    wormhole_slowmode: app_commands.Group = app_commands.Group(
        name="slowmode",
        description="Set of configuration for wormhole slow mode.",
        parent=wormhole,
    )

    def __init__(self, bot: Strawberry):
        self.bot: Strawberry = bot
        self.wormhole_channels = WormholeChannel.get_channel_ids()
        self.restore_slowmode.start()

    @tasks.loop(seconds=2.0, count=1)
    async def restore_slowmode(self):
        """Task to restore the slowmode in wormhole channels after module load."""
        delay = storage.get(self, 0, key="wormhole_slowmode")
        await self._set_slowmode(delay)

    @restore_slowmode.before_loop
    async def before_restore_slowmode(self):
        """Ensures that bot is ready before restoring slowmode."""
        await self.bot.wait_until_ready()

    # ─── HELPERS ──────────────────────────────────────────────────────────────

    async def _message_formatter(self, message: discord.Message) -> tuple[str, Optional[str]]:
        """
        Returns a tuple of (formatted_text, thumbnail_url).
        thumbnail_url will be the server icon if no matching emoji found.
        """
        guild = message.guild
        guild_name = guild.name if guild else "Unknown Server"

        # Normalize with Unidecode so accents, emojis, etc. don't break matching
        norm = unidecode.unidecode(guild_name).lower().replace(" ", "_")

        # Try your custom emoji first
        emoji = None
        for e in await self.bot.fetch_application_emojis():
            if e.name == norm:
                emoji = e
                break

        # If no custom emoji, fall back to guild icon URL (if any)
        thumbnail = None
        if not emoji and guild and guild.icon:
            thumbnail = guild.icon.url

        guild_display = str(emoji) if emoji else f"[{guild_name}]"
        new_content = re.sub(r"<@(\d+)>", r"`[TAGS ARE NOT ALLOWED!]`", message.content)
        formatted = f"**{guild_display} {message.author.name}:** {new_content}"

        return formatted, thumbnail

    async def _set_slowmode(
        self, delay: int, itx: Optional[discord.Interaction] = None
    ):
        """Helper function to set slowmode on Wormhole channels.

        If ITX is provided, it also handles the interaction response.
        """
        forbidden_channels = []
        for channel_id in self.wormhole_channels:
            target_channel = self.bot.get_channel(channel_id)
            if target_channel:
                try:
                    await target_channel.edit(slowmode_delay=delay)
                except discord.Forbidden:
                    ch = f"#{target_channel.name} ({target_channel.id}) {target_channel.guild.name}"
                    forbidden_channels.append(ch)

        if forbidden_channels:
            channels = ", ".join(forbidden_channels)
            await bot_log.warning(
                itx.user if itx else None,
                itx.channel if itx else None,
                f"Missing permissions to set wormhole slow mode in channels {channels}. (TIP: Check if 'manage channel' is granted.)",
            )
            if itx:
                await itx.response.send_message(
                    _(
                        itx,
                        "I do not have proper permissions to set slow mode. Some channel may need manual intervention.",
                    ),
                    ephemeral=True,
                )
        else:
            await bot_log.info(
                itx.user if itx else None,
                itx.channel if itx else None,
                f"Wormhole slow mode set to {delay} seconds.",
            )
            if itx:
                await itx.response.send_message(
                    _(itx, "Slow mode set to {delay} seconds.").format(delay=delay),
                    ephemeral=True,
                )

    # ─── LISTENER ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Main message relay logic."""
        # Ignore bots & commands
        if message.author.bot or message.content.startswith(self.bot.command_prefix):
            return

        # Only proceed if this channel is registered as a wormhole
        if message.channel.id not in self.wormhole_channels:
            return

        # Delete original if possible
        try:
            await message.delete()
        except discord.Forbidden:
            await bot_log.warning(
                message.author, message.channel, "Missing permissions to delete message."
            )

        # Format text and get optional thumbnail URL
        formatted, thumbnail = await self._message_formatter(message)

        # Gather image attachments
        files: list[discord.File] = []
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                data = await att.read()
                fp = io.BytesIO(data)
                files.append(discord.File(fp, filename=att.filename))

        # Send to each wormhole channel
        for cid in self.wormhole_channels:
            chan = self.bot.get_channel(cid)
            if not chan:
                continue

            if thumbnail:
                embed = discord.Embed(description=formatted)
                embed.set_thumbnail(url=thumbnail)
                try:
                    await chan.send(embed=embed, files=files)
                except discord.Forbidden:
                    await bot_log.warning(
                        message.author, chan, "Missing permissions to send embed."
                    )
            else:
                try:
                    await chan.send(formatted, files=files)
                except discord.Forbidden:
                    await bot_log.warning(
                        message.author, chan, "Missing permissions to send message."
                    )

    # ─── COMMANDS ────────────────────────────────────────────────────────────

    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole_channel.command(
        name="set",
        description="Register a channel as a wormhole. All messages in this channel will be deleted and mirrored.",
    )
    async def set_wormhole_channel(
        self, itx: discord.Interaction, channel: discord.TextChannel
    ):
        """Register a channel as a wormhole."""
        if WormholeChannel.check_existence(channel.id):
            await itx.response.send_message(
                _(itx, "Channel is already set as wormhole channel."), ephemeral=True
            )
            return

        delay = storage.get(self, 0, key="wormhole_slowmode")
        try:
            await channel.edit(slowmode_delay=delay)
        except discord.Forbidden:
            await bot_log.warning(
                itx.user,
                itx.channel,
                "Missing permissions to set wormhole slow mode. (TIP: Check if 'manage channel' is granted.)",
            )

        WormholeChannel.add(guild_id=itx.guild.id, channel_id=channel.id)
        self.wormhole_channels.append(channel.id)
        await itx.response.send_message(
            _(itx, "Channel `{channel_name}` was added as wormhole channel.").format(
                channel_name=channel.name
            ),
            ephemeral=True,
        )
        await guild_log.info(
            itx.user,
            itx.channel,
            f"Channel '{channel.name}' was added as wormhole channel.",
        )

    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole_channel.command(
        name="remove",
        description="Unregister a channel from the wormhole.",
    )
    async def unset_wormhole_channel(
        self, itx: discord.Interaction, channel: discord.TextChannel
    ):
        """Unregister a channel from the wormhole."""
        if not WormholeChannel.check_existence(channel.id):
            await itx.response.send_message(
                _(itx, "Channel is not set as wormhole channel."), ephemeral=True
            )
            return

        try:
            await channel.edit(slowmode_delay=0)
        except discord.Forbidden:
            await bot_log.warning(
                itx.user,
                itx.channel,
                "Missing permissions to reset slow mode. (TIP: Check if 'manage channel' is granted.)",
            )

        WormholeChannel.remove(guild_id=itx.guild.id, channel_id=channel.id)
        self.wormhole_channels.remove(channel.id)
        await itx.response.send_message(
            _(itx, "Channel `{channel_name}` was removed as wormhole channel.").format(
                channel_name=channel.name
            ),
            ephemeral=True,
        )
        await guild_log.info(
            itx.user,
            itx.channel,
            f"Channel '{channel.name}' was removed as wormhole channel.",
        )

    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole_slowmode.command(
        name="set",
        description="Apply slowmode to all wormhole channels.",
    )
    @app_commands.describe(delay="Time in seconds")
    async def set_wormhole_slowmode(self, itx: discord.Interaction, delay: int):
        """Apply slowmode to all wormhole channels."""
        if delay < 0:
            await itx.response.send_message(
                _(itx, "Delay should be 0 or more.").format(time=delay),
                ephemeral=True,
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
        """Disable slowmode in all wormhole channels."""
        storage.set(self, 0, key="wormhole_slowmode", value=0)
        await self._set_slowmode(0, itx)


async def setup(bot: Strawberry) -> None:
    await bot.add_cog(Wormhole(bot))
