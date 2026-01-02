import io
import re
import unicodedata
from typing import Optional

import discord
from discord import MessageReferenceType, app_commands
from discord.ext import commands, tasks

from pie import check, i18n, logger, storage, utils
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
        """Ensures that bot is ready before restoring slowmode"""
        await self.bot.wait_until_ready()

    # HELPER FUNCTIONS

    def _remove_accents(self, input_str):
        nfkd_form = unicodedata.normalize("NFKD", input_str)
        return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

    async def _message_formatter(
        self, message: discord.Message, stickers: list = None
    ) -> str:
        """Helper function to format wormhole message.

        :param message: Discord message to format
        :param stickers: list of custom sticker urls
        :return: Formatted message text
        """
        gtx = i18n.TranslationContext(message.guild.id, message.author.id)
        guild = message.guild
        guild_name = (
            self._remove_accents(guild.name).replace(" ", "_").lower()
            if guild
            else _(gtx, "Unknown Server")
        )
        guild_name = re.sub(r"[^a-z0-9_]", "", guild_name)

        emojis = await self.bot.fetch_application_emojis()
        emoji = None
        for e in emojis:
            if e.name == guild_name:
                emoji = e
                break
        guild_display = str(emoji) if emoji else f"[{guild.name}]"

        marks = ["### ", "## ", "-# ", "# ", ">>> ", "> "]

        marks_to_add_to_start = (
            "\n" if any(message.content.startswith(m) for m in marks) else ""
        )

        formatted_message = f"**{guild_display} {message.author.name}:** {marks_to_add_to_start + message.content}\n"

        # add stickers from servers to message
        for s in stickers or []:
            formatted_message = formatted_message.rstrip() + f"[.]({s})"

        referenced_msg = None
        ref = message.reference
        if ref is not None:
            # Try the cached version first
            if ref.resolved:
                referenced_msg = ref.resolved
            else:
                # Try fetching manually
                try:
                    guild = self.bot.get_guild(ref.guild_id)
                    if guild is not None:
                        channel = guild.get_channel(ref.channel_id)
                        if channel is not None:
                            referenced_msg = await channel.fetch_message(ref.message_id)
                except discord.errors.NotFound:
                    pass
                except discord.errors.Forbidden:
                    pass
                except discord.errors.HTTPException:
                    pass

        if ref and ref.type == MessageReferenceType.reply:
            msg_tmp = (
                "> " + referenced_msg.content.replace("\n", "\n> ")
                if referenced_msg and referenced_msg.content
                else _(gtx, "Unknown reference message")
            )
            msg = ""
            for m in msg_tmp.strip().split("\n"):
                if not m.startswith("> >"):
                    msg += m + "\n"
            formatted_message = f"> {msg.rstrip()}\n{formatted_message}"
        elif ref and ref.type == MessageReferenceType.forward:
            guild_ = referenced_msg.guild
            guild_name_ = (
                self._remove_accents(guild_.name).replace(" ", "_").lower()
                if guild_
                else _(gtx, "Unknown Server")
            )
            guild_name_ = re.sub(r"[^a-z0-9_]", "", guild_name_)
            emoji_ = None
            for e in emojis:
                if e.name == guild_name_:
                    emoji_ = e
                    break
            guild_display_ = str(emoji_) if emoji_ else f"[{guild_.name}]"
            formatted_message = f"**{guild_display} {message.author.name}:** {_(gtx, 'Forwarded')}\n>>> {guild_display_} {(
                referenced_msg.author.name
                if referenced_msg.author and referenced_msg.author.name
                else _(gtx, "Unknow author")
            )}: ``` {referenced_msg.content.replace('```', '')
            if referenced_msg and referenced_msg.content
            else _(gtx, 'Unknown forwarded message')}```"
        return formatted_message

    async def _set_slowmode(
        self, delay: int, itx: Optional[discord.Interaction] = None
    ):
        """Helper function to set slowmode on Wormhole channels.

        If ITX is provided, it also handles the interaction response.

        :param delay: Slowmode delay to set
        :param itx: Discord interaction
        """
        forbidden_channels = []
        for channel in self.wormhole_channels:
            target_channel = self.bot.get_channel(channel)
            if target_channel:
                try:
                    await target_channel.edit(slowmode_delay=delay)
                except discord.Forbidden:
                    ch = f"#{target_channel.name} ({target_channel.id}) {target_channel.guild.name}"
                    forbidden_channels.append(ch)

        if forbidden_channels:
            channels = ",".join(forbidden_channels)
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

    # LISTENERS

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Main message relay logics."""
        # Ignore bot messages
        if message.author.bot:
            return

        # Ignore commands
        if message.content.startswith(self.bot.command_prefix):
            return

        # Only proceed if this channel is registered as a wormhole
        if message.channel.id not in self.wormhole_channels:
            return

        attachments_list: list = []

        if message.attachments:
            for a in message.attachments:
                tmp: io.BytesIO = io.BytesIO()
                await a.save(tmp)
                attachments_list.append([tmp, a.filename, a.is_spoiler()])

        # discord default stickers cant be resent by url
        saved_stickers: list = []
        discord_stickers: list = []
        for s in message.stickers or []:
            sticker = await s.fetch()
            if isinstance(sticker, discord.sticker.StandardSticker):
                discord_stickers.append(sticker)
            elif isinstance(sticker, discord.sticker.GuildSticker):
                saved_stickers.append(s.url)  # save custom stickers

        try:
            await message.delete()  # Delete original user message
        except discord.Forbidden:
            await bot_log.warning(
                message.author,
                message.channel,
                "Missing permissions to delete message.",
            )

        gtx = i18n.TranslationContext(message.guild.id, message.author.id)
        formatted_message_parts = utils.text.smart_split(
            await self._message_formatter(message, saved_stickers),
            mark_continuation=_(gtx, "***Continuation***") + "\n",
        )  # Format message

        files_list = []
        for attachment in attachments_list:
            files_list.append(
                discord.File(attachment[0], attachment[1], spoiler=attachment[2])
            )

        # Send to all wormhole channels
        for channel in self.wormhole_channels:
            target_channel = self.bot.get_channel(channel)
            if target_channel:
                try:
                    for message_part in formatted_message_parts:
                        await target_channel.send(
                            message_part,
                            files=files_list,
                            stickers=discord_stickers,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    for attachment in attachments_list:
                        attachment[0].seek(0)
                except discord.Forbidden:
                    await bot_log.warning(
                        message.author,
                        target_channel,
                        "Missing permissions to send the message.",
                    )

    # COMMANDS

    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole_channel.command(
        name="set",
        description="Register a channel as a wormhole. All messages in this channel will be deleted and mirrored.",
    )
    async def set_wormhole_channel(
        self, itx: discord.Interaction, channel: discord.TextChannel
    ):
        """
        Register a channel as a wormhole. All messages in this channel
        will be deleted and mirrored to all other wormhole channels.
        """
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
        return

    @check.acl2(check.ACLevel.SUBMOD)
    @wormhole_channel.command(
        name="list",
        description="List all channels registered as wormholes.",
    )
    async def list_wormhole_channel(self, itx: discord.Interaction):
        """
        List all channels registered as wormholes.
        """

        class Item:
            def __init__(self, bot: Strawberry, channel):
                self.guild = channel["guild"]
                self.channel = channel["channel"]
                self.slowmode = channel["slowmode"]

        channels = []
        for channel in self.wormhole_channels:
            target_channel = self.bot.get_channel(channel)
            if target_channel:
                channels.append(
                    {
                        "guild": target_channel.guild.name,
                        "channel": target_channel.name,
                        "slowmode": target_channel.slowmode_delay,
                    }
                )
            else:
                channels.append(
                    {
                        "guild": str(
                            WormholeChannel.get_guild_id_by_channel_id(channel)
                        ),
                        "channel": str(channel),
                        "slowmode": None,
                    }
                )

        channels = sorted(channels, key=lambda ch: ch["guild"])[::-1]
        items = [Item(self.bot, channel) for channel in channels]

        table: list[str] = utils.text.create_table(
            items,
            header={
                "guild": _(itx, "Guild"),
                "channel": _(itx, "Channel"),
                "slowmode": _(itx, "Slow mode (s)"),
            },
        )

        await itx.response.send_message(content="```" + table[0] + "```")
        for page in table[1:]:
            await itx.followup.send("```" + page + "```")

        await guild_log.info(
            itx.user,
            itx.channel,
            "User used list command.",
        )
        return

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
                "Missing permissions to set ongoing slow mode. (TIP: Check if 'manage channel' is granted.)",
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
        return

    # requires manage_channels permission
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
    async def remove_wormhole_slowmode(self, itx: commands.Context):
        """Disable slowmode in all wormhole channels."""
        storage.set(self, 0, key="wormhole_slowmode", value=0)
        await self._set_slowmode(0, itx)


# Register the Cog with the bot
async def setup(bot: Strawberry) -> None:
    await bot.add_cog(Wormhole(bot))
