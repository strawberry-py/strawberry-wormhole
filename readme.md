# THIS IS A PROTOTYPE — THE CODE IS ROUGH AND SHOULD BE REVIEWED BEFORE USE

# Strawberry Wormhole

A wormhole extension for [strawberry.py](https://github.com/strawberry-py)

**Strawberry Wormhole** is a Python module that adds *wormhole* functionality. A *wormhole* is a virtual bridge between channels and guilds. When a message is sent to one wormhole-enabled channel, it's automatically forwarded to all others in the same group.

---

Make sure to add the following environment variable to your .env file:

```env
EMOJI_GUILD=<your_emoji_guild_id>
```

This variable specifies the ID of the Discord guild where custom emojis for the wormhole are stored. You can create special custom emojis to replace guild names in messages. The name of each emoji should match the guild's name, converted to lowercase, no spaces,    ASCII characters only (if applicable). For the guild `ČVUT FEL`, the corresponding emoji should be named `cvutfel`.

## Authors

The repository is mantained by [Fialin](https://github.com/j-fiala) and [ArcasCZ](https://github.com/ArcasCZ).

The module was originally created by [The HEX](https://github.com/hex-42-52-4f).

We also have several amazing contributors -- see them at the **Contributors** section on the right panel!
