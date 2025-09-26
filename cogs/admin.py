import discord
from discord.ext import commands

from utils.logger import *


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(Admin(bot))
