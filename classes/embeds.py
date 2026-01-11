from datetime import datetime, timezone
from typing import Optional

import discord
from discord import Colour, Embed


class Embeds(discord.Embed):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("color", discord.Color.green())
        kwargs.setdefault("timestamp", datetime.now(timezone.utc))
        super().__init__(*args, **kwargs)

    # TODO: change embeds to accept description by default
    @classmethod
    def success(cls, **kwargs):
        return cls(timestamp=None, **kwargs)

    @classmethod
    def error(cls, **kwargs):
        return cls(timestamp=None, color=discord.Color.red(), **kwargs)

    @classmethod
    def info(cls, **kwargs):
        return cls(timestamp=None, color=discord.Color.blue(), **kwargs)

    # Ticket send embeds: uses mod member, user member, and timestamp
    @classmethod
    def ticket_send(cls, mod, user, flair="", **kwargs):
        title = f"Message Sent [STAFF] {flair}"
        author_text = f"{mod.name} | {mod.id}"
        footer_text = f"{user.name} | {user.id}"

        embed = cls(title=title, **kwargs)
        embed.set_author(name=author_text, icon_url=mod.display_avatar.url)
        embed.set_footer(text=footer_text, icon_url=user.display_avatar.url)

        return embed

    # Ticket receive embeds, set footer to user and set timestamp
    @classmethod
    def ticket_receive(cls, user, **kwargs):
        title = "Message Received"
        footer_text = f"{user.name} | {user.id}"

        embed = cls(title=title, **kwargs)
        embed.set_footer(text=footer_text, icon_url=user.display_avatar.url)

        return embed

    # DM send embeds: uses guild and timestamp
    @classmethod
    def dm_send(cls, guild, **kwargs):
        title = "Message Sent"
        icon_url = guild.icon.url if guild.icon else None

        embed = cls(title=title, **kwargs)
        embed.set_footer(text=guild.name, icon_url=icon_url)

        return embed

    # DM receive embeds: uses guild, sometimes mod member and timestamp
    @classmethod
    def dm_receive(cls, guild, mod_name, mod_url, **kwargs):
        title = "Message Received"
        icon_url = guild.icon.url if guild.icon else None

        embed = cls(title=title, **kwargs)
        embed.set_author(name=mod_name, icon_url=mod_url)
        embed.set_footer(text=guild.name, icon_url=icon_url)

        return embed
