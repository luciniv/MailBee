import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
from datetime import datetime
from typing import List
from classes.error_handler import *
from utils import emojis, checks, queries
from utils.logger import *


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot 

    def build_stat_embed():
        pass
    # tackle either this or member averages first

    # Server stats
    # Current total open and total overall (opened or closed) --> doenst work for timeframes

    # Number of tickets opened (in timespans) --> avg compatible
    # Number of tickets closed (in timespans) --> avg compatible

    # Average ticket duration (in timespans)                            --> ONLY averages
    # Average first response time (in timespans)                        --> ONLY averages
    # Average time for moderator reply to user message (in timespans)   --> ONLY averages



    # Ticket content breakdown
    # Average number of messages sent to user to resolve a ticket (again)
    # Average number of discussion messages, sent, received, their ratio idk


    @commands.hybrid_command(name="server_stats", description="Display this server's statistics")
    @checks.has_access()
    async def server_stats(self, ctx):
        guildID = ctx.guild.id
        editEmbed = discord.Embed(title=f"Edit Results {emojis.mantis}", 
                                description="", 
                                color=0x3ad407)
        

    # Print user specific data
    # Tickets closed (compare to total) DONE
    # Ticket messages sent to users (compare to total) DONE
    # Ticket discussion messages (compare to total) DONE

    # Daily, weekly, monthly, all time
    # All total comparisons include percents

    # Could do a bar chart as well, send charts SEPARATE!! so the full image is displayed :)

    # Button view logic for displaying data? gives the option to select different timeframes
    # Click button to say yes to outputting thing, embed updates
    # Click again to say no to outputting thing, embed updates

    @commands.hybrid_command(name="mod_data", description="Display a moderator's ticketing data over the past X amount of time")
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
    async def mod_data(self, ctx, member: discord.Member, timeframe: discord.app_commands.Choice[str]):
        try:
            # Allows command to take longer than 3 seconds
            await ctx.defer()

            choice = timeframe.value
            name = timeframe.name
            guildID = ctx.guild.id
            closeByID = member.id
            rows = ["Past Hour", "Past Day", "Past Week", "Past Month", "All Time"]
            columns = ["✅ Tickets Closed", "📤 Ticket Replies", "💬 Ticket Chats"]
            intervals = ["1 HOUR", "1 DAY", "7 DAY", "1 MONTH", "TOTAL"]

            if (choice != "ALL"):
                intervals = [f"{choice}"]
                rows = [f"{name}"]

            bot_user = self.bot.user
            time_now = datetime.now()
            format_time = time_now.strftime("Today at %-I:%M %p")

            statsEmbed = discord.Embed(title=f"Moderator Data {emojis.mantis}", 
                                    description=f"Data is formatted as **moderator's data** / **total data** - percent ratio", 
                                    color=0x3ad407)
            statsEmbed.set_author(name=member.name, icon_url=member.avatar.url)
            statsEmbed.set_footer(text=f"Mantid · {format_time}", icon_url=bot_user.avatar.url)
            
            query = queries.mod_data(guildID, closeByID, intervals)
            result = await self.bot.data_manager.execute_query(query)

            if result is not None: # go ahead to build embed
                index = 0
                data = result[0]

                for row in rows:
                    fields = queries.generate_fields(data, index) 
                    
                    # First field is a spacer, second is a heading
                    statsEmbed.add_field(name="", value="", inline=False)
                    statsEmbed.add_field(name=f"{row}", value="", inline=False)

                    # Outputs the three fields from generate_fields
                    for col, field in zip(columns, fields):
                        statsEmbed.add_field(name=col, value=field, inline=True)

                    index += 6
            else:
                statsEmbed.add_field(name="No data found", value="", inline=False)
                
            await ctx.send(embed=statsEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/member_stats sent an error: {e}")
            
            
        
    # member averages command next (queries are in mySQL)
    # same timeframes, use same code structure
    # average tickets closed, average ticket replies, average ticket chats
    # SAME FORMAT, just averages now

    @commands.hybrid_command(name="mod_averages", description="Display moderator's ticketing averages over different time windows")
    @checks.has_access()
    @app_commands.describe(member="Selected member")
    async def mod_averages(self, ctx, member: discord.Member):
        pass

    # close metric --> the % of discussion and ticket messages sent to the user in a ticket that this person also closed
    # helps identify how much of the work they're doing in the tickets they close
    # will be averaged for timeframes





    # CHARTS
    # Server stats --> num tickets opened / closed could be graphs, select timeframe

    # Member stats --> num tickets closed (one mod team in one server), select timeframe


async def setup(bot):
    await bot.add_cog(Stats(bot))