# FIXME make caches to reduce all fetches
import discord
import asyncio
from datetime import datetime, timezone
from utils.logger import *


class Cache:
    def __init__(self, bot):
        self.bot = bot
        self.user_cache = {}
        self.member_cache = {}


    async def store_user(self, user: discord.User):
        epoch_time = int(datetime.now(timezone.utc).timestamp())
        self.user_cache[str(user.id)] = (user, epoch_time)
        print("user cache keys are", self.user_cache.keys())


    async def get_user(self, userID: int):
        try:
            user = None
            epoch = None

            result = self.user_cache.get(str(userID), None)
            if result is not None:
                user, epoch = result
                print("got cached user")
                return user
            else:
                try:
                    user = await asyncio.wait_for(self.bot.fetch_user(userID), timeout=1)
                except Exception as e:
                    print("failed to fetch global user", e)
                    return None
                print("fetched a user", user.name)
                return user
        except Exception as e:
            logger.exception(f"get_user sent an error: {e}")


    async def store_guild_member(self, guildID: int, member: discord.Member):
        epoch_time = int(datetime.now(timezone.utc).timestamp())
        self.member_cache[(str(member.id), str(guildID))] = (member, epoch_time)
        print("member cache keys are", self.member_cache.keys())


    async def get_guild_member(self, guild, memberID: int):
        try:
            member = None
            epoch = None

            result = self.member_cache.get((str(memberID), str(guild.id)), None)
            if result is not None:
                member, epoch = result
                print("got cached member")
                return member
            else:
                epoch_time = int(datetime.now(timezone.utc).timestamp())
                member = guild.get_member(memberID)
                if member is None:
                    try:
                        member = await asyncio.wait_for(guild.fetch_member(memberID), timeout=1)
                    except Exception as e:
                        logger.error(f"failed to fetch guild member using id {memberID}:", e)
                        return None
                    print("fetched a member", member.name)
                    self.member_cache[(str(member.id), str(guild.id))] = (member, epoch_time)
                    return member
                else:
                    self.member_cache[(str(member.id), str(guild.id))] = (member, epoch_time)
                    return member
            
        except Exception as e:
            logger.exception(f"get_member sent an error: {e}")



