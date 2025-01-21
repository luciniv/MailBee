import discord
from discord.ext import commands
from discord import app_commands
from discord.ext.commands import Greedy
from datetime import datetime
from typing import List
from classes.error_handler import *
from classes.paginator import *
from utils import emojis, checks, queries, csv_write
from utils.logger import *


# Subsects a number into a list of numbers that cap at max_size (for pagination)
def build_subsections(size: int, max_size = 6) -> List[int]:
    if size <= max_size:
        return [size]
    
    subsections = [max_size] * (size // max_size)

    remainder = size % max_size
    if (remainder > 0):
        subsections.append(remainder)

    return subsections


# Populate stats embed with fields from query data
def fill_embed(statsEmbed: discord.Embed, 
               data: List[int], 
               index: int, 
               rows: List[str], 
               columns: List[str]):
    for row in rows:
        count = 0
        fields = queries.generate_fields(data, index, columns) 
        
        statsEmbed.add_field(name=f"", value=f"**{'⎯' * 30}\r{row}**", inline=False)

        # Outputs the three fields from generate_fields
        for col, field in zip(columns, fields):
            if count == 2:
                field += f"\n** **"

            statsEmbed.add_field(name=col, value=field, inline=True)
            count += 1
        # Works for single target commands, needs changed for mutli-target
        index += 6
    return statsEmbed


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot 
        self.rows = ["Past Hour", "Past Day", "Past Week", "Past Month", "All Time"]
        self.intervals = ["1 HOUR", "1 DAY", "1 WEEK", "1 MONTH", "TOTAL"]


    # Creates leaderboards for the selected data type
    @commands.hybrid_command(name="leaderboard", description="View certain data types as a leaderboard")
    @checks.has_access()
    @app_commands.describe(type="Select a data type to create a leaderboard for")
    @app_commands.choices(type=[
        app_commands.Choice(name="Current tickets open (server ranking)", value="open"),
        app_commands.Choice(name="Average ticket duration (server ranking)", value="duration"),
        app_commands.Choice(name="Average first response time (server ranking)", value="response"),
        app_commands.Choice(name="Tickets closed by (moderator ranking)", value="closed")])
    @app_commands.describe(timeframe="Select a timeframe for the output data")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Past Hour", value="1 HOUR"),
        app_commands.Choice(name="Past Day", value="1 DAY"),
        app_commands.Choice(name="Past Week", value="1 WEEK"),
        app_commands.Choice(name="Past Month", value="1 MONTH"),
        app_commands.Choice(name="All Time", value="TOTAL")])
    @app_commands.describe(server_id="Server ID to display data from (defaults to current server)")
    async def leaderboard(self, ctx, 
                          type: discord.app_commands.Choice[str], 
                          timeframe: discord.app_commands.Choice[str],  
                          server_id: int = None):
        try:
            # Allows command to take longer than 3 seconds
            await ctx.defer()
            await self.bot.data_manager.flush_messages()

            pages = []
            count = 0
            limit = 0

            type_name = type.name
            type_value = type.value
            time_name = timeframe.name
            time_value = timeframe.value
            guild = ctx.guild
            guildID = guild.id

            if server_id is not None:
                guildID = server_id

            statsEmbed = discord.Embed(title=f"Leaderboard {time_name} {emojis.mantis}", 
                                    description=f"{type_name}\r{'⎯' * 18}", 
                                    color=0x3ad407)
            statsEmbed.set_author(name=guild.name, icon_url=guild.icon.url)
            statsEmbed.set_footer(text=f"")

            query = queries.leaderboard_queries(type_value, guildID, time_value)
            result = await self.bot.data_manager.execute_query(query)

            if result is not None: # Go ahead to build embed
                if len(result) == 0:
                    statsEmbed.add_field(name="No data found", value="", inline=False)
                    await ctx.send(embed=statsEmbed)
                    return

                else:
                    page_counts = build_subsections(len(result)) 
                    for page_count in page_counts: 
                        limit += page_count 
                        if count != 0:
                            statsEmbed = discord.Embed(title=f"Leaderboard {time_name} {emojis.mantis}", 
                                    description=type_name, 
                                    color=0x3ad407)
                            statsEmbed.set_author(name=guild.name, icon_url=guild.icon.url)
                            statsEmbed.set_footer(text=f"")

                        while (count < limit): 
                            row = result[count] 
                            if (type_value == "open"):
                                statsEmbed.add_field(name="", value=f"{count + 1}) **{(self.bot.get_guild(row[0])).name}**"
                                                    f" - **{row[1]}** ticket(s)", inline=False) # added here

                            elif (type_value == "duration"):
                                statsEmbed.add_field(name="", value=f"{count + 1}) **{(self.bot.get_guild(row[0])).name}**"
                                                    f" - **{queries.format_time(row[1])}**", inline=False)

                            elif (type_value == "response"):
                                statsEmbed.add_field(name="", value=f"{count + 1}) **{(self.bot.get_guild(row[0])).name}**"
                                                    f" - **{queries.format_time(row[1])}**", inline=False)

                            elif (type_value == "closed"):
                                statsEmbed.add_field(name="", value=f"{count + 1}) <@{row[0]}> - **{row[1]}** ticket(s)", inline=False)
                            count += 1 
                    pages.append(statsEmbed) 

            for page in range(len(pages)):
                pages[page].set_footer(text=f"Use the buttons below to navigate (Page {page + 1}/{len(pages)})")

            # Create an instance of the pagination view
            view = Paginator(pages)
            view.message = await ctx.send(embed=pages[0], view=view)
            
        except Exception as e:
            raise BotError(f"/leaderboard sent an error: {e}")
  
    
    @commands.hybrid_command(name="server_stats", description="Display this server's statistics,"
                            " includes ticket counts and response averages")
    @checks.has_access()
    @app_commands.describe(timeframe="Select a timeframe for the output data")
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
            await self.bot.data_manager.flush_messages()

            time_value = timeframe.value
            time_name = timeframe.name
            guild = ctx.guild
            guildID = guild.id

            intervals = self.intervals
            rows = self.rows
            columns = ["⏱️ Average Ticket Duration", 
                       "⭐️ Average First Response Time", 
                       "💬 Average Messages Per Ticket Resolved"]

            if (time_value != "ALL"):
                intervals = [f"{time_value}"]
                rows = [f"{time_name}"]

            bot_user = self.bot.user
            time_now = datetime.now()
            format_time = time_now.strftime("Today at %-I:%M %p")

            statsEmbed = discord.Embed(title=f"Server Statistics {emojis.mantis}", 
                                    description=f"(selected server's data / all server data)", 
                                    color=0x3ad407)
            statsEmbed.set_author(name=guild.name, icon_url=guild.icon.url)
            statsEmbed.set_footer(text=f"Mantid · {format_time}", icon_url=bot_user.avatar.url)

            query = queries.server_stats(guildID, intervals)
            result = await self.bot.data_manager.execute_query(query)

            if result is not None: # Go ahead to build embed
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
            raise BotError(f"/server_stats sent an error: {e}")


    @commands.hybrid_command(name="mod_activity", description="Display a moderator's ticketing activity" 
                             " over the past X amount of time")
    @checks.has_access()
    @app_commands.describe(member="Selected moderator")
    @app_commands.describe(timeframe="Select a timeframe for the output data")
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
            await self.bot.data_manager.flush_messages()

            time_value = timeframe.value
            time_name = timeframe.name
            guildID = ctx.guild.id
            closeByID = member.id

            intervals = self.intervals
            rows = self.rows
            columns = ["✅ Tickets Closed", 
                       "📤 Ticket Replies", 
                       "💬 Ticket Chats"]

            if (time_value != "ALL"):
                intervals = [f"{time_value}"]
                rows = [f"{time_name}"]

            bot_user = self.bot.user
            time_now = datetime.now()
            format_time = time_now.strftime("Today at %-I:%M %p")

            statsEmbed = discord.Embed(title=f"Moderator Activity {emojis.mantis}", 
                                    description=f"(selected mod's data / all mods in this server's data)", 
                                    color=0x3ad407)
            statsEmbed.set_author(name=member.name, icon_url=member.avatar.url)
            statsEmbed.set_footer(text=f"Mantid · {format_time}", icon_url=bot_user.avatar.url)
            
            query = queries.mod_activity(guildID, closeByID, intervals)
            result = await self.bot.data_manager.execute_query(query)

            if result is not None: # Go ahead to build embed
                index = 0
                data = result[0]
              
                fill_embed(statsEmbed, data, index, rows, columns)

            else:
                statsEmbed.add_field(name="No data found", value="", inline=False)
                
            await ctx.send(embed=statsEmbed)

        except Exception as e:
            raise BotError(f"/mod_activity sent an error: {e}")
            

    # member averages command next (queries are in mySQL)
    # same timeframes, use same code structure
    # average tickets closed, average ticket replies, average ticket chats
    # SAME FORMAT, just averages now

    # @commands.hybrid_command(name="mod_averages", description="Display moderator's ticketing averages"
    #                          " over different time windows")
    # @checks.has_access()
    # @app_commands.describe(member="Selected member")
    # async def mod_averages(self, ctx, member: discord.Member):
    #     pass


    # CSVs
    # essentially using the same queries, but just outputting the data (no formatting)
    # gives the option to output one person's data, or everyone's data, and then select the timeframe
    # might use the same query gen commands, not sure

    @commands.hybrid_command(name="csv_server_stats", description="Output a CSV file of every server's statistics,"
                            " includes ticket counts and response averages")
    @checks.has_access()
    @app_commands.describe(timeframe="Select a timeframe for the output data")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Past Hour", value="1 HOUR"),
        app_commands.Choice(name="Past Day", value="1 DAY"),
        app_commands.Choice(name="Past Week", value="1 WEEK"),
        app_commands.Choice(name="Past Month", value="1 MONTH"),
        app_commands.Choice(name="All Time", value="TOTAL"),
        app_commands.Choice(name="All of the above", value="ALL")])
    async def csv_server_stats(self, ctx, timeframe: discord.app_commands.Choice[str]):
        try:
            # Allows command to take longer than 3 seconds
            await ctx.defer()
            await self.bot.data_manager.flush_messages()

            guildIDs = []
            time_value = timeframe.value
            time_name = timeframe.name
            file = None

            intervals = self.intervals
            rows = self.rows
            columns = ["Average Ticket Duration", 
                       "Average First Response Time", 
                       "Average Messages Per Ticket Resolved"]

            if (time_value != "ALL"):
                intervals = [f"{time_value}"]
                rows = [f"{time_name}"]

            for guild in self.bot.guilds:
                if (guild.id != 12345):
                    guildIDs.append(guild.id)

            bot_user = self.bot.user
            time_now = datetime.now()
            format_time = time_now.strftime("Today at %-I:%M %p")

            statsEmbed = discord.Embed(title=f"Server Statistics CSV {emojis.mantis}", 
                                    description=f"Download the attatched CSV file to view data", 
                                    color=0x3ad407)
            statsEmbed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)
            statsEmbed.set_footer(text=f"Mantid · {format_time}", icon_url=bot_user.avatar.url)
            
            result_list = []
            query_list = queries.server_stats_CSV(guildIDs, intervals)

            for query in query_list:
                result = await self.bot.data_manager.execute_query(query)
                if result is not None:
                    result_list.append(result[0])

            # Create CSV file from data
            if (len(result_list) != 0):
                header = ["Server ID", "Server Name", "Open Tickets", "All Tickets"]

                for row in rows:
                    for col in columns:
                        header.append(f"{row} {col}")

                write_list = []

                for guildID, result in zip(guildIDs, result_list):
                    guild = self.bot.get_guild(guildID)
                    data = [guildID, guild.name]
                    write_list.append((*data, *result))

                file = csv_write.make_file(header, write_list)
              
            else:
                statsEmbed.add_field(name="No data found", value="", inline=False)
                
            await ctx.send(embed=statsEmbed, file=file)

        except Exception as e:
            raise BotError(f"/csv_server_stats sent an error: {e}")


    @commands.hybrid_command(name="csv_mod_activity", description="Output a CSV file of this server's moderators'"
                             " ticketing activity over the past X amount of time")
    @checks.has_access()
    @app_commands.describe(roles="Input the moderator role(s) for this server")
    @app_commands.describe(timeframe="Select a timeframe for the output data")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Past Hour", value="1 HOUR"),
        app_commands.Choice(name="Past Day", value="1 DAY"),
        app_commands.Choice(name="Past Week", value="1 WEEK"),
        app_commands.Choice(name="Past Month", value="1 MONTH"),
        app_commands.Choice(name="All Time", value="TOTAL"),
        app_commands.Choice(name="All of the above", value="ALL")])
    async def csv_mod_activity(self, ctx, roles: Greedy[discord.Role], timeframe: discord.app_commands.Choice[str]):
        try:
            # Allows command to take longer than 3 seconds
            await ctx.defer()
            await self.bot.data_manager.flush_messages()

            mod_roles = []
            modIDs = []
            time_value = timeframe.value
            time_name = timeframe.name
            guild = ctx.guild
            guildID = guild.id
            file = None

            intervals = self.intervals
            rows = self.rows
            columns = ["Tickets Closed", "Ticket Replies", "Ticket Chats"]

            if (time_value != "ALL"):
                intervals = [f"{time_value}"]
                rows = [f"{time_name}"]

            for role in roles:
                if ("mod" in role.name.casefold()):
                    mod_roles.append(role)

            for role in mod_roles:
                for member in role.members:
                    if (member.id not in modIDs):
                        modIDs.append(member.id)

            bot_user = self.bot.user
            time_now = datetime.now()
            format_time = time_now.strftime("Today at %-I:%M %p")

            statsEmbed = discord.Embed(title=f"Moderator Activity CSV {emojis.mantis}", 
                                    description=f"Download the attatched CSV file to view data", 
                                    color=0x3ad407)
            statsEmbed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)
            statsEmbed.set_footer(text=f"Mantid · {format_time}", icon_url=bot_user.avatar.url)
            
            result_list = []
            query_list = queries.mod_activity_CSV(guildID, modIDs, intervals)

            for query in query_list:
                result = await self.bot.data_manager.execute_query(query)
                if result is not None:
                    result_list.append(result[0])

            # Create CSV file from data
            if (len(result_list) != 0):
                header = ["Server ID", "Mod ID", "Mod Username"]

                for row in rows:
                    for col in columns:
                        header.append(f"{row} {col}")

                write_list = []

                for modID, result in zip(modIDs, result_list):
                    mod = guild.get_member(modID)
                    data = [guildID, modID, mod.name]
                    write_list.append((*data, *result))

                file = csv_write.make_file(header, write_list)
              
            else:
                statsEmbed.add_field(name="No data found", value="", inline=False)
                
            await ctx.send(embed=statsEmbed, file=file)

        except Exception as e:
            raise BotError(f"/csv_mod_activity sent an error: {e}")

    # OTHER STATS
    # close metric --> the % of discussion and ticket messages sent to the user in a ticket that this person also closed
    # helps identify how much of the work they're doing in the tickets they close
    # will be averaged for timeframes

    # CHARTS
    # Server stats --> num tickets opened / closed could be graphs, select timeframe
    # Member stats --> num tickets closed (one mod team in one server), select timeframe

async def setup(bot):
    await bot.add_cog(Stats(bot))