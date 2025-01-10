import discord
from discord.ext import commands
from discord import app_commands
from utils import emojis, checks, queries
from utils.logger import *


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot 

    @commands.hybrid_group()
    async def stats(self, ctx):
        pass


    # Print user specific data
    # Tickets closed (compare to total)
    # NOTE just accomplishing this first, as a test


    # Ticket messages sent to users (compare to total)
    # Ticket discussion messages (compare to total)

    # Weekly, monthly, all time
    # All total comparisons include percents
    @stats.command(name="server", description="Display this server's statistics")
    @checks.has_access()
    async def permissions(self, ctx):
        this_guildID = ctx.guild.id
        editEmbed = discord.Embed(title=f"Edit Results {emojis.mantis}", 
                                description="", 
                                color=0x3ad407)
        

    @stats.command(name="member", description="Display statistics for a certain member")
    @checks.has_access()
    @app_commands.describe(member="Selected member")
    async def permissions(self, ctx, member: discord.Member):
        this_guildID = ctx.guild.id

        editEmbed = discord.Embed(title=f"Edit Results {emojis.mantis}", 
                                description="", 
                                color=0x3ad407)
        # input_list, goofy ass list of same guild, same user ID
        await self.bot.data_manager.execute_query(queries.member_summary, True, False)



# Commands to display data


    # Server specific data
    # Tickets closed 
    # Avg ticket duration
    # Avg first response time
    # Avg mod response time to user message (includes first response time)


# Weekly, monthly, all time
# All total comparisons include percents


async def setup(bot):
    await bot.add_cog(Stats(bot))