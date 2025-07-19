# THIS IS A PROTOTYPE — THE CODE IS ROUGH AND SHOULD BE REVIEWED BEFORE USE

# Strawberry Wormhole

An unofficial extension for [strawberry.py](https://github.com/strawberry-py)

**Strawberry Wormhole** is a Python module that adds *wormhole* functionality. A *wormhole* is a virtual bridge between channels. When a message is sent to one wormhole-enabled channel, it's automatically forwarded to all others in the same group.

---

Make sure to add the following environment variable to your .env file:

```env
EMOJI_GUILD=<your_emoji_guild_id>
```

This variable specifies the ID of the Discord guild where custom emojis for the wormhole are stored. You can create special custom emojis to replace guild names in messages. The name of each emoji should match the guild's name, converted to lowercase, no spaces,    ASCII characters only (if applicable). For the guild `ČVUT FEL`, the corresponding emoji should be named `cvutfel`.
