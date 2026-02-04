import datetime
import io
import re
import unicodedata

import discord
from discord import MessageReferenceType, app_commands
from discord.ext import commands, tasks

from pie import check, i18n, logger, storage, utils
from pie.bot import Strawberry

from .database import (  # Local database model for managing wormhole channels
    BanTimeout,
    WormholeChannel,
)

# Constants
STICKER_INVISIBLE_LINK_FORMAT = "[.]({url})"

# Setup for internationalization (i18n) and logging
_ = i18n.Translator("modules/wormhole").translate
bot_log = logger.Bot.logger()
guild_log = logger.Guild.logger()


class Wormhole(commands.Cog):
    """
    This Cog handles message relaying (a "wormhole") across multiple channels in different guilds.
    """

    wormhole_channels: list[int] = []
    ban_list: dict = {}

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
        self.wormhole_channels: list[int] = WormholeChannel.get_channel_ids()
        self.ban_list = BanTimeout.get_dict()
        self.restore_slowmode.start()

    @tasks.loop(seconds=2.0, count=1)
    async def restore_slowmode(self):
        """Task to restore the slowmode in wormhole channels after module load."""
        delay = storage.get(self, 0, key="wormhole_slowmode")
        await self._set_slowmode(delay)

    @restore_slowmode.before_loop
    async def before_restore_slowmode(self) -> None:
        """Ensures that bot is ready before restoring slowmode"""
        await self.bot.wait_until_ready()

    # HELPER FUNCTIONS

    def _remove_accents(self, input_str: str) -> str:
        nfkd_form = unicodedata.normalize("NFKD", input_str)
        return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

    async def _get_guild_display(self, guild: discord.Guild, gtx) -> str:
        """Helper function for getting guild display name for _message_formatter

        :param guild: discord.Guild to which display will be created
        :param gtx: discord.Guild translation context
        :return: string with guild display name
        """
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
        return str(emoji) if emoji else f"[{guild.name}]"

    async def _format_reply_message(
        self,
        message: discord.Message,
        referenced_msg: discord.Message | None,
        guild_display: str,
        marks_to_add_to_start: str,
        gtx,
    ) -> str:
        """Format a reply-type message.

        :param message: Original discord message
        :param referenced_msg: Referenced message being replied to
        :param guild_display: Display name/emoji for guild
        :param marks_to_add_to_start: Markdown marks to preserve
        :param gtx: Translation context
        :return: Formatted reply message
        """
        msg_tmp = (
            "> " + referenced_msg.content.replace("\n", "\n> ")
            if referenced_msg and referenced_msg.content
            else _(gtx, "Unknown reference message")
        )
        msg = ""
        for m in msg_tmp.strip().split("\n"):
            if not m.startswith("> >"):
                msg += m + "\n"
        return f"> {msg.rstrip()}\n**{guild_display} {message.author.name}:** {marks_to_add_to_start + message.content}\n"

    async def _format_forward_message(
        self,
        message: discord.Message,
        referenced_msg: discord.Message | None,
        guild_display: str,
        gtx,
    ) -> str:
        """Format a forwarded message.

        :param message: Original discord message
        :param referenced_msg: Referenced message being forwarded
        :param guild_display: Display name/emoji for guild
        :param gtx: Translation context
        :return: Formatted forward message
        """
        guild_display_ = (
            await self._get_guild_display(referenced_msg.guild, gtx)
            if referenced_msg
            else ""
        )
        author_info = (
            (guild_display_ + " " + referenced_msg.author.name)
            if referenced_msg and referenced_msg.author and referenced_msg.author.name
            else _(gtx, "Unknown author")
        )
        message_content = (
            referenced_msg.content.replace("```", "")
            if referenced_msg and referenced_msg.content
            else _(gtx, "Unknown forwarded message")
        )
        return (
            f"**{guild_display} {message.author.name}** *{_(gtx, 'forwarded message from')}* **"
            + author_info
            + "** ```"
            + message_content
            + "```"
        )

    async def _message_formatter(
        self, message: discord.Message, stickers: list[str] | None = None
    ) -> str:
        """Helper function to format wormhole message.

        :param message: Discord message to format
        :param stickers: list of custom sticker urls
        :return: Formatted message text
        """
        gtx = i18n.TranslationContext(message.guild.id, message.author.id)

        guild_display = await self._get_guild_display(message.guild, gtx)

        marks = ["### ", "## ", "-# ", "# ", ">>> ", "> "]

        marks_to_add_to_start = (
            "\n" if any(message.content.startswith(m) for m in marks) else ""
        )

        formatted_message = ""

        if message.reference:
            referenced_msg: discord.Message | None = await utils.discord.get_message(
                self.bot,
                message.reference.guild_id,
                message.reference.channel_id,
                message.reference.message_id,
            )
            if (
                message.reference
                and message.reference.type == MessageReferenceType.reply
            ):
                formatted_message = await self._format_reply_message(
                    message, referenced_msg, guild_display, marks_to_add_to_start, gtx
                )
            elif (
                message.reference
                and message.reference.type == MessageReferenceType.forward
            ):
                formatted_message = await self._format_forward_message(
                    message, referenced_msg, guild_display, gtx
                )
        else:
            formatted_message = f"**{guild_display} {message.author.name}:** {marks_to_add_to_start + message.content}\n"

        # add stickers from servers to message
        for s in stickers or []:
            formatted_message = (
                formatted_message.rstrip() + STICKER_INVISIBLE_LINK_FORMAT.format(url=s)
            )
        return formatted_message

    async def _set_slowmode(
        self, delay: int, itx: discord.Interaction | None = None
    ) -> None:
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
                        "I do not have proper permissions to set slow mode. Some channels may need manual intervention.",
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
    async def on_message(self, message: discord.Message) -> None:
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

        if await self.check_if_member_banned(message):
            return

        attachments_list: list = []

        if message.attachments:
            for a in message.attachments:
                tmp: io.BytesIO = io.BytesIO()
                await a.save(tmp)
                attachments_list.append([tmp, a.filename, a.is_spoiler()])

        # discord default stickers cant be resent by url
        saved_stickers: list[str] = []
        discord_stickers: list = []
        for s in message.stickers or []:
            try:
                sticker = await s.fetch()
                if isinstance(sticker, discord.sticker.StandardSticker):
                    discord_stickers.append(sticker)
                elif isinstance(sticker, discord.sticker.GuildSticker):
                    saved_stickers.append(s.url)  # save custom stickers
            except (discord.HTTPException, discord.NotFound) as e:
                await bot_log.warning(
                    message.author,
                    message.channel,
                    f"Failed to fetch sticker: {e}",
                )

        try:
            await message.delete()  # Delete original user message
        except discord.Forbidden:
            await bot_log.warning(
                message.author,
                message.channel,
                "Missing permissions to delete message.",
            )
        except (discord.HTTPException, discord.NotFound) as e:
            await bot_log.error(
                message.author,
                message.channel,
                f"Failed to delete message: {e}",
            )

        gtx = i18n.TranslationContext(message.guild.id, message.author.id)
        formatted_message_parts = utils.text.smart_split(
            await self._message_formatter(message, saved_stickers),
            mark_continuation=_(gtx, "***Continuation***") + "\n",
        )  # Format message

        # Send to all wormhole channels
        for channel_id in self.wormhole_channels:
            target_channel = self.bot.get_channel(channel_id)
            if target_channel:
                try:
                    for idx, message_part in enumerate(formatted_message_parts):
                        # Create files and attach stickers only for the last message part
                        files_to_send = []
                        stickers_to_send = []

                        if idx == len(formatted_message_parts) - 1:
                            # Create fresh File objects for this channel
                            for attachment in attachments_list:
                                files_to_send.append(
                                    discord.File(
                                        attachment[0],
                                        attachment[1],
                                        spoiler=attachment[2],
                                    )
                                )
                            stickers_to_send = discord_stickers

                        await target_channel.send(
                            message_part,
                            files=files_to_send,
                            stickers=stickers_to_send,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )

                    # Reset BytesIO streams for next channel
                    for attachment in attachments_list:
                        attachment[0].seek(0)
                except discord.Forbidden:
                    await bot_log.warning(
                        message.author,
                        target_channel,
                        "Missing permissions to send the message.",
                    )
                except discord.HTTPException as e:
                    await bot_log.error(
                        message.author,
                        target_channel,
                        f"Failed to send message: {e}",
                    )
                except Exception as e:
                    await bot_log.error(
                        message.author,
                        target_channel,
                        f"Unexpected error sending message: {e}",
                    )

    # COMMANDS

    async def check_if_member_banned(self, message: discord.Message) -> bool:
        # Check ban list
        if message.author.name in self.ban_list.keys():
            if not self.ban_list[message.author.name]:
                return False
            if datetime.datetime.utcnow() > self.ban_list[message.author.name]:
                banned_users = BanTimeout.get(message.author.name)
                banned_user = banned_users[0] if banned_users else None
                banned_user.delete()
                del self.ban_list[message.author.name]

                await bot_log.info(
                    None,
                    None,
                    f"Ban of user {message.author.name} has expired.",
                )
                return False
            else:
                return True
        return False

    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole_channel.command(
        name="set",
        description="Register a channel as a wormhole. All messages in this channel will be deleted and mirrored.",
    )
    async def set_wormhole_channel(
        self, itx: discord.Interaction, channel: discord.TextChannel
    ) -> None:
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
    async def list_wormhole_channel(self, itx: discord.Interaction) -> None:
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
    ) -> None:
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
    async def set_wormhole_slowmode(self, itx: discord.Interaction, delay: int) -> None:
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
    async def remove_wormhole_slowmode(self, itx: discord.Interaction) -> None:
        """Disable slowmode in all wormhole channels."""
        storage.set(self, 0, key="wormhole_slowmode", value=0)
        await self._set_slowmode(0, itx)

    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole.command(
        name="ban",
        description="Ban user from sending messages into wormhole.",
    )
    @app_commands.describe(time="Time in seconds")
    async def wormhole_ban_user(
        self, itx: discord.Interaction, user: discord.User, time: int = None
    ):
        """
        Ban user from sending messages into wormhole.
        """
        if user.name in self.ban_list.keys():
            await itx.response.send_message(
                _(itx, "This user is already banned."), ephemeral=True
            )
            return

        if time:
            ban_end = datetime.datetime.utcnow() + datetime.timedelta(seconds=time)
        else:
            ban_end = None

        BanTimeout.add(name=user.name, time=ban_end)
        self.ban_list.update({user.name: ban_end})
        if time:
            await itx.response.send_message(
                _(itx, "User {username} was blocked for {seconds} seconds.").format(
                    username=user.name, seconds=time
                ),
                ephemeral=True,
            )
            await bot_log.info(
                itx.user if itx else None,
                itx.channel if itx else None,
                f"User {user.name} was banned from wormhole for {time} seconds.",
            )
        else:
            await itx.response.send_message(
                _(itx, "User {username} was blocked.").format(username=user.name),
                ephemeral=True,
            )
            await bot_log.info(
                itx.user if itx else None,
                itx.channel if itx else None,
                f"User {user.name} was banned from wormhole.",
            )

    @check.acl2(check.ACLevel.SUBMOD)
    @wormhole.command(
        name="banlist",
        description="List banned users.",
    )
    async def wormhole_list_banned(self, itx: discord.Interaction):
        """
        List banned users.
        """

        class Item:
            def __init__(self, pattern):
                self.idx = pattern.idx
                self.name = pattern.name
                self.time = pattern.time

        bantimout = BanTimeout.get_all()
        items = [Item(bt) for bt in bantimout]

        table: list[str] = utils.text.create_table(
            items,
            header={
                "idx": _(itx, "ID"),
                "name": _(itx, "Name"),
                "time": _(itx, "Time"),
            },
        )

        await itx.response.send_message(content="```" + table[0] + "```")
        for page in table[1:]:
            await itx.followup.send("```" + page + "```")

        await guild_log.info(
            itx.user,
            itx.channel,
            "User used list wormhole ban and timeout command.",
        )
        return

    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole.command(
        name="unban",
        description="Remove ban for user.",
    )
    async def wormhole_unban_user(self, itx: discord.Interaction, user: discord.User):
        """
        Remove ban for user.
        """
        banned_users = BanTimeout.get(user.name)
        banned_user = banned_users[0] if banned_users else None
        banned_user.delete()
        del self.ban_list[user.name]

        await itx.response.send_message(
            _(itx, "User {username} was unblocked.").format(username=user.name),
            ephemeral=True,
        )
        await bot_log.info(
            itx.user if itx else None,
            itx.channel if itx else None,
            f"User {user.name} was unblocked from accessing wormhole.",
        )
        return


# Register the Cog with the bot
async def setup(bot: Strawberry) -> None:
    await bot.add_cog(Wormhole(bot))
