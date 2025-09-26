import asyncio
import time

import discord

from utils.logger import *

MEMBER_UPDATE = 43200  # 12 hours
CHANNEL_UPDATE = 172800  # 48 hours


class Cache:
    def __init__(self, bot):
        self.bot = bot
        self.user_cache = {}
        self.member_cache = {}
        self.channel_cache = {}

    async def store_user(self, user: discord.User):
        epoch_time = int(time.time())
        self.user_cache[user.id] = (user, epoch_time)

    async def get_user(self, user_id: int):
        try:
            user = None
            epoch = None

            result = self.user_cache.get(str(user_id), None)
            if result:
                user, epoch = result
                if (int(time.time()) - epoch) <= MEMBER_UPDATE:
                    return user

            else:
                epoch_time = int(time.time())
                try:
                    user = await asyncio.wait_for(
                        self.bot.fetch_user(user_id), timeout=2
                    )
                except Exception:
                    return None
                self.user_cache[str(user.id)] = (user, epoch_time)
                return user

        except Exception as e:
            logger.exception(f"get_user sent an error: {e}")

    async def store_guild_member(self, guild_id: int, member: discord.Member):
        epoch_time = int(time.time())
        self.member_cache[(member.id, guild_id)] = (member, epoch_time)

    async def get_guild_member(self, guild: discord.Guild, member_id: int):
        try:
            member = None
            epoch = None

            result = self.member_cache.get((member_id, guild.id), None)
            if result:
                member, epoch = result
                if (int(time.time()) - epoch) <= MEMBER_UPDATE:
                    return member

            epoch_time = int(time.time())
            try:
                member = await asyncio.wait_for(
                    guild.fetch_member(member_id), timeout=5
                )
            except Exception as e:
                logger.error(f"Failed to fetch guild member using id {member_id}: {e}")
                return None
            self.member_cache[(member.id, guild.id)] = (member, epoch_time)
            return member

        except Exception as e:
            logger.exception(f"get_guild_member sent an error: {e}")

    async def store_channel(self, channel: discord.abc.GuildChannel):
        epoch_time = int(time.time())
        self.channel_cache[channel.id] = (channel, epoch_time)

    async def get_channel(self, channel_id: int):
        try:
            channel = None
            epoch = None

            result = self.channel_cache.get(channel_id, None)
            if result is not None:
                channel, epoch = result
                if (int(time.time()) - epoch) <= CHANNEL_UPDATE:
                    return channel

            epoch_time = int(time.time())
            channel = self.bot.get_channel(channel_id)
            if channel is not None:
                self.channel_cache[channel.id] = (channel, epoch_time)
                return channel

            else:
                try:
                    channel = await asyncio.wait_for(
                        self.bot.fetch_channel(channel_id), timeout=2
                    )
                except Exception as e:
                    return None
                self.channel_cache[channel.id] = (channel, epoch_time)
                return channel

        except Exception as e:
            logger.exception(f"get_channel sent an error: {e}")
