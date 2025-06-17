# FIXME make caches to reduce all fetches
import discord
import asyncio
import time
from utils.logger import *


class Cache:
    def __init__(self, bot):
        self.bot = bot
        self.user_cache = {}
        self.member_cache = {}
        self.channel_cache = {}


    async def store_user(self, user):
        epoch_time = int(time.time())
        self.user_cache[str(user.id)] = (user, epoch_time)


    async def get_user(self, userID: int):
        try:
            user = None
            epoch = None

            result = self.user_cache.get(str(userID), None)
            if result is not None:
                user, epoch = result
                return user
            else:
                epoch_time = int(time.time())
                try:
                    user = await asyncio.wait_for(self.bot.fetch_user(userID), timeout=1)
                except Exception as e:
                    return None
                self.user_cache[str(user.id)] = (user, epoch_time)
                return user
        except Exception as e:
            logger.exception(f"get_user sent an error: {e}")


    async def store_guild_member(self, guildID: int, member):
        epoch_time = int(time.time())
        self.member_cache[(str(member.id), str(guildID))] = (member, epoch_time)


    async def get_guild_member(self, guild, memberID: int):
        try:
            member = None
            epoch = None

            result = self.member_cache.get((str(memberID), str(guild.id)), None)
            if result is not None:
                member, epoch = result
                return member
            else:
                epoch_time = int(time.time())
                member = guild.get_member(memberID)
                if member is None:
                    try:
                        member = await asyncio.wait_for(guild.fetch_member(memberID), timeout=1)
                    except Exception as e:
                        logger.error(f"failed to fetch guild member using id {memberID}:", e)
                        return None
                    self.member_cache[(str(member.id), str(guild.id))] = (member, epoch_time)
                    return member
                else:
                    self.member_cache[(str(member.id), str(guild.id))] = (member, epoch_time)
                    return member
            
        except Exception as e:
            logger.exception(f"get_member sent an error: {e}")


    # For guild channels, including ticket channels, logs, and threads
    async def store_channel(self, channel):
        epoch_time = int(time.time())
        self.channel_cache[str(channel.id)] = (channel, epoch_time)


    async def get_channel(self, channelID: int):
        try:
            channel = None
            epoch = None

            result = self.channel_cache.get(str(channelID), None)
            if result is not None:
                channel, epoch = result
                return channel
            else:
                epoch_time = int(time.time())
                channel = self.bot.get_channel(channelID)
                if channel is not None:
                    self.channel_cache[str(channel.id)] = (channel, epoch_time)
                    return channel
                else:
                    try:
                        channel = await asyncio.wait_for(self.bot.fetch_channel(channelID), timeout=1)
                    except Exception as e:
                        return None 
                    self.channel_cache[str(channel.id)] = (channel, epoch_time)
                    return channel
        except Exception as e:
            logger.exception(f"get_user sent an error: {e}")