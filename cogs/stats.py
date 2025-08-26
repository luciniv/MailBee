import discord
from discord.ext import commands
from discord import app_commands
from discord.ext.commands import Greedy
from datetime import datetime, timezone, date
from typing import List
from classes.error_handler import *
from classes.paginator import Paginator, build_subsections
from classes.embeds import *
from utils import checks, queries, csv_write
from utils.logger import *


# Populate stats embed with fields from query data
def fill_embed(statsEmbed: discord.Embed, 
               data: List[int], 
               index: int, 
               rows: List[str], 
               columns: List[str]):
    for row in rows:
        count = 0
        fields = queries.generate_fields(data, index, columns) 
        
        statsEmbed.add_field(name=row, value="", inline=False)

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


    @commands.hybrid_command(name="hourly_data", description="View certain data types per hour from a selected day")
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(type="Select a data type to display hourly")
    @app_commands.choices(type=[
        app_commands.Choice(name="Tickets opened & closed", value="open")])
    @app_commands.describe(time_zone="Select a timezone (Default is UTC)")
    @app_commands.choices(time_zone=[
        app_commands.Choice(name="UTC", value="UTC"),
        app_commands.Choice(name="EST", value="EST"),
        app_commands.Choice(name="PST", value="PST")])
    @app_commands.describe(day="Input a number for the day (1-31)")
    @app_commands.describe(month="Input a number for the month (1-12)")
    @app_commands.describe(year="Input a number for the year (2024-2025)")
    @app_commands.describe(all_servers="Display data for all servers? (False by default)")
    async def hourly_data(self, ctx, 
                          type: discord.app_commands.Choice[str], 
                          time_zone: discord.app_commands.Choice[str],
                          day: int,
                          month: int,
                          year: int, 
                          all_servers: bool = False):
        try:
            # Allows command to take longer than 3 seconds
            await ctx.defer()
            await self.bot.data_manager.flush_messages()
            
            count = 0
            date_list = []

            type_name = type.name
            type_value = type.value
            time_value = time_zone.value
            guild = ctx.guild
            guildID = guild.id
            bot_user = self.bot.user

            servers = ""
            if all_servers:
                servers = " for all servers"
                guildID = 0

            # Catch parsing errors (aka invalid input)
            parsed_date = date(year, month, day)
            if parsed_date:
                date_list = [year, month, day]

            statsEmbed = Embeds(self.bot, title=f"{time_value} Hourly Data: {day}-{month}-{year}", 
                                description=f"{type_name}{servers}\r{'⎯' * 30}")
            statsEmbed.set_author(name=guild.name, icon_url=guild.icon.url)

            query = queries.hourly_queries(type_value, guildID, date_list, time_value)
            result = await self.bot.data_manager.execute_query(query)

            if result is not None: # Go ahead to build embed
                if len(result) == 0:
                    statsEmbed.add_field(name="No data found", value="", inline=False)
                    await ctx.send(embed=statsEmbed)
                    return

                else:
                    while (count < 24):
                        loop = 0
                        content = ""
                        # Build fields with 8 hours each
                        while (loop < 8): 
                            data = [0,0]
                            for row in result:
                                if (row[0] == count):
                                    data = [row[1], row[2]]

                            if (type_value == "open"):
                                content += f"**{count}:00**\nOpened: **{data[0]}**\nClosed: **{data[1]}**\n\n"

                            loop += 1
                            count += 1

                        statsEmbed.add_field(name="", value=content, inline=True) 

                        # elif (type_value == "duration"):
                        #     statsEmbed.add_field(name="", value=f"{count + 1}) **{(self.bot.get_guild(row[0])).name}**"
                        #                         f" - **{queries.format_time(row[1])}**", inline=False)

            await ctx.send(embed=statsEmbed)

        except ValueError as e:
            logger.exception(e)
            raise BotError(f"Input value error for date: {e}")
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"/hourly_data sent an error: {e}")


    # Creates leaderboards for the selected data type
    @app_commands.command(name="leaderboard", description="View certain data types as a leaderboard")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(type="Select a data type to create a leaderboard for")
    @app_commands.choices(type=[
        app_commands.Choice(name="Current tickets open (server ranking)", value="open"),
        app_commands.Choice(name="Average ticket duration (server ranking)", value="duration"),
        app_commands.Choice(name="Average first response time (server ranking)", value="response"),
        app_commands.Choice(name="Tickets closed (moderator ranking)", value="closed"),
        app_commands.Choice(name="Tickets messages sent (moderator ranking)", value="sent")
        ])
    @app_commands.describe(timeframe="Select a timeframe for the output data")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Past Hour", value="1 HOUR"),
        app_commands.Choice(name="Past Day", value="1 DAY"),
        app_commands.Choice(name="Past Week", value="1 WEEK"),
        app_commands.Choice(name="Past Month", value="1 MONTH"),
        app_commands.Choice(name="All Time", value="TOTAL")])
    async def leaderboard(self, interaction, 
                          type: discord.app_commands.Choice[str], 
                          timeframe: discord.app_commands.Choice[str]):
        try:
            # Allows command to take longer than 3 seconds
            await interaction.response.defer()
            await self.bot.data_manager.flush_messages()

            pages = []
            count = 0
            limit = 0

            type_name = type.name
            type_value = type.value
            time_name = timeframe.name
            time_value = timeframe.value
            guild = interaction.guild
            guildID = guild.id

            statsEmbed = discord.Embed(title=f"Leaderboard {time_name}", 
                                    description=f"{type_name}", 
                                    color=discord.Color.green())
            statsEmbed.set_author(name=guild.name, icon_url=guild.icon.url)
            statsEmbed.set_footer(text="")

            query = queries.leaderboard_queries(type_value, guildID, time_value)
            result = await self.bot.data_manager.execute_query(query)
            
            if result is not None: # Go ahead to build embed
                if len(result) == 0:
                    statsEmbed.add_field(name="No data found", value="", inline=False)
                    await interaction.followup.send(embed=statsEmbed)
                    return

                else:
                    final_result = result
                    # Clean out servers this bot isn't in FIXME not a huge fan of this setup
                    if type_value in ("open", "duration", "response"):
                        final_result = []
                        for entry in result:
                            if self.bot.get_guild(entry[0]) is not None:
                                final_result.append(entry)
                    
                    page_counts = build_subsections(len(final_result)) 
                    for page_count in page_counts: 
                        limit += page_count 
                        if count != 0:
                            statsEmbed = discord.Embed(title=f"Leaderboard {time_name}", 
                                    description=f"{type_name}", 
                                    color=discord.Color.green())
                            statsEmbed.set_author(name=guild.name, icon_url=guild.icon.url)
                            statsEmbed.set_footer(text="")

                        while (count < limit): 
                            row = final_result[count] 
                            
                            if (type_value == "open"):
                                if not (self.bot.get_guild(row[0]) is None):
                                    statsEmbed.add_field(name="", value=f"{count + 1}) **{(self.bot.get_guild(row[0])).name}**"
                                                        f" - **{row[1]}** ticket(s)", inline=False)

                            elif (type_value == "duration"):
                                if not (self.bot.get_guild(row[0]) is None):
                                    statsEmbed.add_field(name="", value=f"{count + 1}) **{(self.bot.get_guild(row[0])).name}**"
                                                        f" - **{queries.format_time(row[1])}**", inline=False)

                            elif (type_value == "response"):
                                if not (self.bot.get_guild(row[0]) is None):
                                    statsEmbed.add_field(name="", value=f"{count + 1}) **{(self.bot.get_guild(row[0])).name}**"
                                                        f" - **{queries.format_time(row[1])}**", inline=False)

                            elif (type_value == "closed"):
                                statsEmbed.add_field(name="", value=f"{count + 1}) <@{row[0]}> - **{row[1]}** ticket(s)", inline=False)

                            elif (type_value == "sent"):
                                statsEmbed.add_field(name="", value=f"{count + 1}) <@{row[0]}> - **{row[1]}** message(s)", inline=False)
                            count += 1 
                        pages.append(statsEmbed) 

            for page in range(len(pages)):
                pages[page].set_footer(text=f"Use the buttons below to navigate (Page {page + 1}/{len(pages)})")

            # Create an instance of the pagination view
            view = Paginator(pages)
            view.message = await interaction.followup.send(embed=pages[0], view=view)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"/leaderboard sent an error: {e}")
  
    
    @app_commands.command(name="server_stats", description="Display this server's statistics,"
                            " includes ticket counts and response averages")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(timeframe="Select a timeframe for the output data")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Past Hour", value="1 HOUR"),
        app_commands.Choice(name="Past Day", value="1 DAY"),
        app_commands.Choice(name="Past Week", value="1 WEEK"),
        app_commands.Choice(name="Past Month", value="1 MONTH"),
        app_commands.Choice(name="All Time", value="TOTAL"),
        app_commands.Choice(name="All of the above", value="ALL")])
    async def server_stats(self, interaction, timeframe: discord.app_commands.Choice[str]):
        try:
            # Allows command to take longer than 3 seconds
            await interaction.response.defer()
            await self.bot.data_manager.flush_messages()

            time_value = timeframe.value
            time_name = timeframe.name
            guild = interaction.guild
            guildID = guild.id

            intervals = self.intervals
            rows = self.rows
            columns = ["⏱️ Average Ticket Duration", 
                       "⭐️ Average First Response Time", 
                       "💬 Average Messages Per Ticket Resolved"]

            if (time_value != "ALL"):
                intervals = [f"{time_value}"]
                rows = [f"{time_name}"]

            statsEmbed = discord.Embed(title=f"Server Statistics", 
                                description=f"[Selected server's data / All server data]",
                                color=discord.Color.green())
            statsEmbed.set_author(name=guild.name, icon_url=guild.icon.url)

            query = queries.server_stats(guildID, intervals)
            result = await self.bot.data_manager.execute_query(query)

            if result is not None: # Go ahead to build embed
                index = 0
                data = result[0]
                statsEmbed.add_field(name=f"Current Data", value="", inline=False)
                statsEmbed.add_field(name="📬 Tickets Open", value=queries.format_data(data, index, None), inline=True)
                index += 2
                statsEmbed.add_field(name="📮 Total Tickets", value=queries.format_data(data, index, None), inline=True)
                index += 2
                fill_embed(statsEmbed, data, index, rows, columns)
                
            else:
                statsEmbed.add_field(name="No data found", value="", inline=False)
            await interaction.followup.send(embed=statsEmbed)
            
        except Exception as e:
            raise BotError(f"/server_stats sent an error: {e}")


    @app_commands.command(name="mod_activity", description="Display a moderator's ticketing activity" 
                             " over the past X amount of time")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(member="Selected moderator")
    @app_commands.describe(timeframe="Select a timeframe for the output data")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Past Hour", value="1 HOUR"),
        app_commands.Choice(name="Past Day", value="1 DAY"),
        app_commands.Choice(name="Past Week", value="1 WEEK"),
        app_commands.Choice(name="Past Month", value="1 MONTH"),
        app_commands.Choice(name="All Time", value="TOTAL"),
        app_commands.Choice(name="All of the above", value="ALL")])
    async def mod_activity(self, interaction, member: discord.Member, timeframe: discord.app_commands.Choice[str]):
        try:
            # Allows command to take longer than 3 seconds
            await interaction.response.defer()
            await self.bot.data_manager.flush_messages()

            time_value = timeframe.value
            time_name = timeframe.name
            guildID = interaction.guild.id
            closeByID = member.id

            intervals = self.intervals
            rows = self.rows
            columns = ["✅ Tickets Closed", 
                       "📤 Ticket Replies", 
                       "💬 Ticket Chats"]

            if (time_value != "ALL"):
                intervals = [f"{time_value}"]
                rows = [f"{time_name}"]

            statsEmbed = discord.Embed(title=f"Moderator Activity", 
                                description=f"[Selected mod's data / All mods in this server's data]",
                                color=discord.Color.green())
            statsEmbed.set_author(name=f"{member.name} | {member.id}", icon_url=member.display_avatar.url)
            
            query = queries.mod_activity(guildID, closeByID, intervals)
            result = await self.bot.data_manager.execute_query(query)

            if result is not None: # Go ahead to build embed
                index = 0
                data = result[0]
              
                fill_embed(statsEmbed, data, index, rows, columns)

            else:
                statsEmbed.add_field(name="No data found", value="", inline=False)
            await interaction.followup.send(embed=statsEmbed)

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
    

    @commands.hybrid_command(name="export_week", description="Output a CSV file of one week's data")
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(year="Select the year")
    @app_commands.choices(year=[
        app_commands.Choice(name="2024", value="2024"),
        app_commands.Choice(name="2025", value="2025")])
    @app_commands.describe(week="Enter a week number (ISO 8601)")
    async def export_week(self, ctx, year: discord.app_commands.Choice[str], week: int):
        try:
            # Allows command to take longer than 3 seconds
            await ctx.defer()
            await self.bot.data_manager.flush_messages()

            weekISO = ""
            guildIDs = []
            file = None
            
            if (week < 1 or week > 53):
                errorEmbed = discord.Embed(title=f"", 
                                    description="❌ Week number must be in the range 1-53", 
                                    color=0xFF0000)

                await ctx.send(embed=errorEmbed, ephemeral=True)
                return
            
            if (week < 10):
                weekISO = f"{year.value}0{week}"
            else:
                weekISO = f"{year.value}{week}"

            for guild in self.bot.guilds:
                if (guild.id != 12345):
                    guildIDs.append(guild.id)

            statsEmbed = Embeds(self.bot, title=f"Weekly Statistics Export", 
                                description=f"Download the attached CSV file to view data")
            statsEmbed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)
            

            type_numbers = [int(num) for num, name in self.bot.data_manager.types]
            result_list = []

            query_list = queries.week_CSV(guildIDs, weekISO, type_numbers)

            for query in query_list:
                result = await self.bot.data_manager.execute_query(query)
                if result is not None:
                    result_list.append(result[0])

            header = ["Server ID", 
                    "Server Name",
                    "Total Tickets Open",
                    "Total Tickets Closed",
                    "Num Tickets Opened This Week",
                    "Num Tickets Still Open From This Week",
                    "Num Tickets Closed From This Week",
                    "Total Tickets Closed This Week",
                    "Day Most Tickets Opened",
                    "Day Most Tickets Closed",
                    "Average Ticket Duration",
                    "Average First Response Time",
                    "Average Messages Per Ticket Resolved",
                    "Value: Average Ticket Robux", 
                    "Value: Average Ticket Hours", 
                    "Activity: Daily Time Most Tickets Opened", 
                    "Activity: Daily Time Most Tickets Closed",
                    "Activity: Daily Time Most Mod Activity",
                    "Activity: Daily Time Least Mod Activity",
                    "Mod: Closed The Most Tickets", 
                    "Mod: Sent The Most Replies",
                    "Mod: Sent The Most Discussions",
                    "Mod: Num Mods Answering Tickets"]

            type_names = [name for num, name in self.bot.data_manager.types]
            type_header = [
                    metric.format(name)
                    for name in type_names  
                    for metric in [ 
                        "Type: {} - Num Tickets Opened This Week",
                        "Type: {} - Average Ticket Duration",
                        "Type: {} - Average First Response Time"
                        ]
                    ]

            # Link static headings to dynamic type headings
            header.extend(type_header)

            # Create CSV file from data
            if (len(result_list) != 0):
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
            raise BotError(f"/export_week sent an error: {e}")


    @commands.hybrid_command(name="export_week_v2", description="Output a CSV file of one week's data")
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(year="Select the year")
    @app_commands.choices(year=[
        app_commands.Choice(name="2025", value="2025")])
    @app_commands.describe(week="Enter a week number (ISO 8601)")
    @app_commands.describe(guild_id="The ID of the guild to export data for")
    async def export_week_v2(self, ctx, year: discord.app_commands.Choice[str], week: int, guild_id: str):
        try:
            await ctx.defer()
            await self.bot.data_manager.flush_messages()

            if week < 1 or week > 53:
                errorEmbed = discord.Embed(
                    description="❌ Week number must be in the range 1–53",
                    color=discord.Color.red()
                )
                await ctx.send(embed=errorEmbed, ephemeral=True)
                return

            weekISO = f"{year.value}{week:02d}"
            # guild = self.bot.get_guild(guild_id)
            # if guild is None:
            #     guild = await self.bot.fetch_guild(guild_id)

            # if guild is None:
            #     await ctx.send(
            #         embed=discord.Embed(
            #             description=f"❌ Guild with ID `{guild_id}` not found in bot's cache.",
            #             color=discord.Color.red()
            #         ),
            #         ephemeral=True
            #     )
            #     return

            statsEmbed = Embeds(
                self.bot,
                title="Weekly Statistics Export",
                description="Download the attached CSV file to view data"
            )
            # statsEmbed.set_author(name=guild.name, icon_url=guild.icon.url)
            result_list = []

            # Generate and execute query
            query, headers = await queries.week_CSV_v2(self, guild_id, int(weekISO))
            result = await self.bot.data_manager.execute_query(query)

            file = None
            if result:
                row = [guild_id] + list(result[0])
                result_list.append(row)
                file = csv_write.make_file(headers, result_list)
            else:
                statsEmbed.add_field(name="No data found", value="", inline=False)

            await ctx.send(embed=statsEmbed, file=file)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/export_week_v2 sent an error: {e}")


    @commands.hybrid_command(name="export_server_stats", description="Output a CSV file of every server's statistics,"
                            " includes ticket counts and response averages")
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(timeframe="Select a timeframe for the output data")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Past Hour", value="1 HOUR"),
        app_commands.Choice(name="Past Day", value="1 DAY"),
        app_commands.Choice(name="Past Week", value="1 WEEK"),
        app_commands.Choice(name="Past Month", value="1 MONTH"),
        app_commands.Choice(name="All Time", value="TOTAL"),
        app_commands.Choice(name="All of the above", value="ALL")])
    async def export_server_stats(self, ctx, timeframe: discord.app_commands.Choice[str]):
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

            statsEmbed = Embeds(self.bot, title=f"Server Statistics Export", 
                                description=f"Download the attached CSV file to view data")
            statsEmbed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)
            
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
            raise BotError(f"/export_server_stats sent an error: {e}")


    @commands.hybrid_command(name="export_mod_activity", description="Output a CSV file of this server's moderators'"
                             " ticketing activity over the past X amount of time")
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(timeframe="Select a timeframe for the output data")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Past Hour", value="1 HOUR"),
        app_commands.Choice(name="Past Day", value="1 DAY"),
        app_commands.Choice(name="Past Week", value="1 WEEK"),
        app_commands.Choice(name="Past Month", value="1 MONTH"),
        app_commands.Choice(name="All Time", value="TOTAL"),
        app_commands.Choice(name="All of the above", value="ALL")])
    async def export_mod_activity(self, ctx, timeframe: discord.app_commands.Choice[str]):
        try:
            # Allows command to take longer than 3 seconds
            await ctx.defer()
            await self.bot.data_manager.flush_messages()

            modIDs = []
            time_value = timeframe.value
            time_name = timeframe.name
            guild = ctx.guild
            guildID = guild.id
            bot_user = self.bot.user
            file = None

            intervals = self.intervals
            rows = self.rows
            columns = ["Tickets Closed", "Ticket Replies", "Ticket Chats"]

            if (time_value != "ALL"):
                intervals = [f"{time_value}"]
                rows = [f"{time_name}"]

            modIDs_query = queries.get_mod_ids(guildID, intervals)
            modIDs_result = await self.bot.data_manager.execute_query(modIDs_query)
            if len(modIDs_result) != 0:
                for id in modIDs_result:
                    modIDs.append(id[0])

            statsEmbed = Embeds(self.bot, title=f"Moderator Activity Export", 
                                description=f"Download the attached CSV file to view data")
            statsEmbed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)
            
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
                    mod = await guild.fetch_member(modID)
                    data = [guildID, modID, mod.name]
                    write_list.append((*data, *result))

                file = csv_write.make_file(header, write_list)
              
            else:
                statsEmbed.add_field(name="No data found", value="", inline=False)
            await ctx.send(embed=statsEmbed, file=file)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/export_mod_activity sent an error: {e}")

    # OTHER STATS
    # close metric --> the % of discussion and ticket messages sent to the user in a ticket that this person also closed
    # helps identify how much of the work they're doing in the tickets they close
    # will be averaged for timeframes

    # CHARTS
    # Server stats --> num tickets opened / closed could be graphs, select timeframe
    # Member stats --> num tickets closed (one mod team in one server), select timeframe

async def setup(bot):
    await bot.add_cog(Stats(bot))