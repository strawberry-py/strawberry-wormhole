import os
import re

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

# ID of the guild (server) that hosts custom emojis
emoji_guild_id = int(os.getenv("EMOJI_GUILD"))


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
        delay = storage.get(self, 0, key="wormhole_slowmode")
        await self._set_slowmode(delay)

    @restore_slowmode.before_loop
    async def before_restore_slowmode(self):
        """Ensures that bot is ready before registering"""
        await self.bot.wait_until_ready()

    # Helper function to format messages before sending
    def _message_formatter(self, message: discord.Message):
        guild = message.guild
        guild_name = guild.name if guild else "Unknown Server"

        emoji_guild = self.bot.get_guild(emoji_guild_id)
        emoji = None
        if emoji_guild:
            emoji = next(
                (
                    e
                    for e in emoji_guild.emojis
                    if e.name.replace(" ", "").lower()
                    == guild_name.replace(" ", "").lower()
                ),
                None,
            )
        guild_display = str(emoji) if emoji else f"[{guild_name}]"

        # Sanitize user mentions to prevent abuse across servers
        new_content = re.sub(r"<@(\d+)>", r"`[TAGS ARE NOT ALLOWED!]`", message.content)

        formatted_message = f"**{guild_display} {message.author.name}:** {new_content}"
        return formatted_message

    # Listen to all messages in channels
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages
        if message.author.bot:
            return

        # Ignore commands
        if message.content.startswith(self.bot.command_prefix):
            # await message.delete()
            return

        # Only proceed if this channel is registered as a wormhole
        if message.channel.id not in self.wormhole_channels:
            return

        await message.delete()  # Delete original user message

        formatted_message = self._message_formatter(message)  # Format message

        # Send to all wormhole channels
        for channel in self.wormhole_channels:
            target_channel = self.bot.get_channel(channel)
            if target_channel:
                await target_channel.send(formatted_message)

    @check.acl2(check.ACLevel.GUILD_OWNER)
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

        delay = storage.get(self, 0, key="wormhole_slowmode")
        await channel.edit(slowmode_delay=delay)
        return

    async def _set_slowmode(self, delay: int):
        for channel in self.wormhole_channels:
            target_channel = self.bot.get_channel(channel)
            if target_channel:
                await target_channel.edit(slowmode_delay=delay)

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

        await self._set_slowmode(delay)

        storage.set(self, 0, key="wormhole_slowmode", value=delay)
        await itx.response.send_message(_(itx, "Slow mode set."), ephemeral=True)
        await bot_log.info(
            itx.user, itx.channel, f"Wormhole slow mode set to {delay} seconds."
        )
        return

    @check.acl2(check.ACLevel.GUILD_OWNER)
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

        await channel.edit(slowmode_delay=0)
        return

    @check.acl2(check.ACLevel.BOT_OWNER)
    @wormhole_slowmode.command(
        name="remove",
        description="Disable slowmode in all wormhole channels.",
    )
    async def remove_wormhole_slowmode(self, itx: commands.Context):
        """Disable slowmode in all wormhole channels."""
        await self._set_slowmode(0)

        storage.set(self, 0, key="wormhole_slowmode", value=0)
        await itx.response.send_message(_(itx, "Slow mode removed"), ephemeral=True)
        await bot_log.info(
            itx.user, itx.channel, "Wormhole slow mode set to 0 seconds."
        )
        return


# Register the Cog with the bot
async def setup(bot: Strawberry) -> None:
    await bot.add_cog(Wormhole(bot))
