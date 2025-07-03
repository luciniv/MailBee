import discord
from discord.ext import commands
from discord import app_commands
from classes.error_handler import *
from classes.embeds import *
from utils import checks
from utils.logger import *


class Storage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    

async def setup(bot):
    await bot.add_cog(Storage(bot))
