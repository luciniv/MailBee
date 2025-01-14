import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import List
from classes.error_handler import *
from utils import emojis, checks, queries
from utils.logger import *


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot 


    # Server stats
    # Number of tickets opened (in timespans)
    # Number of tickets closed (in timespans)
    # Average ticket duration (in timespans)
    # Average first response time (in timespans)
    # Average time for moderator reply to user message (in timespans)



    # Ticket content breakdown
    # Average number of messages sent to user to esolve a ticket (again)
    # Average number of discussion messages


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


    @commands.hybrid_command(name="member_stats", description="Display statistics for a certain member")
    @checks.has_access()
    @app_commands.describe(member="Selected member")
    async def member_stats(self, ctx, member: discord.Member):
        try:
            
            guildID = ctx.guild.id
            closeByID = member.id
            rows = ["Past Day", "Past Week", "Past Month", "All Time"]
            columns = ["✅ Tickets Closed", "📤 Ticket Replies", "💬 Ticket Chats"]
            bot_user = self.bot.user
            time_now = datetime.now()
            format_time = time_now.strftime("Today at %-I:%M %p")

            statsEmbed = discord.Embed(title=f"Moderator Statistics {emojis.mantis}", 
                                    description=f"Timeframe data for {member.name} from {ctx.guild.name}"
                                                "\n\nRun `/mod_averages` to view average data"
                                                "\nRun `/stats_dictionary` for information on data field names and calculations (WIP)", 
                                    color=0x3ad407)
            statsEmbed.set_author(name=member.name, icon_url=member.avatar.url)
            statsEmbed.set_footer(text=f"Mantid · {format_time}", icon_url=bot_user.avatar.url)
            
            query = queries.member_stats(guildID, closeByID)
            result = await self.bot.data_manager.execute_query(query)

            if result is not None:
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




    # close metric --> the % of discussion and ticket messages sent to the user in a ticket that this person also closed
    # helps identify how much of the work they're doing in the tickets they close
    # will be averaged for timeframes





    # CHARTS
    # Server stats --> num tickets opened / closed could be graphs, select timeframe

    # Member stats --> num tickets closed (one mod team in one server), select timeframe


async def setup(bot):
    await bot.add_cog(Stats(bot))