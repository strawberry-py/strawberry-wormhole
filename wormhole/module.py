import os
import re

import discord
from discord.ext import commands

from pie import check, i18n, logger
from pie.bot import Strawberry

from .database import (  # Local database model for managing wormhole channels
    WormholeChannel,
)

# Setup for internationalization (i18n) and logging
_ = i18n.Translator(__file__).translate
bot_log = logger.Bot.logger()
guild_log = logger.Guild.logger()

# ID of the guild (server) that hosts custom emojis
emoji_guild_id = int(os.getenv("EMOJI_GUILD"))


class Wormhole(commands.Cog):
    """
    This Cog handles message relaying (a "wormhole") across multiple channels in different guilds.
    """

    wormhole_channels: list[int] = []

    def __init__(self, bot: Strawberry):
        self.bot: Strawberry = bot
        self.wormhole_channels = WormholeChannel.get_channel_ids()

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

    # Command group: !wormhole
    @check.acl2(check.ACLevel.GUILD_OWNER)
    @commands.group()
    async def wormhole(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid wormhole command.")

    # Subgroup: !wormhole set
    @check.acl2(check.ACLevel.GUILD_OWNER)
    @wormhole.group()
    async def set(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid set command under wormhole.")

    # Command: !wormhole set channel <channel_id>
    @commands.guild_only()
    @check.acl2(check.ACLevel.GUILD_OWNER)  # ACL rules
    @set.command(name="channel")
    async def set_wormhole_channel(self, ctx: commands.Context, *, channel_id: str):
        """
        Register a channel as a wormhole. All messages in this channel
        will be deleted and mirrored to all other wormhole channels.
        """
        if channel_id is None:
            await ctx.reply("Channel ID is empty.")
            return

        try:
            cha_id = int(channel_id)
        except (ValueError, TypeError):
            await ctx.reply(f"`{channel_id}` is not a valid number.")
            return

        channel = ctx.guild.get_channel(cha_id)
        if channel is None:
            await ctx.reply("Channel not found.")
            return

        if WormholeChannel.check_existence(cha_id):
            await ctx.reply("Channel is already set as wormhole channel.")
            return

        WormholeChannel.add(guild_id=ctx.guild.id, channel_id=cha_id)
        self.wormhole_channels.append(cha_id)
        await ctx.reply(f"Channel `{channel.name}` was added as wormhole channel.")
        await guild_log.info(
            ctx.author,
            ctx.channel,
            f"Channel '{channel.name}' was added as wormhole channel.",
        )
        return

    # Command: !wormhole set slowmode <seconds>
    # requires manage_channels permission
    @commands.guild_only()
    @check.acl2(check.ACLevel.BOT_OWNER)
    @set.command(name="slowmode")
    async def set_wormhole_slowmode(self, ctx: commands.Context, *, time: str):
        """Apply slowmode to all wormhole channels."""
        try:
            delay = int(time)
        except (ValueError, TypeError):
            await ctx.reply(f"`{time}` is not a valid number.")
            return

        for channel in self.wormhole_channels:
            target_channel = self.bot.get_channel(channel)
            if target_channel:
                await target_channel.edit(slowmode_delay=delay)

        await ctx.reply("Slow mode set")
        await bot_log.info(
            ctx.author, ctx.channel, f"Wormhole slow mode set to {delay} seconds."
        )
        return

    # Subgroup: !wormhole remove
    @check.acl2(check.ACLevel.GUILD_OWNER)
    @wormhole.group()
    async def remove(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid set command under wormhole.")

    # Command: !wormhole remove channel <channel_id>
    @commands.guild_only()
    @check.acl2(check.ACLevel.GUILD_OWNER)
    @remove.command(name="channel")
    async def unset_wormhole_channel(self, ctx: commands.Context, *, channel_id: str):
        """Unregister a channel from the wormhole."""
        if channel_id is None:
            await ctx.reply("Channel ID is empty.")
            return

        try:
            cha_id = int(channel_id)
        except (ValueError, TypeError):
            await ctx.reply(f"`{channel_id}` is not a valid number.")
            return

        channel = ctx.guild.get_channel(cha_id)
        if channel is None:
            await ctx.reply("Channel not found.")
            return

        if not WormholeChannel.check_existence(cha_id):
            await ctx.reply("Channel is not set as wormhole channel.")
            return

        WormholeChannel.remove(guild_id=ctx.guild.id, channel_id=cha_id)
        self.wormhole_channels.remove(cha_id)
        await ctx.reply(f"Channel `{channel.name}` was removed as wormhole channel.")
        await guild_log.info(
            ctx.author,
            ctx.channel,
            f"Channel '{channel.name}' was removed as wormhole channel.",
        )
        return

    # Command: !wormhole remove slowmode
    # requires manage_channels permission
    @commands.guild_only()
    @check.acl2(check.ACLevel.BOT_OWNER)
    @remove.command(name="slowmode")
    async def remove_wormhole_slowmode(self, ctx: commands.Context):
        """Disable slowmode in all wormhole channels."""
        for channel in self.wormhole_channels:
            target_channel = self.bot.get_channel(channel)
            if target_channel:
                await target_channel.edit(slowmode_delay=0)

        await ctx.reply("Slow mode removed")
        await bot_log.info(
            ctx.author, ctx.channel, "Wormhole slow mode set to 0 seconds."
        )
        return


# Register the Cog with the bot
async def setup(bot: Strawberry) -> None:
    await bot.add_cog(Wormhole(bot))
