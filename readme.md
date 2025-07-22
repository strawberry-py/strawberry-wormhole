# THIS IS A PROTOTYPE — THE CODE IS ROUGH AND SHOULD BE REVIEWED BEFORE USE

# Strawberry Wormhole

A wormhole extension for [strawberry.py](https://github.com/strawberry-py)

**Strawberry Wormhole** is a Python module that adds *wormhole* functionality. A *wormhole* is a virtual bridge between channels and guilds. When a message is sent to one wormhole-enabled channel, it's automatically forwarded to all others in the same group.

---

You can create special custom emojis to replace guild names in messages. These custom emojis are stored as application emojis and they can be uploaded in [discord developer portal](https://discord.com/developers/applications). The name of each emoji should match the guild's name, converted to lowercase, with spaces converted to `'_'`, ASCII characters only (if applicable). For the guild `ČVUT FEL`, the corresponding emoji should be named `cvut_fel`.

## Authors

The repository is mantained by [Fialin](https://github.com/j-fiala) and [ArcasCZ](https://github.com/ArcasCZ).

The module was originally created by [The HEX](https://github.com/hex-42-52-4f).

We also have several amazing contributors -- see them at the **Contributors** section on the right panel!
