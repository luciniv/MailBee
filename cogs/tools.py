import discord
import time
import asyncio
import io
import re
import datetime
from discord.ext import commands
from discord import app_commands
from typing import List
from classes.error_handler import *
from classes.embeds import *
from classes.ticket_creator import DMCategoryButtonView, TicketRatingView
from utils import checks, queries
from utils.logger import *


async def close_ticket(bot, guild, ticket_channel,
                        log_channel, dm_channel, thread, 
                        closer, opener, reason, closing_text,
                        anon):
    try:
        await bot.data_manager.close_ticket(guild.id, opener.id, closer.id, closer.name)
        await bot.data_manager.delete_user_ticket(opener.id, guild.id)
        
        errorEmbed = discord.Embed(title="", description="", color=discord.Color.red())
                
        closeLogEmbed = discord.Embed(title=f"Ticket Closed", description=reason, 
                                color=discord.Color.red())
        closeLogEmbed.timestamp = datetime.now(timezone.utc)

        await bot.data_manager.flush_messages_v2()
        logger.info(f"Called flush tickets_v2")
        query = queries.closing_queries(ticket_channel.id)
        result = await bot.data_manager.execute_query(query)
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

        if (closer.avatar):
            closeLogEmbed.set_author(name=f"{closer.name} | {closer.id}", icon_url=closer.avatar.url)
        else:
            closeLogEmbed.set_author(name=f"{closer.name} | {closer.id}")

        if opener:
            if opener.avatar:
                closeLogEmbed.set_footer(text=f"{opener.name} | {opener.id}", icon_url=opener.avatar.url)
            else:
                closeLogEmbed.set_footer(text=f"{opener.name} | {opener.id}")

        closeUserEmbed = discord.Embed(title=f"Ticket Closed", description=reason, 
                                        color=discord.Color.red())
        closeUserEmbed.timestamp = datetime.now(timezone.utc)

        if guild.icon:
            closeUserEmbed.set_footer(text=guild.name, icon_url=guild.icon.url)
        else:
            closeUserEmbed.set_footer(text=guild.name)

        # Check if command was anon
        print("anon is", anon)
        if anon:
            print("closing was anon")
            name = closeLogEmbed.author.name
            closeLogEmbed.author.name = f"{name} (Anonymous)"

        else:
            if (closer.avatar):
                closeUserEmbed.set_author(name=f"{closer.name} | {closer.id}", icon_url=closer.avatar.url)
            else:
                closeUserEmbed.set_author(name=f"{closer.name} | {closer.id}")

        await dm_channel.send(embed=closeUserEmbed)

        if (len(closing_text) > 1):
            await send_closing(bot, guild, dm_channel, thread.id, opener, closing_text)

        await thread.send(embed=closeLogEmbed)
        await log_channel.send(embed=closeLogEmbed)

        await thread.edit(archived=True, locked=True)
        
        return True
    
    except Exception as e:
            print(f"close_ticket sent an error: {e}")
            logger.exception(e)


async def send_closing(bot, guild, dm_channel, threadID, user, closing_text):
    try:
        closing = closing_text.format(
            mention=f"<@{user.id}>",
            name=user.name,
            id=user.id)
    except KeyError:
        return

    closingEmbed = discord.Embed(title="Closing Message", description=closing)
    closingEmbed.timestamp = datetime.now(timezone.utc)

    if guild.icon:
        closingEmbed.set_footer(text=guild.name, icon_url=guild.icon.url)
    else:
        closingEmbed.set_footer(text=guild.name)

    view = TicketRatingView(bot=bot, guildID=guild.id, threadID=threadID)
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
                return await interaction.response.send_message("You can't use this button.", ephemeral=True)

            await self.target_channel.send(self.reply_text)
            await interaction.response.edit_message(content="✅ Reply sent.", view=None)
            self.stop()

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
        async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user != self.author:
                return await interaction.response.send_message("You can't use this button.", ephemeral=True)

            await interaction.response.edit_message(content="❌ Cancelled reply.", view=None)
            self.stop()


class Tools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        

    @app_commands.command(name="reply", description="Send a reply in the current ticket")
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(message="The content of your reply")
    @app_commands.describe(anon="Whether your message is anonymous or not (default is per server)")
    async def reply(self, interaction: discord.Interaction, message: str, anon: bool = None):
        try:
            channel = interaction.channel

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    dm_channelID = id_list[-2]
                    userID = id_list[-3]
                    guild = interaction.guild

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        await analytics.route_to_dm(None, threadID, dm_channelID, userID, anon, interaction, message)
                        await interaction.response.send_message("Reply sent", ephemeral=True)
                    return

            errorEmbed = discord.Embed(title="", 
                                       description="❌ This command can only be used in ticket channels.",
                                       color=discord.Color.red())
            await interaction.response.send_message(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"/reply sent an error: {e}")
        

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
            return f"This is a placeholder reply based on the transcript of {len(transcript.splitlines())} lines."
    

    @commands.hybrid_command(name="close", description="Close the current ticket, with an optional reason")
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(reason="Reason for closing the ticket. This will be shared with the ticket opener")
    @app_commands.describe(anon="Toggle if closing is anonymous or not (default is per server)")
    async def close(self, ctx, reason: str = "No reason provided", anon: bool = None):
        try:
            ticket_channel = ctx.channel
            guild = ctx.guild
            closer = ctx.author
            state = None

            errorEmbed = discord.Embed(title="", 
                                       description=("❌ Error closing ticket. Please contact a"
                                                    " server admin with this error."),
                                       color=discord.Color.red())

            if (ticket_channel.topic):
                if ("Ticket channel" in ticket_channel.topic):

                    closingEmbed = discord.Embed(description="Closing ticket...",
                                         color=discord.Color.blue())
                    await ctx.channel.send(embed=closingEmbed)
                    await self.bot.channel_status.set_emoji(ticket_channel, None)
                    await ticket_channel.delete(reason="Ticket channel closed")

                    # FIXME add some more error checking later
                    id_list = (ticket_channel.topic).split()
                    threadID = id_list[-1]
                    dm_channelID = id_list[-2]
                    userID = id_list[-3]
                    opener = None

                    config = await self.bot.data_manager.get_or_load_config(guild.id)

                    if config is None:
                        # FIXME
                        return False
                    
                    closing = config["closing"]
                    logID = config["logID"] 
                    log_channel = guild.get_channel(logID)

                    if not log_channel:
                        try:
                            log_channel = await asyncio.wait_for(guild.fetch_channel(logID), timeout=1)
                        except Exception as e:
                            print("log channel fetch failed, must not exist")
                            return False

                    dm_channel = guild.get_channel(dm_channelID)
                    if not dm_channel:
                        try:
                            dm_channel = await asyncio.wait_for(self.bot.fetch_channel(dm_channelID), timeout=1)
                        except Exception as e:
                            print("dm channel fetch failed, must not exist")
                            return False
                        
                    thread = self.bot.get_channel(threadID)
                    if not thread:
                        logger.debug("thread via fetch")
                        try:
                            thread = await asyncio.wait_for(self.bot.fetch_channel(threadID), timeout=1)
                        except Exception as e:
                            print("thread fetch failed, must not exist")
                            return
                    logger.debug("got the thread")
                    
                    try:
                        print("FETCHING MEMBER", userID)
                        opener = await asyncio.wait_for(guild.fetch_member(int(userID)), timeout=1)
                    except Exception as e:
                        print("user fetch failed, oops")
                        pass
                
                    state = await close_ticket(self.bot, guild, ticket_channel,
                                              log_channel, dm_channel, thread, 
                                              closer, opener, reason, closing, 
                                              anon)
            
                    if not state:
                        await ctx.reply(embed=errorEmbed)
                        
                    return

            errorEmbed.description=("❌ This command can only be used in ticket channels.")
            await ctx.reply(embed=errorEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/close sent an error: {e}")
    

    # Set a ticket as inactive for a period of time, then mark to close
    # Remove inactive / close marker if the user responds
    @commands.hybrid_command(name="inactive", description="Mark current ticket to close after X hours of non-response")
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(hours="(Default is 24) Hours to wait before marking to close")
    async def inactive(self, ctx, hours: int = 24):
        try:    
            channel = ctx.channel
            channelID = channel.id
            now = time.time()

            if (isinstance(channel, discord.TextChannel)):
                if (channel.topic):
                    if ("Ticket channel" in channel.topic):
                        if ((hours < 1) or (hours > 72)):
                            errorEmbed = discord.Embed(title="", 
                                                description="❌ Hours must be between 1 to 72 (inclusive)", 
                                                color=discord.Color.red())
                            await ctx.send(embed=errorEmbed, ephemeral=True)
                            return
                        else:
                            end_time = now + (hours * 3600)
                            result = await self.bot.channel_status.set_emoji(channel, "inactive")
                            statusEmbed = discord.Embed(title="", 
                                            description=f"Status set to **inactive** 🕓 for {hours} hours(s).\n"
                                                        f"This ticket will **close** in <t:{int(end_time)}:R> "
                                                        "(alotting up to 5 minutes of potential delay)",
                                                        color=discord.Color.green())
                            
                            if not result:
                                statusEmbed.description=(f"Failed to change status to **inactive** 🕓, "
                                                        "please try again later")
                                statusEmbed.color=discord.Color.red()
                                await ctx.reply(embed=statusEmbed)
                                return
                            
                            # self.bot.channel_status.timers[channelID] = end_time
                            # await self.bot.data_manager.save_timers_to_redis()

                            await ctx.reply(embed=statusEmbed)
                            return

            errorEmbed = discord.Embed(title="", 
                                description="❌ Channel is not a ticket", 
                                color=discord.Color.red())
            await ctx.send(embed=errorEmbed, ephemeral=True)
            return

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/inactive sent an error: {e}")


    # Manually update the status of a ticket channel
    @commands.hybrid_command(name="status", description="Change the emoji status of a ticket")
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(status="Select an emoji from the defined list, or add a custom one" 
                                    " (unicode only)")
    @app_commands.choices(status=[
        app_commands.Choice(name=f"🆕 - new ticket", value="new"),
        app_commands.Choice(name=f"❗️ - pending moderator response", value="alert"),
        app_commands.Choice(name=f"⏳ - waiting for user response", value="wait")])
    @app_commands.describe(emoji="Enter a default Discord emoji (only works without status choice)")
    async def status(self, ctx, status: discord.app_commands.Choice[str] = None, emoji: str = None):
        try:    
            status_flag = False
            channel = ctx.channel
            emoji_name = None
            emoji_str = None

            if status is None and emoji is None:
                errorEmbed = discord.Embed(title=f"", 
                                    description="❌ You must select a status or provide an emoji", 
                                    color=0xFF0000)

                await ctx.send(embed=errorEmbed, ephemeral=True)
                return

            # Prioritizes status selection over custom emojis
            if status is not None:
                status_flag = True
                emoji_name = status.name
                emoji_str = status.value

            if emoji_str is None:
                if (self.bot.channel_status.check_unicode(emoji)):
                    emoji_str = emoji

            result = await self.bot.channel_status.set_emoji(channel, emoji_str, True)

            # Fix for outputting readable explanation of what the emoji is for
            if status_flag:
                emoji_str = emoji_name

            statusEmbed = Embeds(self.bot, title="", 
                                description=f"Channel status set to {emoji_str}\n*Please wait up to 5 minutes for edits to appear*")

            if not result:
                statusEmbed.description=f"Failed to set channel status to {emoji_str}, current or pending status is already set as this"
                statusEmbed.color=0xFF0000

            await ctx.reply(embed=statusEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/status sent an error: {e}")
        

    @commands.hybrid_command(name="ticket_button", description="Creates a button users can click to open a ticket via DMs")
    @commands.has_permissions(administrator=True)
    async def post_ticket_button(self, ctx: commands.Context):
        guild_id = ctx.guild.id

        # Load ticket types for this guild (from your database/cache)
        types = await self.bot.data_manager.get_or_load_guild_types(guild_id)

        if not types:
            await ctx.send("❌ This server doesn't have any ticket types configured.")
            return

        view = DMCategoryButtonView(self.bot)
        ticketEmbed=discord.Embed(title="Need Support?", 
                                  description="Click the button below to open a support ticket with staff "
                                              "in your direct messages. The bot will guide you through the process!",
                                  color=discord.Color.green())
        await ctx.channel.send(embed=ticketEmbed, view=view)
    

async def setup(bot):
    await bot.add_cog(Tools(bot))
