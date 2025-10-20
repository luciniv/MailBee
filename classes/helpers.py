import asyncio
import os
import re
import time

import aiohttp
import discord
from utils.logger import *

tenor_key = os.getenv("TENOR_KEY")
tenor_cache = {}

from dataclasses import dataclass, asdict
from datetime import datetime, timezone


# ticket class item is created upon form submission
# thus, this must contain everything to open the ticket
# cant store user, guild, or category objects due to redis storage
# will make use of memory caches for these

# create ticket object from ticket submission
# add ticket object to queue
# send object to opener to "open" it (open a ticket with it)
# ticket opener will no longer handle data lookups, ticket submitter does

# ticket id is only for tickets that open


@dataclass
class Ticket:
    user_id: int
    guild_id: int
    category_id: int
    type_id: int
    type_name: str
    data: dict
    time_taken: int
    ping_roles: list[int] = None
    nsfw: bool = False
    roblox_username: str = ""
    roblox_id: int = -1
    robux_spent: int = -1
    hours_played: float = -1
    submitted_at: int = int(time.time())
    dm_message_id: int | None = None
    is_new: bool = True
    is_queued: bool = False

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)

    @property
    def user_mention(self):
        return f"<@{self.user_id}>"


def clean_username_id(text: str):
    username = text.split(" ")[0].strip()
    user_id = text.split(" ")[2].strip()
    return username, user_id


async def export_ticket_messages(channel: discord.TextChannel):
    try:
        transcript = []
        async for message in channel.history(oldest_first=True, limit=200):
            type = ""
            username = ""
            id = ""
            content = ""

            # Skip other bot messages
            if message.author.bot and message.author.id != 1333954467519004673:
                continue

            # Ticket embeds
            if message.embeds and message.embeds[0].title:
                embed = message.embeds[0]

                if len(message.embeds) == 2:
                    type = "USER"
                    form_embed = message.embeds[1]
                    username, id = clean_username_id(embed.footer.text)
                    for field in form_embed.fields:
                        content += f"{field.name}: {field.value}\n"

                elif "[STAFF]" in embed.title:
                    type = "STAFF"
                    if embed.description:
                        username, id = clean_username_id(embed.author.name)
                        content = embed.description

                    else:
                        continue

                elif "Received" in embed.title:
                    type = "USER"
                    if embed.description:
                        username, id = clean_username_id(embed.footer.text)
                        content = embed.description
                    else:
                        continue
                else:
                    continue

            # Staff comments
            elif message.author.id != 1333954467519004673:
                type = "COMMENT"
                username = message.author.name
                id = message.author.id
                content = message.content

            if not content or content.startswith(("+", "/")):
                continue

            timestamp = message.created_at.strftime("%d-%m-%Y %H:%M:%S")
            header = f"{timestamp} | {username} ({id}) [{type}]:"
            transcript.append(f"{header} {content}")

        return "\n".join(transcript)

    except Exception as e:
        logger.exception(e)
        print(f"export_ticket_messages sent an error: {e}")
        return None


async def convert_mentions(bot, text: str, guild: discord.Guild):
    async def replace_mention(match):
        channel_id = int(match.group(1))
        channel = await bot.cache.get_channel(channel_id)
        if channel:
            return f"https://discord.com/channels/{guild.id}/{channel_id}"
        return match.group(0)

    return re.sub(r"<#(\d+)>", replace_mention, text)


async def verify_text(bot, guild: discord.Guild, text: str, limit: int = 3000):
    text = await convert_mentions(bot, text, guild)
    if not text:
        return False, "❌ No text provided."
    elif len(text) > limit:
        return False, f"❌ Text exceeds limit of {limit} characters."
    return True, text


def get_ticket_channel_info(channel: discord.ChannelType):
    id_list = (channel.topic).split()
    thread_id = id_list[-1]
    user_id = id_list[-2]
    return thread_id, user_id


def add_footers(pages):
    for page in range(len(pages)):
        pages[page].set_footer(
            text=f"Use the buttons below to navigate (Page {page + 1}/{len(pages)})"
        )
    return pages
