import discord
import time
import asyncio
import io
import re
import datetime
from discord.ext import commands
from copy import deepcopy
from typing import List
from discord import app_commands
from classes.error_handler import *
from classes.embeds import *
from classes.ticket_creator import DMCategoryButtonView, TicketRatingView
from utils import checks, queries, emojis
from utils.logger import *


async def close_ticket(bot, ticket_channel, closer, 
                       userID, guildID, 
                       reason, anon, inactive = False):
    try:
        deleted = False
        closerID = -1
        closerName = "Unknown"
        if closer is not None:
            closerID = closer.id
            closerName = closer.name
        closingMessage = None
        closingEmbed = discord.Embed(description="Closing ticket...",
                                         color=discord.Color.blue())
        
        if isinstance(ticket_channel, discord.TextChannel):
            try:
                closingMessage = await ticket_channel.send(embed=closingEmbed)
            except discord.NotFound:
                deleted = True
            except Exception:
                pass
            try:
                await bot.data_manager.close_ticket(ticket_channel.id, closerID, closerName)
                await bot.data_manager.delete_user_ticket(userID, guildID)
                await bot.data_manager.clear_channel_links(ticket_channel.id)
                await bot.channel_status.set_emoji(ticket_channel, None)
            except Exception:
                errorEmbed = discord.Embed(description="❌ Data error on ticket close, contact an admin",
                                           color=discord.Color.red())
                await ticket_channel.send(embed=errorEmbed)
                return
            
            asyncio.create_task(delete_channel(ticket_channel, closingMessage, deleted))

            guild = ticket_channel.guild
            id_list = (ticket_channel.topic).split()
            threadID = id_list[-1]
            opener = None
            config = await bot.data_manager.get_or_load_config(guild.id)

            if config is None:
                # FIXME
                return False

            if anon is None:
                if (config["anon"] == 'true'):
                    anon = True
                else:
                    anon = False
            
            closing = config["closing"]
            logID = config["logID"] 
            log_channel = await bot.cache.get_channel(logID)
            thread = await bot.cache.get_channel(threadID)
            opener = await bot.cache.get_guild_member(guild, userID)
                    
            closeLogEmbed = discord.Embed(title=f"Ticket Closed", description=reason, 
                                    color=discord.Color.red())
            closeLogEmbed.timestamp = datetime.now(timezone.utc)

            await bot.data_manager.flush_messages_v2()
            query = queries.closing_queries(ticket_channel.id)
            try:
                result = await bot.data_manager.execute_query(query)
            except Exception:
                result = []
                
            if (len(result) > 0):
                data = result[0]
                if data[0] is None:
                    duration = "N/A"
                else:
                    duration = queries.format_time(data[0])
                if data[1] is None:
                    response = "N/A"
                else:
                    response = queries.format_time(data[1])

            closeLogEmbed.add_field(name="Logs", value=f"<#{thread.id}>", inline=False)
            closeLogEmbed.add_field(name="Ticket Duration", value=duration, inline=True)
            closeLogEmbed.add_field(name="First Response Time", value=response, inline=True)

            name = f"{closerName} | {closerID}"
            url = (closer.avatar and closer.avatar.url) or closer.display_avatar.url
            if anon:
                name = f"{name} (Anonymous)"
            closeLogEmbed.set_author(name=name, icon_url=url)

            if inactive:
                closeLogEmbed.title="Ticket Closed (Inactivity)"

            if opener:
                closeLogEmbed.set_footer(text=f"{opener.name} | {opener.id}", icon_url=(opener.avatar and opener.avatar.url) or opener.display_avatar.url)

                dm_channel = opener.dm_channel or await opener.create_dm()
                if dm_channel:
                    closeUserEmbed = discord.Embed(title=f"Ticket Closed", description=reason, 
                                            color=discord.Color.red())
                    closeUserEmbed.timestamp = datetime.now(timezone.utc)
                    if guild.icon:
                        closeUserEmbed.set_footer(text=guild.name, icon_url=guild.icon.url)
                    else:
                        closeUserEmbed.set_footer(text=guild.name)
                    if not anon:
                        closeUserEmbed.set_author(name=name, icon_url=url)
                    try:
                        await dm_channel.send(embed=closeUserEmbed)
                        await send_closing(bot, guild, dm_channel, ticket_channel.id, opener, closing)
                    except Exception:
                        logger.warning("Failed to DM closing messages to a user")
                        pass
                else:
                    pass
            else:
                closeLogEmbed.set_footer(text=f"Member not found | {userID}")
            try:
                await thread.send(embed=closeLogEmbed)
            except Exception: 
                pass
            await log_channel.send(embed=closeLogEmbed)
            await thread.edit(archived=True, locked=True)
            return True
        
        else:
            pass
            # FIXME edge case, channel with timer is deleted (aka ticket closed but channel doesn't exist)
            # await bot.data_manager.close_ticket(ticket_channel.id, closerID, closerName)
            # await bot.data_manager.delete_user_ticket(userID, guild.id)
            # await bot.channel_status.set_emoji(ticket_channel, None)
    
    except Exception as e:
            print(f"close_ticket sent an error: {e}")
            logger.exception(e)


async def delete_channel(ticket_channel, closingMessage, deleted):
    if not deleted:
        delete_time = int(time.time()) + 5
        countdownEmbed = discord.Embed(description=f"Deleting ticket channel <t:{delete_time}:R>.\n"
                                    "Switch channels now to avoid jumping to the top of the channel list.",
                                    color=discord.Color.blue())
        await closingMessage.edit(embed=countdownEmbed)
        await asyncio.sleep(5)
        await ticket_channel.delete(reason="Ticket closed due to inactivity")
    return


async def send_closing(bot, guild, dm_channel, channelID, user, closing_text):
    try:
        if (closing_text is None or len(closing_text) <= 1):
            closing_text = ("Your ticket has been closed. Please do not reply to this message. "
                       "\n\nIf you require support again in the future, you may open a new ticket."
                       "\n\nHow did we do? Let us know below!")
        closing = closing_text.format(
            mention=f"<@{user.id}>",
            name=user.name,
            id=user.id)
    except KeyError:
        return

    closingEmbed = discord.Embed(title="Closing Message", description=closing)
    closingEmbed.timestamp = datetime.now(timezone.utc)

    url = None
    if guild.icon:
        url = guild.icon.url
    closingEmbed.set_footer(text=f"{guild.name} | {channelID}", icon_url=url)

    view = TicketRatingView(bot=bot)
    message = await dm_channel.send(embed=closingEmbed, view=view)
    view.message = message


async def export_ticket_history(channel: discord.TextChannel,
                                close_message: str = "",
                                closer_username: str = "") -> discord.File:
    try:
        history = []

        async for message in channel.history(oldest_first=True, limit=200):
            # Skip other bot messages
            if message.author.bot and message.author.id != 1333954467519004673:
                continue 

            is_staff = False
            content = None

            if message.embeds:
                embed = message.embeds[0]
                # Embedded staff message
                if "[STAFF]" in embed.title:
                    is_staff = True
                    if embed.description:
                        content = embed.description
                    break
                
                # Embedded user message
                elif "Received" in embed.title:
                    if embed.description:
                        content = embed.description
                    break

            elif "[COMMENT]" in message.content:
                text = """**luciniv** `[COMMENT]`
                comment
                more comment
                -# `ID: 429711831695753237 | MSG: 1377379957126463579`"""

                match = re.search(r"\[COMMENT\]\s*\n(.*?)(?:\n-#|$)", text, re.DOTALL)
                if match:
                    comment_text = match.group(1).strip()

                content = comment_text

            role_label = "Staff" if is_staff else "User"

            history.append(f"({role_label}): {content}")

        # Append the close message, if provided
        if close_message and closer_username:
            timestamp = datetime.utcnow().strftime("[%Y-%m-%d %H:%M:%S]")
            history.append(f"{timestamp} {closer_username} (Staff): {close_message.strip()}")

        joined_history = "\n".join(history)
        file_bytes = io.BytesIO(joined_history.encode())
        file = discord.File(file_bytes, filename=f"ticket_log_{channel.id}.txt")
        return file

    except Exception as e:
        print(f"export_ticket_history sent an error: {e}")
        logger.exception(e)


class GenerateReplyView(discord.ui.View):
        def __init__(self, reply_text, author, target_channel):
            super().__init__(timeout=60)
            self.reply_text = reply_text
            self.author = author
            self.target_channel = target_channel
            self.message = None

        @discord.ui.button(label="Send Reply", style=discord.ButtonStyle.success)
        async def send_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user != self.author:
                return await interaction.response.send_message("You can't use this button", ephemeral=True)

            await self.target_channel.send(self.reply_text)
            await interaction.response.edit_message(content="✅ Reply sent", view=None)
            self.stop()

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
        async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user != self.author:
                return await interaction.response.send_message("You can't use this button", ephemeral=True)

            await interaction.response.edit_message(content="❌ Cancelled reply", view=None)
            self.stop()


class Tools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        

    @commands.command(name="reply", aliases=["r"])
    @checks.is_user()
    @checks.is_guild()
    async def reply(self, ctx, *, message):
        try:
            channel = ctx.channel
            author = ctx.author

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-2]
                    full_message = ctx.message if hasattr(ctx, "message") else message

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        task = asyncio.create_task(analytics.route_to_dm(full_message, channel, author, threadID, userID, None, False))
                        result = await task
                    return

            errorEmbed = discord.Embed(description="❌ This command can only be used in ticket channels",
                                       color=discord.Color.red())
            await channel.send_message(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"+reply sent an error: {e}")
        

    @commands.command(name="areply", aliases=["ar"])
    @checks.is_user()
    @checks.is_guild()
    async def areply(self, ctx, *, message):
        try:
            channel = ctx.channel
            author = ctx.author

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-2]
                    full_message = ctx.message if hasattr(ctx, "message") else message

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        task = asyncio.create_task(analytics.route_to_dm(full_message, channel, author, threadID, userID, True, False))
                        result = await task
                    return

            errorEmbed = discord.Embed(description="❌ This command can only be used in ticket channels",
                                       color=discord.Color.red())
            await channel.send_message(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"+areply sent an error: {e}")
        

    @commands.command(name="nonareply", aliases=["nar"])
    @checks.is_user()
    @checks.is_guild()
    async def nonareply(self, ctx, *, message):
        try:
            channel = ctx.channel
            author = ctx.author

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-2]
                    full_message = ctx.message if hasattr(ctx, "message") else message

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        task = asyncio.create_task(analytics.route_to_dm(full_message, channel, author, threadID, userID, False, False))
                        result = await task
                    return

            errorEmbed = discord.Embed(description="❌ This command can only be used in ticket channels",
                                       color=discord.Color.red())
            await channel.send_message(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"+nonareply sent an error: {e}")
        

    @commands.command(name="ai_reply")
    @checks.is_user()
    @checks.is_guild()
    async def ai_reply(self, ctx):
        await ctx.defer()

        # Step 1: Fetch message history
        history = await ctx.channel.history(limit=50, oldest_first=True).flatten()
        transcript = ""
        for msg in history:
            transcript += f"{msg.author.display_name}: {msg.content}\n"

        # Step 2: Write to file (optional for debugging or archiving)
        file_buffer = io.StringIO(transcript)
        file_buffer.seek(0)

        # Step 3: Generate AI reply (replace this with actual logic)
        await ctx.send("Generating reply from AI...")
        ai_reply = await self.generate_ai_reply(transcript)

        # Step 4: Show user the reply and ask for confirmation
        view = GenerateReplyView(ai_reply, ctx.author, ctx.channel)
        view.message = await ctx.send(
            content=f"🧠 AI-generated reply:\n```{ai_reply}```\nWould you like to send this?",
            view=view
        )

    async def generate_ai_reply(self, transcript: str) -> str:
        # 🧠 Replace this with your AI call
        # e.g., OpenAI, Claude, local model, etc.
        return f"This is a placeholder reply based on the transcript of {len(transcript.splitlines())} lines"

    
    @commands.command(name="reply_edit", aliases=["edit"])
    @checks.is_user()
    @checks.is_guild()
    async def reply_edit(self, ctx, reply_id: str, *, new_content: str):
        try:
            guild = ctx.guild
            channel = ctx.channel
            author = ctx.author
            userID = None
            user = None
            old_content = None
            new_content = await self.bot.helper.convert_mentions(new_content, guild)

            errorEmbed = discord.Embed(description="❌ This command can only be used in ticket channels",
                                          color=discord.Color.red())

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-2]
                    startEmbed = discord.Embed(description="Started editing process...", 
                                               color=discord.Color.blue())
                    startMessage = await ctx.send(embed=startEmbed)
       
                    try:
                        message = await channel.fetch_message(reply_id)
                    except Exception:
                        errorEmbed.description="❌ An error occurred fetching the message. Please try again"
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    if message is None:
                        errorEmbed.description="❌ Could not find a message in this channel with that ID"
                        await ctx.send(embed=errorEmbed)
                        return

                    if (message.author.id not in (1304609006379073628, 1333954467519004673)):
                        errorEmbed.description="❌ The message you selected is not from MailBee"
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    if (not message.embeds) or (not message.embeds[0].title) or (not "Sent" in message.embeds[0].title):
                        errorEmbed.description="❌ The message you selected is not a ticket reply"
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    if ((message.embeds[0].author.name).split()[2] != str(author.id)):
                        if (channel.permissions_for(author).administrator):
                            pass
                        else:
                            errorEmbed.description="❌ You do not have permission to alter that message"
                            await ctx.send(embed=errorEmbed)
                            return

                    if (len(new_content) > 4000):
                        errorEmbed.description=("❌ Content must be at most 4000 characters. Note that "
                                                "channel links add ~70 additional characters each")
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    member = await self.bot.cache.get_guild_member(guild, userID)
                    if member is None:
                        errorEmbed.description=("❌ User not found, if this command fails again the user "
                                                "does not exist (or Discord's API is down)")
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    dm_messageID, thread_messageID = await self.bot.data_manager.get_linked_messages(channel.id, reply_id)
                    dm_channel = member.dm_channel or await member.create_dm()
              
                    if dm_channel:
                        try:
                            dm_message = await dm_channel.fetch_message(dm_messageID)
                        except Exception:
                            errorEmbed.description="❌ Could not find respective message in DMs"
                            await ctx.send(embed=errorEmbed)
                            return
                    else:
                        errorEmbed.description="❌ Could not open DM channel with the user"
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    if dm_message:
                        newEmbed = deepcopy(dm_message.embeds[0])
                        newEmbed.description=new_content
                        try:
                            await dm_message.edit(embed=newEmbed)
                        except Exception:
                            errorEmbed.description=("❌ Failed to edit DM message, user does not share "
                                                    "a server with me or has blocked me")
                            await ctx.send(embed=errorEmbed)
                            return
                    else:
                        errorEmbed.description="❌ Could not find respective message in DMs"
                        await ctx.send(embed=errorEmbed)
                        return

                    newSentEmbed = None
                    thread = await self.bot.cache.get_channel(threadID)
                    thread_flag = False
                    if thread:
                        try:
                            thread_message = await thread.fetch_message(thread_messageID)
                        except Exception as e:
                            thread_flag = True

                        if thread_message:
                            newSentEmbed = deepcopy(thread_message.embeds[0])
                            newSentEmbed.title = f"{newSentEmbed.title} [EDITED]"
                            newSentEmbed.description=new_content
                            newSentEmbed.color=discord.Color.yellow()
                            try:
                                await thread_message.reply(embed=newSentEmbed)
                            except Exception:
                                thread_flag = True
                        else:
                            thread_flag = True
                    else:
                        thread_flag = True

                    if thread_flag:
                        errorEmbed.description=("❌ Failed to edit thread log message")
                        await ctx.send(embed=errorEmbed)

                    try:
                        await message.edit(embed=newSentEmbed)
                    except Exception:
                        errorEmbed.description=("❌ Failed to edit message in this channel, DM message has been edited")
                        await ctx.send(embed=errorEmbed)
                        return

                    await startMessage.delete()
                    successEmbed = discord.Embed(description=f"✅ Updated ticket reply to **{member.name}**",
                                                color=discord.Color.green())
                    await ctx.send(embed=successEmbed)
                    return
            
            await ctx.send(embed=errorEmbed)

        except Exception as e:
            logger.exception(f"reply_edit error: {e}")
            raise BotError(f"/reply_edit sent an error: {e}")
        

    @commands.command(name="reply_delete", aliases=["delete"])
    @checks.is_user()
    @checks.is_guild()
    async def reply_delete(self, ctx, reply_id: str):
        try:
            guild = ctx.guild
            channel = ctx.channel
            author = ctx.author
            userID = None
            user = None

            errorEmbed = discord.Embed(description="❌ This command can only be used in ticket channels",
                                          color=discord.Color.red())

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-2]

                    startEmbed = discord.Embed(description="Started deleting process...", color=discord.Color.blue())
                    startMessage = await ctx.send(embed=startEmbed)
       
                    try:
                        message = await channel.fetch_message(reply_id)
                    except Exception:
                        errorEmbed.description="❌ An error occurred fetching the message. Please try again"
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    if message is None:
                        errorEmbed.description="❌ Could not find a message in this channel with that ID"
                        await ctx.send(embed=errorEmbed)
                        return

                    if (message.author.id not in (1304609006379073628, 1333954467519004673)):
                        errorEmbed.description="❌ The message you selected is not from MailBee"
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    if (not message.embeds) or (not message.embeds[0].title) or (not "Sent" in message.embeds[0].title):
                        errorEmbed.description="❌ The message you selected is not a ticket reply"
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    if ((message.embeds[0].author.name).split()[2] != str(author.id)):
                        if (channel.permissions_for(author).administrator):
                            pass
                        else:
                            errorEmbed.description="❌ You do not have permission to alter that message"
                            await ctx.send(embed=errorEmbed)
                            return
                    
                    member = await self.bot.cache.get_guild_member(guild, userID)
                    if member is None:
                        errorEmbed.description=("❌ User not found, if this command fails again the user "
                                                "does not exist (or Discord's API is down)")
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    dm_messageID, thread_messageID = await self.bot.data_manager.get_linked_messages(channel.id, reply_id)
                    dm_channel = member.dm_channel or await member.create_dm()
              
                    if dm_channel:
                        try:
                            dm_message = await dm_channel.fetch_message(dm_messageID)
                        except Exception:
                            errorEmbed.description="❌ Could not find respective message in DMs"
                            await ctx.send(embed=errorEmbed)
                            return
                    else:
                        errorEmbed.description="❌ Could not open DM channel with the user"
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    if dm_message:
                        try:
                            await dm_message.delete()
                        except Exception:
                            errorEmbed.description=("❌ Failed to delete DM message, user does not share "
                                                    "a server with me or has blocked me")
                            await ctx.send(embed=errorEmbed)
                            return
                    else:
                        errorEmbed.description="❌ Could not find respective message in DMs"
                        await ctx.send(embed=errorEmbed)
                        return

                    thread = await self.bot.cache.get_channel(threadID)
                    thread_flag = False
                    if thread:
                        try:
                            thread_message = await thread.fetch_message(thread_messageID)
                        except Exception as e:
                            thread_flag = True

                        if thread_message:
                            newEmbed = deepcopy(thread_message.embeds[0])
                            newEmbed.title = f"{newEmbed.title} [DELETED]"
                            newEmbed.color=discord.Color.red()
                            try:
                                await thread_message.edit(embed=newEmbed)
                            except Exception:
                                thread_flag = True
                        else:
                            thread_flag = True
                    else:
                        thread_flag = True

                    if thread_flag:
                        errorEmbed.description=("❌ Failed to mark thread log message as deleted")
                        await ctx.send(embed=errorEmbed)

                    try:
                        await message.delete()
                    except Exception:
                        errorEmbed.description=("❌ Failed to delete message in this channel, DM message has been deleted")
                        await ctx.send(embed=errorEmbed)
                        return

                    await startMessage.delete()
                    successEmbed = discord.Embed(description=f"✅ Deleted ticket reply to **{member.name}**",
                                                color=discord.Color.green())
                    await ctx.send(embed=successEmbed)
                    return
            
            await ctx.send(embed=errorEmbed)

        except Exception as e:
            logger.exception(f"reply_delete error: {e}")
            raise BotError(f"/reply_delete sent an error: {e}")


    @commands.command(name="close", aliases=["c"])
    @checks.is_user()
    @checks.is_guild()
    async def close(self, ctx, *, reason: str = "No reason provided"):
        try:
            ticket_channel = ctx.channel
            guild = ticket_channel.guild
            closer = ctx.author
            state = None

            errorEmbed = discord.Embed(description=("❌ Error closing ticket. Please contact a"
                                                    " server admin with this error"),
                                       color=discord.Color.red())

            if (ticket_channel.topic):
                if ("Ticket channel" in ticket_channel.topic):
                    text = await self.bot.helper.convert_mentions(reason, guild)
                    if len(text) > 3000:
                        errorEmbed.description=("❌ Reason must be at most 3000 characters. Note that "
                                                "channel links add ~70 additional characters each.")
                        await ticket_channel.send(embed=errorEmbed)
                        return
                    
                    id_list = (ticket_channel.topic).split()
                    userID = id_list[-2]

                    await self.bot.channel_status.remove_timer(ticket_channel.id)
                    state = await close_ticket(self.bot, ticket_channel, closer, userID, guild.id, text, None)
            
                    if not state:
                        await ticket_channel.send(embed=errorEmbed)
                        
                    return

            errorEmbed.description=("❌ This command can only be used in ticket channels")
            await ticket_channel.send(embed=errorEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/close sent an error: {e}")
        

    @commands.command(name="aclose", aliases=["ac"])
    @checks.is_user()
    @checks.is_guild()
    async def aclose(self, ctx, *, reason: str = "No reason provided"):
        try:
            ticket_channel = ctx.channel
            guild = ticket_channel.guild
            closer = ctx.author
            state = None

            errorEmbed = discord.Embed(description=("❌ Error closing ticket. Please contact a"
                                                    " server admin with this error"),
                                       color=discord.Color.red())

            if (ticket_channel.topic):
                if ("Ticket channel" in ticket_channel.topic):
                    text = await self.bot.helper.convert_mentions(reason, guild)
                    if len(text) > 3000:
                        errorEmbed.description=("❌ Reason must be at most 3000 characters. Note that "
                                                "channel links add ~70 additional characters each.")
                        await ticket_channel.send(embed=errorEmbed)
                        return
                    id_list = (ticket_channel.topic).split()
                    userID = id_list[-2]

                    await self.bot.channel_status.remove_timer(ticket_channel.id)
                    state = await close_ticket(self.bot, ticket_channel, closer, userID, guild.id, text, True)
            
                    if not state:
                        await ticket_channel.send(embed=errorEmbed)
                        
                    return

            errorEmbed.description=("❌ This command can only be used in ticket channels")
            await ticket_channel.send(embed=errorEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/aclose sent an error: {e}")
        

    @commands.command(name="nonaclose", aliases=["nac"])
    @checks.is_user()
    @checks.is_guild()
    async def nonaclose(self, ctx, *, reason: str = "No reason provided"):
        try:
            ticket_channel = ctx.channel
            guild = ticket_channel.guild
            closer = ctx.author
            state = None

            errorEmbed = discord.Embed(description=("❌ Error closing ticket. Please contact a"
                                                    " server admin with this error"),
                                       color=discord.Color.red())

            if (ticket_channel.topic):
                if ("Ticket channel" in ticket_channel.topic):
                    text = await self.bot.helper.convert_mentions(reason, guild)
                    if len(text) > 3000:
                        errorEmbed.description=("❌ Reason must be at most 3000 characters. Note that "
                                                "channel links add ~70 additional characters each.")
                        await ticket_channel.send(embed=errorEmbed)
                        return
                    id_list = (ticket_channel.topic).split()
                    userID = id_list[-2]

                    await self.bot.channel_status.remove_timer(ticket_channel.id)
                    state = await close_ticket(self.bot, ticket_channel, closer, userID, guild.id, text, False)
            
                    if not state:
                        await ticket_channel.send(embed=errorEmbed)
                        
                    return

            errorEmbed.description=("❌ This command can only be used in ticket channels")
            await ticket_channel.send(embed=errorEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/nonaclose sent an error: {e}")
    

    # Set a ticket as inactive for a period of time, then mark to close
    # Remove inactive / close marker if the user responds
    @commands.command(name="inactive", aliases=["inact"])
    @checks.is_user()
    @checks.is_guild()
    async def inactive(self, ctx, hours: int = 24, *, reason: str = "Ticket closed due to inactivity"):
        try:    
            author = ctx.author
            channel = ctx.channel
            channelID = channel.id
            guild = channel.guild
            now = time.time()

            errorEmbed = discord.Embed(description="❌ Hours must be between 1 to 72 (inclusive)", 
                                       color=discord.Color.red())

            if (isinstance(channel, discord.TextChannel)):
                if (channel.topic):
                    if ("Ticket channel" in channel.topic):
                        if ((hours < 1) or (hours > 72)):
                            await channel.send(embed=errorEmbed)
                            return
                        else:
                            text = await self.bot.helper.convert_mentions(reason, guild)
                            if len(text) > 3000:
                                errorEmbed.description=("❌ Reason must be at most 3000 characters. Note that "
                                                        "channel links add ~70 additional characters each.")
                                await channel.send(embed=errorEmbed)
                                return
                            end_time = now + (hours * 3600)
                            timer = self.bot.channel_status.get_timer(channelID)
                            statusEmbed = discord.Embed(title="", 
                                            description=f"Status set to **inactive** 🕓 for {hours} hour(s).\n"
                                                        f"This ticket will **close** <t:{int(end_time)}:R> "
                                                        "(allowing up to 1 minute of potential delay)\n\n"
                                                        f"**Reason:** {text}",
                                                        color=discord.Color.green())
                            
                            if timer is not None:
                                statusEmbed.description=(f"Failed to change status to **inactive** 🕓, "
                                                        "use `+active` to remove current inactive state")
                                statusEmbed.color=discord.Color.red()
                                await channel.send(embed=statusEmbed)
                                return
                            
                            await self.bot.cache.store_guild_member(guild.id, author)
                            await self.bot.cache.store_user(author)

                            id_list = (channel.topic).split()
                            userID = id_list[-2]
                        
                            await self.bot.channel_status.set_emoji(channel, "inactive", True)
                            await self.bot.channel_status.add_timer(channelID, end_time, 
                                                              author.id, userID, reason)
                            await self.bot.data_manager.save_timers_to_redis()

                            await channel.send(embed=statusEmbed)
                            return

            errorEmbed = discord.Embed(title="", 
                                description="❌ Channel is not a ticket", 
                                color=discord.Color.red())
            await channel.send(embed=errorEmbed)
            return

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/inactive sent an error: {e}")
        

    # Set a ticket as inactive for a period of time, then mark to close
    # Remove inactive / close marker if the user responds
    @commands.command(name="active", aliases=["act"])
    @checks.is_user()
    @checks.is_guild()
    async def active(self, ctx):
        try:    
            channel = ctx.channel
            channelID = channel.id
            now = time.time()

            if (isinstance(channel, discord.TextChannel)):
                if (channel.topic):
                    if ("Ticket channel" in channel.topic):

                        state = await self.bot.channel_status.remove_timer(channelID)

                        if not state:
                            errorEmbed = discord.Embed(title="", 
                                                description="❌ Ticket was not inactive", 
                                                color=discord.Color.red())
                            await channel.send(embed=errorEmbed)
                            return
                        else:
                            await self.bot.data_manager.save_timers_to_redis()
                            successEmbed = discord.Embed(title="", 
                                            description=f"Removed **inactive** timer, status set to **waiting**",
                                                        color=discord.Color.green())
                            await self.bot.channel_status.set_emoji(channel, "wait", True)
                            await channel.send(embed=successEmbed)
                            return

            errorEmbed = discord.Embed(title="", 
                                description="❌ Channel is not a ticket", 
                                color=discord.Color.red())
            await channel.send(embed=errorEmbed)
            return

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/active sent an error: {e}")
        

    # Move a ticket channel
    @app_commands.command(name="move", description="Move a ticket to a different category")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(category="Ticket category to move the current ticket channel to")
    @app_commands.describe(location="Any category to move the current ticket channel to")
    async def move(self, interaction: discord.Interaction, category: str = None, location: discord.CategoryChannel = None):
        try:
            await interaction.response.defer()

            guild = interaction.guild
            channel = interaction.channel
            author = interaction.user

            errorEmbed = discord.Embed(description="❌ This command can only be used in ticket channels.",
                                        color=discord.Color.red())

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-2]
                    if category is None and location is None:
                        errorEmbed = discord.Embed(description="❌ You must specify some category or location.",
                                        color=discord.Color.red())
                        await interaction.followup.send(embed=errorEmbed)
                        return
                    if category is not None:
                        categoryID, flag = category.split()
                        category = await self.bot.cache.get_channel(categoryID)

                        if category is None:
                            errorEmbed = discord.Embed(description="❌ Category doesn't exist.",
                                            color=discord.Color.red())
                            await interaction.followup.send(embed=errorEmbed)
                            return
                        
                        if category.id == channel.category.id:
                            errorEmbed = discord.Embed(description="❌ Cannot move channel to the category it's already in.",
                                            color=discord.Color.red())
                            await interaction.followup.send(embed=errorEmbed)
                            return
                        
                        ticket_is_nsfw = False
                        types_raw = await self.bot.data_manager.get_or_load_guild_types(guild.id)
                        for type in types_raw:
                            if int(type["NSFWCategoryID"]) == channel.category.id:
                                ticket_is_nsfw = True
                                break

                        try:
                            if flag == "True" and not ticket_is_nsfw:
                                await channel.edit(nsfw=True,
                                                overwrites=category.overwrites,
                                                category=category)
                                await self.bot.channel_status.set_emoji(channel, None, False, True)

                            elif flag == "False" and ticket_is_nsfw:
                                await channel.edit(nsfw=False,
                                                overwrites=category.overwrites,
                                                category=category)
                                await self.bot.channel_status.set_emoji(channel, None, False, False)
                                
                            else:
                                await channel.edit(overwrites=category.overwrites,
                                                category=category)
                                
                        except Exception:
                            errorEmbed.description="❌ Failed to edit channel. Please try again later."
                            await interaction.followup.send(embed=errorEmbed)
                            return

                        successEmbed = discord.Embed(description=f"✅ Moved this channel to **{category.name}**\n"
                                                                "**NOTE:** This channel's emoji status may take up to "
                                                                "5 minutes to update",
                                                    color=discord.Color.green())
                        await interaction.followup.send(embed=successEmbed)
                        return
                    else:
                        if location.id == channel.category.id:
                            errorEmbed = discord.Embed(description="❌ Cannot move channel to the category it's already in.",
                                            color=discord.Color.red())
                            await interaction.followup.send(embed=errorEmbed)
                            return
                        try:
                            await channel.edit(category=location)
                                
                        except Exception:
                            errorEmbed.description="❌ Failed to edit channel. Please try again later."
                            await interaction.followup.send(embed=errorEmbed)
                            return

                        successEmbed = discord.Embed(description=f"✅ Moved this channel to **{location.name}**\n"
                                                                "**NOTE:** Using `/move` with a **location** will not "
                                                                "sync channel permissions or stauses.",
                                                    color=discord.Color.green())
                        await interaction.followup.send(embed=successEmbed)
                        return
                
            await interaction.followup.send(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"/move sent an error: {e}")


    @move.autocomplete('category')
    async def move_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        if not guild:
            return [] 

        # Get types for the specific guild
        types_raw = await self.bot.data_manager.get_or_load_guild_types(guild.id)

        id_flags = {}
        for t in types_raw:
            cat_id = int(t["categoryID"])
            nsfw_id = int(t["NSFWCategoryID"])

            if cat_id not in (-1, 0):
                id_flags[cat_id] = id_flags.get(cat_id, False)

            if nsfw_id not in (-1, 0):
                id_flags[nsfw_id] = True  # overwrites False if already present

        final_ids = [
            (cat.name, cat.id, id_flags[cat.id])
            for cat in guild.categories
            if cat.id in id_flags]

        matches = [
            app_commands.Choice(name=name, value=f"{id} {flag}")
            for name, id, flag in final_ids
            if current.casefold() in name.casefold()]
        
        return matches[:25]
    

    # Move a ticket channel
    @commands.command(name="nsfw")
    @checks.is_user()
    @checks.is_guild()
    async def nsfw(self, ctx):
        try:
            guild = ctx.guild
            channel = ctx.channel
            author = ctx.author

            errorEmbed = discord.Embed(description="❌ This command can only be used in ticket channels.",
                                        color=discord.Color.red())

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-2]

                    ticket_is_nsfw = False
                    types_raw = await self.bot.data_manager.get_or_load_guild_types(guild.id)
                    for type in types_raw:
                        if int(type["NSFWCategoryID"]) == channel.category.id:
                            ticket_is_nsfw = True
                            break

                    if ticket_is_nsfw:
                        errorEmbed.description=("❌ This ticket is already in a NSFW catgeory.\n"
                                                "Use `/move` to move it manually elsewhere.")
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    nsfwID = -1
                    for type in types_raw:
                        if int(type["categoryID"]) == channel.category.id:
                            nsfwID = int(type["NSFWCategoryID"])

                    if nsfwID in (0, -1):
                        errorEmbed.description=("❌ This ticket's type does not have a NSFW catgeory set.\n"
                                                "Use `/move` to move it manually.")
                        await ctx.send(embed=errorEmbed)
                        return

                    category = await self.bot.cache.get_channel(nsfwID)

                    if category is None:
                        errorEmbed = discord.Embed(description="❌ NSFW category for this ticket's type doesn't exist.",
                                        color=discord.Color.red())
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    if category.id == channel.category.id:
                        errorEmbed = discord.Embed(description="❌ Cannot move channel to the category it's already in.",
                                        color=discord.Color.red())
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    try:
                        await channel.edit(nsfw=True,
                                            overwrites=category.overwrites,
                                            category=category)
                        await self.bot.channel_status.set_emoji(channel, None, False, True)   
                    except Exception:
                        errorEmbed.description="❌ Failed to edit channel. Please try again later."
                        await ctx.send(embed=errorEmbed)
                        return

                    successEmbed = discord.Embed(description=f"✅ Moved this channel to **{category.name}**\n"
                                                              "**NOTE:** This channel's emoji status may take up to "
                                                              "5 minutes to update",
                                                 color=discord.Color.green())
                    await ctx.send(embed=successEmbed)
                    return
                
            await ctx.send(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"/move sent an error: {e}")


    # Manually update the status of a ticket channel
    @commands.hybrid_command(name="status", description="Change the emoji status of a ticket")
    @checks.is_user()
    @checks.is_guild()
    @app_commands.describe(status="Select an emoji from the provided list")
    @app_commands.choices(status=[
        app_commands.Choice(name=f"🆕 - New ticket", value="new"),
        app_commands.Choice(name=f"❗️ - Waiting for moderator response", value="alert"),
        app_commands.Choice(name=f"⏳ - Waiting for user response", value="wait"),
        app_commands.Choice(name=f"🔎 - Under review", value="review")])

    async def status(self, ctx, status: discord.app_commands.Choice[str]):
        try:    
            channel = ctx.channel
            emoji_name = status.name
            emoji_str = status.value

            current_name = self.bot.channel_status.pending_updates.get(channel.id, channel.name)
            if current_name.startswith(emojis.emoji_map.get("inactive", "")):
                errorEmbed = discord.Embed(description="❌ Cannot change the status of an **inactive** ticket", 
                                           color=discord.Color.red())
                await ctx.send(embed=errorEmbed)
                return

            result = await self.bot.channel_status.set_emoji(channel, emoji_str, True)

            statusEmbed = discord.Embed(description=f"✅ Channel status set to **{emoji_name}**"
                                        "\n(*Please wait up to 5 minutes for edits to appear*)",
                                        color=discord.Color.green())
            if not result:
                statusEmbed.description=(f"❌ Failed to set channel status to **{emoji_name}**, current "
                                         "or pending status is already set as this")
                statusEmbed.color=discord.Color.red()
            await ctx.send(embed=statusEmbed)
            return

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/status sent an error: {e}")
        

    @commands.command(name="ticket_button")
    @checks.is_admin()
    @checks.is_guild()
    async def post_ticket_button(self, ctx: commands.Context):
        guild_id = ctx.guild.id

        types = await self.bot.data_manager.get_or_load_guild_types(guild_id)

        if not types:
            await ctx.send("❌ This server doesn't have any ticket types configured")
            return

        view = DMCategoryButtonView(self.bot)
        ticketEmbed=discord.Embed(title="Need Support?", 
                                  description="Click the button below to open a support ticket with staff "
                                              "in your direct messages. The bot will guide you through the process!",
                                  color=discord.Color.green())
        await ctx.channel.send(embed=ticketEmbed, view=view)
    

async def setup(bot):
    await bot.add_cog(Tools(bot))
