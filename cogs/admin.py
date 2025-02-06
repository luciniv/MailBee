import discord
from discord.ext import commands
from utils.logger import *


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    # Restarts the bot
    @commands.command(name="old_restart")
    @commands.is_owner()
    async def restart(self, ctx):
        await ctx.send("Restarting the bot...")
        await self.bot.data_manager.close_db()
        await self.bot.data_manager.close_redis()
        await self.bot.close()


async def setup(bot):
    await bot.add_cog(Admin(bot))
