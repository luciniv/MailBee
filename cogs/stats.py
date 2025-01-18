import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
from datetime import datetime
from typing import List
from classes.error_handler import *
from utils import emojis, checks, queries
from utils.logger import *


def fill_embed(statsEmbed: discord.Embed, 
               data: List[int], 
               index: int, 
               rows: List[str], 
               columns: List[str]):
    
    for row in rows:
        count = 0
        fields = queries.generate_fields(data, index, columns) 
        
        # First field is a heading
        statsEmbed.add_field(name=f"", value=f"**{row} {'-' * (78 - len(row))}**", inline=False)

        # Outputs the three fields from generate_fields
        for col, field in zip(columns, fields):
            if count == 2:
                field += f"\n** **"

            statsEmbed.add_field(name=col, value=field, inline=True)
            count += 1

        index += 6

    return statsEmbed


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot 

  
    @commands.hybrid_command(name="server_stats", description="Display this server's statistics,"
                            " includes current tickets open and response averages")
    @checks.has_access()
    @app_commands.describe(timeframe="Select list to show (server role permissions or monitored channels)")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Past Hour", value="1 HOUR"),
        app_commands.Choice(name="Past Day", value="1 DAY"),
        app_commands.Choice(name="Past Week", value="1 WEEK"),
        app_commands.Choice(name="Past Month", value="1 MONTH"),
        app_commands.Choice(name="All Time", value="TOTAL"),
        app_commands.Choice(name="All of the above", value="ALL")])
    async def server_stats(self, ctx, timeframe: discord.app_commands.Choice[str]):
        try:
            # Allows command to take longer than 3 seconds
            await ctx.defer()

            choice = timeframe.value
            name = timeframe.name
            guildID = ctx.guild.id
            rows = ["Past Hour", "Past Day", "Past Week", "Past Month", "All Time"]
            columns = ["⏱️ Average Ticket Duration", "⭐️ Average First Response Time", "💬 Average Messages Per Ticket Resolved"]
            intervals = ["1 HOUR", "1 DAY", "1 WEEK", "1 MONTH", "TOTAL"]

            if (choice != "ALL"):
                intervals = [f"{choice}"]
                rows = [f"{name}"]

            bot_user = self.bot.user
            time_now = datetime.now()
            format_time = time_now.strftime("Today at %-I:%M %p")

            statsEmbed = discord.Embed(title=f"Server Statistics {emojis.mantis}", 
                                    description=f"Data formatted as **server's data** / **all server data**  - calculated percent", 
                                    color=0x3ad407)
            statsEmbed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)
            statsEmbed.set_footer(text=f"Mantid · {format_time}", icon_url=bot_user.avatar.url)

            query = queries.server_stats(guildID, intervals)
            result = await self.bot.data_manager.execute_query(query)

            if result is not None: # go ahead to build embed
                index = 0
                data = result[0]

                statsEmbed.add_field(name="📬 Tickets Open", value=queries.format_data(data, index, None), inline=True)
                index += 2
                statsEmbed.add_field(name="📮 Total Tickets", value=queries.format_data(data, index, None), inline=True)
                index += 2
                fill_embed(statsEmbed, data, index, rows, columns)
                
            else:
                statsEmbed.add_field(name="No data found", value="", inline=False)
                
            await ctx.send(embed=statsEmbed)

            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"/server_stats sent an error: {e}")

        


    # Could do a bar chart as well, send charts SEPARATE!! so the full image is displayed

    @commands.hybrid_command(name="mod_activity", description="Display a moderator's ticketing activity over the past X amount of time")
    @checks.has_access()
    @app_commands.describe(member="Selected moderator")
    @app_commands.describe(timeframe="Select list to show (server role permissions or monitored channels)")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Past Hour", value="1 HOUR"),
        app_commands.Choice(name="Past Day", value="1 DAY"),
        app_commands.Choice(name="Past Week", value="1 WEEK"),
        app_commands.Choice(name="Past Month", value="1 MONTH"),
        app_commands.Choice(name="All Time", value="TOTAL"),
        app_commands.Choice(name="All of the above", value="ALL")])
    async def mod_activity(self, ctx, member: discord.Member, timeframe: discord.app_commands.Choice[str]):
        try:
            # Allows command to take longer than 3 seconds
            await ctx.defer()

            choice = timeframe.value
            name = timeframe.name
            guildID = ctx.guild.id
            closeByID = member.id
            rows = ["Past Hour", "Past Day", "Past Week", "Past Month", "All Time"]
            columns = ["✅ Tickets Closed", "📤 Ticket Replies", "💬 Ticket Chats"]
            intervals = ["1 HOUR", "1 DAY", "1 WEEK", "1 MONTH", "TOTAL"]

            if (choice != "ALL"):
                intervals = [f"{choice}"]
                rows = [f"{name}"]

            bot_user = self.bot.user
            time_now = datetime.now()
            format_time = time_now.strftime("Today at %-I:%M %p")

            statsEmbed = discord.Embed(title=f"Moderator Activity {emojis.mantis}", 
                                    description=f"Data formatted as **moderator's data** / **total data** - calculated percent", 
                                    color=0x3ad407)
            statsEmbed.set_author(name=member.name, icon_url=member.avatar.url)
            statsEmbed.set_footer(text=f"Mantid · {format_time}", icon_url=bot_user.avatar.url)
            
            query = queries.mod_activity(guildID, closeByID, intervals)
            result = await self.bot.data_manager.execute_query(query)

            if result is not None: # go ahead to build embed
                index = 0
                data = result[0]
              
                fill_embed(statsEmbed, data, index, rows, columns)

            else:
                statsEmbed.add_field(name="No data found", value="", inline=False)
                
            await ctx.send(embed=statsEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/mod_data sent an error: {e}")
            
            
        
    # member averages command next (queries are in mySQL)
    # same timeframes, use same code structure
    # average tickets closed, average ticket replies, average ticket chats
    # SAME FORMAT, just averages now

    @commands.hybrid_command(name="mod_averages", description="Display moderator's ticketing averages over different time windows")
    @checks.has_access()
    @app_commands.describe(member="Selected member")
    async def mod_averages(self, ctx, member: discord.Member):
        pass



        # CSVs
        # essentially using the same queries, but just outputting the data (no formatting)
        # gives the option to output one person's data, or everyone's data, and then select the timeframe
        # might use the same query gen commands, not sure


    # close metric --> the % of discussion and ticket messages sent to the user in a ticket that this person also closed
    # helps identify how much of the work they're doing in the tickets they close
    # will be averaged for timeframes



    # CHARTS
    # Server stats --> num tickets opened / closed could be graphs, select timeframe

    # Member stats --> num tickets closed (one mod team in one server), select timeframe


async def setup(bot):
    await bot.add_cog(Stats(bot))