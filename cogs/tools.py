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


async def close_ticket(bot, ticket_channel, closer, reason, anon):
    try:
        closingEmbed = discord.Embed(description="Closing ticket...",
                                         color=discord.Color.blue())
        await ticket_channel.send(embed=closingEmbed)
        await bot.channel_status.set_emoji(ticket_channel, None)
        await ticket_channel.delete(reason="Ticket channel closed")
        
        guild = ticket_channel.guild
        id_list = (ticket_channel.topic).split()
        threadID = id_list[-1]
        dm_channelID = id_list[-2]
        userID = id_list[-3]
        opener = None
        closerID = None
        closerName = None
        config = await bot.data_manager.get_or_load_config(guild.id)

        if config is None:
            # FIXME
            return False

        if anon is None:
            if (config["anon"] == 'true'):
                anon = True
            else:
                anon = False

        if closer is None:
            closerID = -1
            closerName = "Inactive"
        else:
            closerID = closer.id
            closerName = closer.name
        
        closing = config["closing"]
        logID = config["logID"] 
        log_channel = await bot.cache.get_channel(logID)
        thread = await bot.cache.get_channel(threadID)  
        opener = await bot.cache.get_user(userID)
        dm_channel = opener.dm_channel or await opener.create_dm()

        await bot.data_manager.close_ticket(guild.id, opener.id, closerID, closerName)
        await bot.data_manager.delete_user_ticket(opener.id, guild.id)
                
        closeLogEmbed = discord.Embed(title=f"Ticket Closed", description=reason, 
                                color=discord.Color.red())
        closeLogEmbed.timestamp = datetime.now(timezone.utc)

        await bot.data_manager.flush_messages_v2()
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

        if closer is not None:
            name = f"{closer.name} | {closer.id}"
            url = None
            if anon:
                name += " (Anonymous)"
            if closer.avatar:
                url = closer.avatar.url
            closeLogEmbed.set_author(name=name, icon_url=url)

            if not anon:
                if (closer.avatar):
                    closeUserEmbed.set_author(name=f"{closer.name} | {closer.id}", icon_url=closer.avatar.url)
                else:
                    closeUserEmbed.set_author(name=f"{closer.name} | {closer.id}")

        try:
            await dm_channel.send(embed=closeUserEmbed)
            await send_closing(bot, guild, dm_channel, ticket_channel.id, thread.id, opener, closing)
        except Exception:
            logger.exception("Failed to DM closing messages to a user")
            pass

        await thread.send(embed=closeLogEmbed)
        await log_channel.send(embed=closeLogEmbed)
        await thread.edit(archived=True, locked=True)
        return True
    
    except Exception as e:
            print(f"close_ticket sent an error: {e}")
            logger.exception(e)


async def send_closing(bot, guild, dm_channel, channelID, threadID, user, closing_text):
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
        

    @commands.hybrid_command(name="reply", description="Send a reply in the current ticket", aliases=["r"])
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(message="The content of your reply")
    @app_commands.describe(anon="Whether your message is anonymous or not (default is not)")
    async def reply(self, ctx, *, message, anon: bool = False):
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
                        await analytics.route_to_dm(full_message, channel, author, threadID, userID, anon, False)
                    return

            errorEmbed = discord.Embed(title="", 
                                       description="❌ This command can only be used in ticket channels.",
                                       color=discord.Color.red())
            await channel.send_message(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"/reply sent an error: {e}")
        

    @commands.hybrid_command(name="areply", description="Send an anonymous reply in the current ticket", aliases=["ar"])
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(message="The content of your reply")
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

            errorEmbed = discord.Embed(title="", 
                                       description="❌ This command can only be used in ticket channels.",
                                       color=discord.Color.red())
            await channel.send_message(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"/areply sent an error: {e}")
        

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
    

    @commands.hybrid_command(name="close", description="Close the current ticket, with an optional reason", aliases=["c"])
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(reason="Reason for closing the ticket. This will be shared with the ticket opener")
    @app_commands.describe(anon="Toggle if closing is anonymous or not (default is per server)")
    async def close(self, ctx, *, reason: str = "No reason provided", anon: bool = None):
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
                    state = await close_ticket(self.bot, ticket_channel, closer, reason, anon)
            
                    if not state:
                        await ctx.reply(embed=errorEmbed)
                        
                    return

            errorEmbed.description=("❌ This command can only be used in ticket channels.")
            await ctx.reply(embed=errorEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/close sent an error: {e}")
        

    @commands.hybrid_command(name="aclose", description="Close the current ticket anonymously, with an optional reason", aliases=["ac"])
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(reason="Reason for closing the ticket. This will be shared with the ticket opener")
    async def aclose(self, ctx, *, reason: str = "No reason provided"):
        try:
            ticket_channel = ctx.channel
            closer = ctx.author
            state = None

            errorEmbed = discord.Embed(title="", 
                                       description=("❌ Error closing ticket. Please contact a"
                                                    " server admin with this error."),
                                       color=discord.Color.red())

            if (ticket_channel.topic):
                if ("Ticket channel" in ticket_channel.topic):
                    state = await close_ticket(self.bot, ticket_channel, closer, reason, True)
            
                    if not state:
                        await ctx.reply(embed=errorEmbed)
                        
                    return

            errorEmbed.description=("❌ This command can only be used in ticket channels.")
            await ctx.reply(embed=errorEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/aclose sent an error: {e}")
    

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
                            
                            result = await self.bot.channel_status.set_emoji(channel, "inactive", True)
                            statusEmbed = discord.Embed(title="", 
                                            description=f"Status set to **inactive** 🕓 for {hours} hour(s).\n"
                                                        f"This ticket will **close** in <t:{int(end_time)}:R> "
                                                        "(alotting up to 1 minute of potential delay)",
                                                        color=discord.Color.green())
                            
                            if not result:
                                statusEmbed.description=(f"Failed to change status to **inactive** 🕓, "
                                                        "use `+active` to remove current inactive state")
                                statusEmbed.color=discord.Color.red()
                                await ctx.reply(embed=statusEmbed)
                                return
                            
                            self.bot.channel_status.add_timer(channelID, end_time)
                            await self.bot.data_manager.save_timers_to_redis()

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
        

    # Set a ticket as inactive for a period of time, then mark to close
    # Remove inactive / close marker if the user responds
    @commands.hybrid_command(name="active", description="Remove inactivity status from a ticket")
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
                            await ctx.send(embed=errorEmbed, ephemeral=True)
                            return
                        else:
                            await self.bot.data_manager.save_timers_to_redis()
                            successEmbed = discord.Embed(title="", 
                                            description=f"Removed **inactive** timer, status set to **waiting**",
                                                        color=discord.Color.green())
                            result = await self.bot.channel_status.set_emoji(channel, "wait", True)
                            await ctx.reply(embed=successEmbed)
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
