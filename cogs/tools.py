import discord
import time
import asyncio
import io
import re
import datetime
from discord.ext import commands
from discord import app_commands
from classes.error_handler import *
from classes.embeds import *
from classes.ticket_creator import DMCategoryButtonView, TicketRatingView
from utils import checks, queries
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
        closingEmbed = discord.Embed(description="Closing ticket...",
                                         color=discord.Color.blue())
        
        if isinstance(ticket_channel, discord.TextChannel):
            try:
                await ticket_channel.send(embed=closingEmbed)
            except discord.NotFound:
                deleted = True
            except Exception:
                pass

            await bot.data_manager.close_ticket(ticket_channel.id, closerID, closerName)
            await bot.data_manager.delete_user_ticket(userID, guildID)
            await bot.channel_status.set_emoji(ticket_channel, None)

            if not deleted:
                await ticket_channel.delete(reason="Ticket closed due to inactivity")

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
            url = closer.display_avatar.url
            if anon:
                name = f"{name} (Anonymous)"
            closeLogEmbed.set_author(name=name, icon_url=url)

            if inactive:
                closeLogEmbed.title="Ticket Closed (Inactivity)"

            if opener:
                closeLogEmbed.set_footer(text=f"{opener.name} | {opener.id}", icon_url=opener.display_avatar.url)

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
                        logger.exception("Failed to DM closing messages to a user")
                        pass
                else:
                    pass
            else:
                closeLogEmbed.set_footer(text=f"Member not found | {userID}")

            await thread.send(embed=closeLogEmbed)
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


async def send_closing(bot, guild, dm_channel, channelID, user, closing_text):
    try:
        if (closing_text is None or len(closing_text) <= 1):
            closing_text = ("Thank you for reaching out to us! Your ticket has been closed. "
                       "Please do not respond to this message.\n\nFeel free to let us "
                       "know how we're doing using the buttons below!")
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
    closingEmbed.set_footer(text=f"{guild.name} | Ticket ID: {channelID}", icon_url=url)

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
                    print(comment_text)

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
        

    @commands.command(name="reply", description="Send a reply in the current ticket", 
                             aliases=["r"])
    @checks.is_guild()
    @checks.is_user()
    async def reply(self, ctx, *, message):
        try:
            channel = ctx.channel
            author = ctx.author

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-3]
                    full_message = ctx.message if hasattr(ctx, "message") else message

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        await analytics.route_to_dm(full_message, channel, author, threadID, userID, None, False)
                    return

            errorEmbed = discord.Embed(description="❌ This command can only be used in ticket channels",
                                       color=discord.Color.red())
            await channel.send_message(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"+reply sent an error: {e}")
        

    @commands.command(name="areply", description="Send an anonymous reply in the current ticket", 
                             aliases=["ar"])
    @checks.is_guild()
    @checks.is_user()
    async def areply(self, ctx, *, message):
        try:
            channel = ctx.channel
            author = ctx.author

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-3]
                    full_message = ctx.message if hasattr(ctx, "message") else message

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        await analytics.route_to_dm(full_message, channel, author, threadID, userID, True, False)
                    return

            errorEmbed = discord.Embed(description="❌ This command can only be used in ticket channels",
                                       color=discord.Color.red())
            await channel.send_message(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"+areply sent an error: {e}")
        

    @commands.command(name="nonareply", description="Send an NON-anonymous reply in the current ticket", 
                             aliases=["nar"])
    @checks.is_guild()
    @checks.is_user()
    async def nonareply(self, ctx, *, message):
        try:
            channel = ctx.channel
            author = ctx.author

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-3]
                    full_message = ctx.message if hasattr(ctx, "message") else message

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        await analytics.route_to_dm(full_message, channel, author, threadID, userID, False, False)
                    return

            errorEmbed = discord.Embed(description="❌ This command can only be used in ticket channels",
                                       color=discord.Color.red())
            await channel.send_message(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"+nonareply sent an error: {e}")
        

    @commands.command(name="ai_reply")
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
    

    async def find_message(self, channel, search_channel, locator, output = True):
        errorEmbed = discord.Embed(description="N/A", color=discord.Color.red())
        try:
            async for message in search_channel.history(limit=50, oldest_first=False):
                if message.embeds:
                    embed = message.embeds[0]
                    if embed.footer and locator in (embed.footer.text or ""):
                        target_message = message
                        break

        except discord.NotFound:
            if output:
                errorEmbed.description="❌ Message not found in the most recent 50 DMs to user"
                await channel.send(embed=errorEmbed)
            return

        except discord.Forbidden:
            if output:
                errorEmbed.description="❌ Unable to edit message, user may not be accepting DMs"
                await channel.send(embed=errorEmbed)
            return

        except Exception:
            if output:
                errorEmbed.description="❌ Unable to find message",
                await channel.send(embed=errorEmbed)
            return

    
    @commands.hybrid_command(name="reply_edit", description="Edit a ticket reply",
                             aliases=["edit"])
    @app_commands.describe(reply_id="The message ID of the ticket reply")
    @app_commands.describe(new_content="The new content of the ticket reply")
    @checks.is_guild()
    @checks.is_user()
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
                    userID = id_list[-3]

                    if (len(new_content) > 4000):
                        errorEmbed.description=("❌ Content must be at most 4000 characters. Note that "
                                                "channel links add ~70 additional characters each")
                        await ctx.send(embed=errorEmbed)
                        return
                    
                    gif_links = re.findall(r'https?://[^\s)]+', new_content, flags=re.IGNORECASE)
                    gif = None

                    for link in gif_links:
                        gif_candidate = await self.bot.helper.convert_to_direct_gif(link)
                        if gif_candidate:
                            gif = gif_candidate
                            break
                    
                    member = await self.bot.cache.get_guild_member(guild, userID)
                    if member is None:
                        errorEmbed.description=("❌ User not found, if this command fails again the user "
                                                "does not exist (or Discord's API is down)")
                        await ctx.send(embed=errorEmbed)
                        return
                
                    dm_channel = user.dm_channel or await user.create_dm()
                    thread = await self.bot.cache.get_channel(threadID)
                    target_message = None
                    if dm_channel:
                        target_message = await self.find_message(channel, dm_channel, reply_id)
                    else:
                        errorEmbed.description="❌ Could not create a DM channel with the user"
                        await ctx.send(embed=errorEmbed)
                        return

                    if target_message is not None:
                        if target_message.embeds:
                            embed = target_message.embeds[0]
                            embed.description=new_content
                            embed.set_image(url=gif)

                            await target_message.edit(embed=embed)

                            if thread is not None:
                                thread_message = await self.find_message(channel, thread, reply_id, False)
                                if thread_message.embeds:
                                    embed = thread_message.embeds[0]
                                    embed.description=new_content
                                    embed.set_image(url=gif)

                                    await thread_message.edit(embed=embed)
                    else:
                        return
                    


                    if len(new_content) > 1024:
                        new_content = new_content[:1021] + "..."

                    if len(old_content) > 1024:
                        old_content = old_content[:1021] + "..."

                    successEmbed = discord.Embed(description=f"✅ **Updated ticket reply to <@{user.id}> ({user.name})**",
                                                color=discord.Color.green())
                    successEmbed.add_field(name="Old Message", value=new_content, inline=False)
                    successEmbed.add_field(name="New Message", value=old_content, inline=False)
                    await ctx.send(embed=successEmbed)
                    return
            
            await ctx.send(embed=errorEmbed)

        except Exception as e:
            logger.exception(f"reply_edit error: {e}")
            raise BotError(f"/reply_edit sent an error: {e}")


    @commands.command(name="close", description="Close the current ticket, with an optional reason", 
                             aliases=["c"])
    @checks.is_guild()
    @checks.is_user()
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
                    userID = id_list[-3]

                    self.bot.channel_status.remove_timer(ticket_channel.id)
                    state = await close_ticket(self.bot, ticket_channel, closer, userID, guild.id, text, None)
            
                    if not state:
                        await ticket_channel.send(embed=errorEmbed)
                        
                    return

            errorEmbed.description=("❌ This command can only be used in ticket channels")
            await ticket_channel.send(embed=errorEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/close sent an error: {e}")
        

    @commands.command(name="aclose", description="Close the current ticket anonymously, with an optional reason", 
                             aliases=["ac"])
    @checks.is_guild()
    @checks.is_user()
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
                    userID = id_list[-3]

                    self.bot.channel_status.remove_timer(ticket_channel.id)
                    state = await close_ticket(self.bot, ticket_channel, closer, userID, guild.id, text, True)
            
                    if not state:
                        await ticket_channel.send(embed=errorEmbed)
                        
                    return

            errorEmbed.description=("❌ This command can only be used in ticket channels")
            await ticket_channel.send(embed=errorEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/aclose sent an error: {e}")
        

    @commands.command(name="nonaclose", description="Close the current ticket NON-anonymously, with an optional reason", 
                             aliases=["nac"])
    @checks.is_guild()
    @checks.is_user()
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
                    userID = id_list[-3]

                    self.bot.channel_status.remove_timer(ticket_channel.id)
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
    @commands.command(name="inactive", description="Mark current ticket to close after X hours of non-response", 
                             aliases=["inact"])
    @checks.is_guild()
    @checks.is_user()
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
                            end_time = now + (hours * 60)
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
                            userID = id_list[-3]
                        
                            await self.bot.channel_status.set_emoji(channel, "inactive", True)
                            self.bot.channel_status.add_timer(channelID, end_time, 
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
    @commands.command(name="active", description="Remove inactivity status from a ticket", 
                             aliases=["act"])
    @checks.is_guild()
    @checks.is_user()
    async def active(self, ctx):
        try:    
            channel = ctx.channel
            channelID = channel.id
            now = time.time()

            if (isinstance(channel, discord.TextChannel)):
                if (channel.topic):
                    if ("Ticket channel" in channel.topic):

                        state = self.bot.channel_status.remove_timer(channelID)

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


    # Manually update the status of a ticket channel
    @commands.hybrid_command(name="status", description="Change the emoji status of a ticket")
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(status="Select an emoji from the defined list, or add a custom one" 
                                    " (unicode only)")
    @app_commands.choices(status=[
        app_commands.Choice(name=f"🆕 - new ticket", value="new"),
        app_commands.Choice(name=f"❗️ - pending moderator response", value="alert"),
        app_commands.Choice(name=f"⏳ - waiting for user response", value="wait"),
        app_commands.Choice(name=f"🔎 - under review", value="review")])

    async def status(self, ctx, status: discord.app_commands.Choice[str]):
        try:    
            channel = ctx.channel
            emoji_name = status.name
            emoji_str = status.value

            result = await self.bot.channel_status.set_emoji(channel, emoji_str, True)

            statusEmbed = discord.Embed(description=f"Channel status set to **{emoji_name}**."
                                        "(*Please wait up to 5 minutes for edits to appear*)",
                                        color=discord.Color.green())
            if not result:
                statusEmbed.description=(f"Failed to set channel status to {emoji_str}, current "
                                         "or pending status is already set as this")
                statusEmbed.color=discord.Color.red()
            await channel.send(embed=statusEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/status sent an error: {e}")
        

    @commands.hybrid_command(name="ticket_button", description="Creates a button users can click to open a ticket via DMs")
    @checks.is_guild()
    @checks.is_admin()
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
