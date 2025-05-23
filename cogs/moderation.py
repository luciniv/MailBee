import discord
import datetime
import asyncio
from discord.ext import commands
from discord import app_commands
from classes.error_handler import *
from classes.paginator import Paginator, build_subsections
from classes.embeds import *
from utils import emojis, checks
from utils.logger import *


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.hybrid_command(name="ticket_history", description="View a user's ticketing history")
    @checks.is_user()
    @app_commands.describe(user="User to view history of")
    async def ticket_history(self, ctx, user: discord.Member):
        try:
            pages = []
            count = 0
            limit = 0
            
            historyEmbed = discord.Embed(title="Ticket History",
                                  description="User has not opened any tickets",
                                  color=discord.Color.green())
            if (user.avatar):
                historyEmbed.set_author(name=f"{user.name} | {user.id}", icon_url=user.avatar.url)
            else:
                historyEmbed.set_author(name=f"{user.name} | {user.id}")
            
            history = await self.bot.data_manager.get_ticket_history(ctx.guild.id, user.id)
            print("history", history)

            if history is not None:
                if len(history) == 0:
                    await ctx.send(embed=historyEmbed)
                    return
                else:
                    page_counts = build_subsections(len(history), 4)
                    print(page_counts)
                    for page_count in page_counts:
                        limit += page_count
                        historyEmbed = discord.Embed(title="Ticket History",
                                description="Tickets are displayed by most recent open date.\n"
                                "Logs may appear as `#unknown` before being accessed.",
                                color=discord.Color.green())
                        
                        if (user.avatar):
                            historyEmbed.set_author(name=f"{user.name} | {user.id}", icon_url=user.avatar.url)
                        else:
                            historyEmbed.set_author(name=f"{user.name} | {user.id}")

                        while (count < limit):
                            ticket = history[count]

                            ticketID = ticket[0]
                            logID = ticket[1]
                            date_open = ticket[2].strftime("%m/%d/%Y")
                            date_close = None
                            close = ticket[3]
                            if close is not None:
                                date_close = close.strftime("%m/%d/%Y")
                            state = (ticket[5]).upper()
                            typeName = ticket[6]

                            historyEmbed.add_field(name=f"{count + 1}) {typeName} Ticket: {state}", 
                                            value=f"`ID: {ticketID}`\n**Opened:** {date_open}\n**Closed:** {date_close}\n**Logs:** <#{logID}>\n{'⎯' * 20}", 
                                            inline=False)
                            count += 1
                        pages.append(historyEmbed)


            for page in range(len(pages)):
                pages[page].set_footer(text=f"Use the buttons below to navigate (Page {page + 1}/{len(pages)})")

            # Create an instance of the pagination view
            view = Paginator(pages)
            view.message = await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            raise BotError(f"/ticket_history sent an error: {e}")
        

    @commands.hybrid_command(name="notes_add", description="Add a note to a ticket or user")
    @checks.is_user()
    @app_commands.describe(user="User to view history of")
    async def notes_add(self, ctx, ticket: str = None, user: discord.Member = None):
        pass

    
    @commands.hybrid_command(name="notes", description="View a ticket's or user's notes")
    @checks.is_user()
    @app_commands.describe(user="User to view history of")
    async def notes(self, ctx, user: discord.Member):
        pass


    @commands.hybrid_command(name="blacklist", description="Blacklist a user from opening tickets")
    @app_commands.describe(user="User to blacklist", reason="Reason for blacklisting (required)")
    @checks.is_guild()
    @checks.is_user()
    async def blacklist(self, ctx: commands.Context, user: discord.Member, *, reason: str):
        try:
            guild = ctx.guild
            existing = await self.bot.data_manager.get_blacklist_from_db(guild.id, user.id)

            if existing:
                embed = discord.Embed(
                    description=f"❌ **{user.mention}** is already blacklisted.",
                    color=discord.Color.red()
                )
            else:
                await self.bot.data_manager.add_blacklist_to_db(guild.id, user.id, reason, ctx.author.id)
                embed = discord.Embed(
                    description=f"✅ **{user.mention}** has been blacklisted from opening tickets.\nReason: {reason}",
                    color=discord.Color.green()
                )

            await ctx.send(embed=embed)

        except Exception as e:
            logger.exception(f"blacklist error: {e}")
            raise BotError(f"/blacklist sent an error: {e}")

    # FIXME pagination
    @commands.hybrid_command(name="view_blacklist", description="View all blacklisted users in this server")
    @checks.is_guild()
    @checks.is_user()
    async def view_blacklist(self, ctx: commands.Context):
        try:
            guild = ctx.guild
            entries = await self.bot.data_manager.get_all_blacklist_from_db(guild.id)

            if not entries:
                embed = discord.Embed(
                    description="✅ No users are currently blacklisted in this server.",
                    color=discord.Color.green()
                )
            else:
                lines = []
                for row in entries:
                    user_id = int(row["userID"])
                    user = guild.get_member(user_id) or await self.bot.fetch_user(user_id)
                    lines.append(f"• {user.mention} (`{user_id}`)")

                embed = discord.Embed(
                    title=f"Blacklisted Users ({len(entries)})",
                    description="\n".join(lines),
                    color=discord.Color.orange()
                )

            await ctx.send(embed=embed)

        except Exception as e:
            logger.exception(f"view_blacklist error: {e}")
            raise BotError(f"/view_blacklist sent an error: {e}")
        

    @commands.hybrid_command(name="whitelist", description="Remove a user from the ticket blacklist")
    @app_commands.describe(user="User to remove from blacklist")
    @checks.is_guild()
    @checks.is_user()
    async def whitelist(self, ctx: commands.Context, user: discord.Member):
        try:
            guild = ctx.guild
            existing = await self.bot.data_manager.get_blacklist_from_db(guild.id, user.id)

            if not existing:
                embed = discord.Embed(
                    description=f"❌ **{user.mention}** is not blacklisted.",
                    color=discord.Color.red()
                )
            else:
                await self.bot.data_manager.delete_blacklist_from_db(guild.id, user.id)
                embed = discord.Embed(
                    description=f"✅ **{user.mention}** has been removed from the blacklist.",
                    color=discord.Color.green()
                )

            await ctx.send(embed=embed)

        except Exception as e:
            logger.exception(f"whitelist error: {e}")
            raise BotError(f"/whitelist sent an error: {e}")
        

    @commands.hybrid_command(name="verbal", description="Send a verbal warning to a user")
    @app_commands.describe(user="User to verbally warn")
    @app_commands.describe(reason="Text content of the verbal warning")
    @checks.is_guild()
    @checks.is_user()
    async def verbal(self, ctx, user: discord.Member, *, reason: str):
        try:
            guild = ctx.guild
            author = ctx.author
            sent_message = None
            dm_channel = user.dm_channel or await user.create_dm()

            verbalEmbed = discord.Embed(title="Verbal Warning",
                                        description=f"**{reason}**",
                                        color=discord.Color.blue())
            verbalEmbed.set_footer(text="This does NOT count as a moderation warning. If you have any questions, "
                               f"please reach out to us via ModMail.")
            if (guild.icon):
                verbalEmbed.set_author(name=f"{guild.name}", icon_url=guild.icon.url)
            else:
                verbalEmbed.set_author(name=f"{guild.name}")

            if dm_channel:
                try:
                    sent_message = await dm_channel.send(embed=verbalEmbed)

                except discord.Forbidden:
                    embed = discord.Embed(description="❌ Failed to DM user, they may not be accepting DMs",
                                          color=discord.Color.red())
                    await ctx.send(embed=embed)
                    return
                
                except Exception:
                    embed = discord.Embed(description="❌ Failed to DM user",
                                          color=discord.Color.red())
                    await ctx.send(embed=embed)
                    return
            else:
                embed = discord.Embed(description="❌ Could not create a DM channel with the user",
                                      color=discord.Color.red())
                await ctx.send(embed=embed)
                return
            
            await self.bot.data_manager.add_verbal(sent_message.id, guild.id, user.id, author.id, author.name, reason)
            
            successEmbed = discord.Embed(description=f"✅ **Verbally warned <@{user.id}> ({user.name})**",
                                         color=discord.Color.green())
            successEmbed.add_field(name="Reason", value=reason, inline=False)
            successEmbed.add_field(name="Verbal ID", value=f"```{sent_message.id}```", inline=False)
            await ctx.send(embed=successEmbed)

        except Exception as e:
            logger.exception(f"verbal error: {e}")
            raise BotError(f"/verbal sent an error: {e}")
        

    @commands.hybrid_command(name="verbal_edit", description="Edit a user's verbal warning")
    @app_commands.describe(verbal_id="The verbal's ID")
    @app_commands.describe(new_reason="New content of the verbal")
    @checks.is_guild()
    @checks.is_user()
    async def verbal_edit(self, ctx, verbal_id: str, *, new_reason: str):
        try:
            guild = ctx.guild
            author = ctx.author
            userID = None
            user = None

            result = await self.bot.data_manager.get_verbal(verbal_id)
            if len(result) != 0:
                userID = result[0][3]
            else:
                embed = discord.Embed(description="❌ Verbal not found, invalid ID",
                                            color=discord.Color.red())
                await ctx.send(embed=embed)
                return
            
            try:
                user = await asyncio.wait_for(guild.fetch_member(userID), timeout=1)
            except Exception:
                try:
                    user = await asyncio.wait_for(guild.fetch_member(userID), timeout=1)
                except Exception:
                    embed = discord.Embed(description="❌ User not found, if this command fails "
                                          "again the user does not exist (or Discord's API is down)",
                                            color=discord.Color.red())
                    await ctx.send(embed=embed)
                    return
        
            dm_channel = user.dm_channel or await user.create_dm()
         
            if dm_channel:
                try:
                    sent_message = await dm_channel.fetch_message(int(verbal_id))

                except discord.NotFound:
                    embed = discord.Embed(description="❌ Verbal not found, invalid user or ID",
                                            color=discord.Color.red())
                    await ctx.send(embed=embed)
                    return

                except discord.Forbidden:
                    embed = discord.Embed(description="❌ Unable to edit verbal, user may not be accepting DMs",
                                            color=discord.Color.red())
                    await ctx.send(embed=embed)
                    return

                except Exception:
                    embed = discord.Embed(description="❌ Unable to find verbal",
                                            color=discord.Color.red())
                    await ctx.send(embed=embed)
                    return

                newEmbed = sent_message.embeds[0]
                newEmbed.description = new_reason
                await sent_message.edit(embed=newEmbed)

            else:
                embed = discord.Embed(description="❌ Could not create a DM channel with the user",
                                      color=discord.Color.red())
                await ctx.send(embed=embed)
                return
            
            await self.bot.data_manager.edit_verbal(verbal_id, author.id, author.name, new_reason)

            successEmbed = discord.Embed(description=f"✅ **Updated verbal for <@{user.id}> ({user.name})**",
                                         color=discord.Color.green())
            successEmbed.add_field(name="New Reason", value=new_reason, inline=False)
            successEmbed.add_field(name="Verbal ID", value=f"```{verbal_id}```", inline=False)
            await ctx.send(embed=successEmbed)

        except Exception as e:
            logger.exception(f"verbal_edit error: {e}")
            raise BotError(f"/verbal_edit sent an error: {e}")


    @commands.hybrid_command(name="verbal_delete", description="Delete a user's verbal warning")
    @app_commands.describe(verbal_id="The verbal's ID")
    @checks.is_guild()
    @checks.is_user()
    async def verbal_delete(self, ctx, verbal_id: str):
        try:
            guild = ctx.guild
            userID = None
            user = None
            
            result = await self.bot.data_manager.get_verbal(verbal_id)
            if len(result) != 0:
                userID = result[0][3]
            else:
                embed = discord.Embed(description="❌ Verbal not found, invalid ID",
                                            color=discord.Color.red())
                await ctx.send(embed=embed)
                return
            
            try:
                user = await asyncio.wait_for(guild.fetch_member(userID), timeout=1)
            except Exception:
                try:
                    user = await asyncio.wait_for(guild.fetch_member(userID), timeout=1)
                except Exception:
                    embed = discord.Embed(description="❌ User not found, if this command fails "
                                          "again the user does not exist (or Discord's API is down)",
                                            color=discord.Color.red())
                    await ctx.send(embed=embed)
                    return
                
            dm_channel = user.dm_channel or await user.create_dm()
            print("dm channel id", dm_channel.id)
         
            if dm_channel:
                try:
                    print("id to fetch", int(verbal_id))
                    message = await dm_channel.fetch_message(int(verbal_id))
                    print("got message", message.id)
                except discord.NotFound:
                    embed = discord.Embed(description="❌ Verbal not found, invalid user or ID",
                                            color=discord.Color.red())
                    await ctx.send(embed=embed)
                    return

                except discord.Forbidden:
                    embed = discord.Embed(description="❌ Unable to delete verbal, user may not be accepting DMs",
                                            color=discord.Color.red())
                    await ctx.send(embed=embed)
                    return

                except Exception:
                    embed = discord.Embed(description="❌ Unable to find verbal",
                                            color=discord.Color.red())
                    await ctx.send(embed=embed)
                    return
                
                await message.delete()

            else:
                embed = discord.Embed(description="❌ Could not create a DM channel with the user",
                                      color=discord.Color.red())
                await ctx.send(embed=embed)
                return
            
            await self.bot.data_manager.remove_verbal(verbal_id)

            successEmbed = discord.Embed(description=f"✅ **Deleted verbal `{verbal_id}` from <@{user.id}> ({user.name})**",
                                         color=discord.Color.green())
            
            await ctx.send(embed=successEmbed)

        except Exception as e:
            logger.exception(f"verbal_delete error: {e}")
            raise BotError(f"/verbal_delete sent an error: {e}")
        

    @commands.hybrid_command(name="verbal_history", description="View a user's verbal warning history")
    @app_commands.describe(user="User to remove from blacklist")
    @checks.is_guild()
    @checks.is_user()
    async def verbal_history(self, ctx: commands.Context, user: discord.Member):
        try:
            pages = []
            count = 0
            limit = 0
            guild = ctx.guild
            
            historyEmbed = discord.Embed(title=f"Verbal history for {user.name}",
                                  description="User does not have any verbals",
                                  color=discord.Color.green())
            if (user.avatar):
                historyEmbed.set_author(name=f"{user.name} | {user.id}", icon_url=user.avatar.url)
            else:
                historyEmbed.set_author(name=f"{user.name} | {user.id}")
            
            history = await self.bot.data_manager.get_verbal_history(guild.id, user.id)
            print("verbal history", history)

            if history is not None:
                if len(history) == 0:
                    await ctx.send(embed=historyEmbed)
                    return
                else:
                    page_counts = build_subsections(len(history), 4)
                    print(page_counts)
                    for page_count in page_counts:
                        limit += page_count
                        historyEmbed = discord.Embed(title=f"Verbal history for {user.name}",
                                description="",
                                color=discord.Color.green())
                        
                        if (user.avatar):
                            historyEmbed.set_author(name=f"{user.name} | {user.id}", icon_url=user.avatar.url)
                        else:
                            historyEmbed.set_author(name=f"{user.name} | {user.id}")

                        while (count < limit):
                            verbal = history[count]

                            verbalID = verbal[0]
                            authorID = verbal[1]
                            authorName = verbal[2]
                            date = verbal[3]
                            content = verbal[4]

                            # member = guild.get_member(user_id)
                            # if not member:
                            #     member = await guild.fetch_member(user_id)

                            #     await asyncio.wait_for(self.bot.fetch_channel(inboxID), timeout=1)

                            historyEmbed.add_field(name=f"Case {count + 1}", 
                                            value=f"**Moderator:** {authorName} ({authorID})\n**Date:** <t:{date}:D> (<t:{date}:R>)\n**Reason:** {content}\n**Verbal ID:**```{verbalID}```{'⎯' * 20}", 
                                            inline=False)
                            count += 1
                        pages.append(historyEmbed)


            for page in range(len(pages)):
                pages[page].set_footer(text=f"Use the buttons below to navigate (Page {page + 1}/{len(pages)})")

            # Create an instance of the pagination view
            view = Paginator(pages)
            view.message = await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            raise BotError(f"/verbal_history sent an error: {e}")

async def setup(bot):
    await bot.add_cog(Moderation(bot))