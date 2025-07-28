import discord
import asyncio
import time
import os
import io
import re
from discord.ext import commands
from datetime import datetime, timezone
from roblox_data.helpers import *
from classes.error_handler import *
from classes.embeds import *
from classes.ticket_creator import TicketSelectView
from utils import emojis
from utils.logger import *

SERVER_TO_GAME = {
    714722808009064492: ("Creatures of Sonaria", 1831550657, os.getenv("COS_KEY")),
    346515443869286410: ("Dragon Adventures", 1235188606, os.getenv("DA_KEY")),
    1196293227976863806: ("Horse Life", 5422546686, os.getenv("HL_KEY"))}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 20MB in bytes


class MessageReceivedButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # no timeout needed
        self.add_item(discord.ui.Button(label="Send a message to reply!", style=discord.ButtonStyle.blurple, disabled=True))


class Analytics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.processing_queue = asyncio.Queue()


    async def cog_load(self):
        # refresh queue
        logger.log("SYSTEM", "------- CATCHING BACKLOG -----------------")
        await self.catch_modmail_backlog()
        await self.process_queue()

    ### NOTE
    ### Modmail System Development --> Message event handling functions
    ### NOTE

    async def bot_dm(self, message: discord.Message):
        try:
            channel = message.channel
            authorID = message.author.id
            tickets = await self.bot.data_manager.get_or_load_user_tickets(authorID)

            # Prompt to open a ticket
            if tickets is None:
                startEmbed = discord.Embed(title="Open a Ticket",
                                        description="Click the **\"Open a Ticket\"** button in a server you "
                                                    "share with this bot to open a ticket!\n\nAlternatively, "
                                                    "use the `/create_ticket` command in this DM channel to open "
                                                    "a ticket with a selected server. You must be a member of the "
                                                    "server you wish to open a ticket with.",
                                        color=discord.Color.blue())
                # startEmbed = discord.Embed(title="Open a Ticket",
                #                         description="Type `/create_ticket` in this channel to open a ticket."
                #                         f"\n\n{self.bot.user.name} needs to know what servers you are in to open a ticket. "
                #                         "If you have not verified your servers yet: [CLICK HERE](https://x.com)",
                #                         color=discord.Color.blue())
                await channel.send(embed=startEmbed)

            # Route message to open ticket
            elif (len(tickets) == 1):
                ticket = tickets[0]
                guildID = ticket["guildID"]
                channelID = ticket["channelID"]
                await self.route_to_server(message, guildID, channelID)

            # Selection menu for where to route ticket message
            elif (len(tickets) > 1):
                ticketEmbed = discord.Embed(title="❗️You Have Multiple Tickets Open, Choose Your Message Destination",
                                        description="Use the dropdown menu to select which server to send your message to. "
                                        "These are servers you **currently have an open ticket with**.\n\n"
                                        "If you would like to create a new ticket with a different server, use `/create_ticket`",
                                        color=discord.Color.blue())
                view = TicketSelectView(self.bot, tickets, message)
                view_message = await channel.send(embed=ticketEmbed, view=view)
                view.message = view_message

        except Exception as e:
            logger.exception(f"bot_dm sent an error: {e}")


    async def route_to_server(self, message: discord.Message, guildID: int, channelID: int):
        try:
            errorEmbed = discord.Embed(description="❌ You are blacklisted from sending messages "
                                       "to this server.",
                                       color=discord.Color.red())
            # Check blacklist
            author = message.author
            entry = await self.bot.data_manager.get_or_load_blacklist_entry(guildID, author.id)
            if entry is not None:
                await message.channel.send(embed=errorEmbed)
                return

            guild = self.bot.get_guild(guildID)
            if guild is None:
                errorEmbed.description=("❌ I could not find the server you are trying to contact. "
                                        "Please try again later. If this error persists, then I am "
                                        "not in that server.")
                await message.channel.send(embed=errorEmbed)
                return
            
            member = await self.bot.cache.get_guild_member(guild, author.id)
            if member is None: 
                errorEmbed.description=("❌ You are not in the server you are trying to contact. Please "
                                        "rejoin the server before attempting to send messages there.\n\n"
                                        "If you ARE in the server, please re-try sending your message. "
                                        "Discord API issues may prevent your messages from being sent.")
                await message.channel.send(embed=errorEmbed)
                return
            
            server_channel = await self.bot.cache.get_channel(channelID)
            if server_channel is None:
                errorEmbed.description=("❌ Could not find your ticket channel in this server. "
                                        "Please contact staff another way if this error persists.")
                await message.channel.send(embed=errorEmbed)
                return
                
            id_list = (server_channel.topic).split()
            threadID = id_list[-1]
            guild = server_channel.guild
            timestamp = datetime.now(timezone.utc)
            format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            snapshot_flag = False
            content = None

            if message.type.name == "FORWARD":
                snapshots = getattr(message, "message_snapshots", None)
                if snapshots:
                    snapshot_flag = True
                    snapshot = snapshots[0].message
                    content = snapshot.content
                else:
                    errorEmbed.description=("❌ Failed to process forwarded message. "
                                            "Send the message via copy-paste instead.")
                    await message.channel.send(embed=errorEmbed)
                    return
            else:
                content = message.content

            if content is None:
                errorEmbed.description=("❌ Failed to read forwarded message content. "
                                        "Send the message via copy-paste instead.")
                await message.channel.send(embed=errorEmbed)
                return
            
            text = await self.bot.helper.convert_mentions(content, guild)

            # Check if over 4000 characters
            if len(text) > 4000:
                errorEmbed.description=("❌ Message must be less than 4000 characters. Note that "
                                        "channel links add ~70 additional characters each.")
                await message.channel.send(embed=errorEmbed)
                return

            # gif_links = re.findall(r'https?://[^\s)]+', text, flags=re.IGNORECASE)
            # gif = None

            # for link in gif_links:
            #     gif_candidate = await self.bot.helper.convert_to_direct_gif(link)
            #     if gif_candidate:
            #         gif = gif_candidate
            #         break

            # Process any attachments
            attachments = []
            final_attachments = []
            raw_files = []  # <-- store raw data
            files = []
            fileMessage = None
            fileEmbed = discord.Embed(title="", 
                                    description="**Processing files...**\n"
                                    "Please note that image / video files may not send if they are too "
                                    "large (>10MB). For the fastest processing, upload large files to "
                                    "hosting websites and share links to the uploads instead.",
                                    color=discord.Color.blue())
            skipped_files = False
            if message:
                if snapshot_flag:
                    attachments = message.message_snapshots[0].message.attachments
                else:
                    attachments = message.attachments

                if len(attachments) > 0:
                    fileMessage = await message.channel.send(embed=fileEmbed)

                total_size = 0
                for file in attachments:
                    if file.size + total_size > MAX_FILE_SIZE:
                        skipped_files = True
                        continue
                    else:
                        final_attachments.append(file.url)
                    saved_file = io.BytesIO()
                    await file.save(saved_file)
                    raw_files.append((saved_file.getvalue(), file.filename))  # store raw bytes + filename
                    total_size += file.size

            if len(text) == 0 and len(final_attachments) == 0:
                emptyEmbed = discord.Embed(description="❌ Message not sent, you cannot send an empty message.",
                                           color=discord.Color.red())
                await message.channel.send(embed=emptyEmbed)
                return

            replyEmbed = discord.Embed(title="Message Sent", 
                                    description=text,
                                    color=discord.Color.green())
            replyEmbed.timestamp = datetime.now(timezone.utc)
            # Add attachment URLs to embed
            for count, url in enumerate(final_attachments, start=1):
                replyEmbed.add_field(name=f"Attachment {count}", value=url, inline=False)

            if guild.icon:
                replyEmbed.set_footer(text=guild.name, icon_url=guild.icon.url)
            else:
                replyEmbed.set_footer(text=guild.name)

            # Later, when sending:
            files = [discord.File(io.BytesIO(data), filename=filename) for data, filename in raw_files]
            try:
                sent_message = await message.channel.send(embed=replyEmbed, files=files)
            except Exception:
                await message.add_reaction("❌")
                return

            if skipped_files:
                skipEmbed = discord.Embed(description="⚠️ Some attachments were skipped for being too "
                                          "large or exceeding the total file size limit (10MB).", 
                                          color=discord.Color.yellow())
                await message.channel.send(embed=skipEmbed)

            if fileMessage is not None:
                await fileMessage.delete()

            sendEmbed = discord.Embed(title="Message Received", 
                                    description=text,
                                    color=discord.Color.green())
            sendEmbed.timestamp = datetime.now(timezone.utc)
            # Add attachment URLs to embed
            for count, url in enumerate(final_attachments, start=1):
                sendEmbed.add_field(name=f"Attachment {count}", value=url, inline=False)
            sendEmbed.set_footer(text=f"{author.name} | {author.id}", icon_url=(author.avatar and author.avatar.url) or author.display_avatar.url)

            files = [discord.File(io.BytesIO(data), filename=filename) for data, filename in raw_files]
            try:
                await server_channel.send(embed=sendEmbed, files=files)
            except Exception:
                errorEmbed.description=("❌ Failed to send message to server. Please try again.")
                await message.channel.send(embed=errorEmbed)
                return

            thread = await self.bot.cache.get_channel(threadID)
            
            files = [discord.File(io.BytesIO(data), filename=filename) for data, filename in raw_files]
            try:
                await thread.send(embed=sendEmbed, files=files, allowed_mentions=discord.AllowedMentions(users=False))
            except Exception:
                pass

            await self.bot.data_manager.add_ticket_message(sent_message.id, 
                                                            None, 
                                                            message.channel.id, 
                                                            author.id, 
                                                            format_time, 
                                                            "Received", True)
            await self.bot.channel_status.remove_timer(server_channel.id)
            await self.bot.channel_status.set_emoji(server_channel, "alert")

        except Exception as e:
            await message.add_reaction("❌")
            logger.exception(f"route_to_server sent an error: {e}")


    async def staff_message(self, message: discord.Message, anon: bool = None):
        channel = message.channel
        author = message.author
        id_list = (channel.topic).split()
        threadID = id_list[-1]
        userID = id_list[-2]
        
        # Process message to ticket opener
        await self.route_to_dm(message, channel, author, threadID, userID, anon, False)


    async def route_to_dm(self, message, channel, author, threadID: int, userID: int, 
                          anon: bool = None, snippet: bool = None):
        try:
            member = None
            guild = channel.guild
            errorEmbed = discord.Embed(description="❌ Ticket opener is no longer in this server. "
                                       "Use `+close [reason]` to close this ticket.",
                                       color=discord.Color.red())
            member = await self.bot.cache.get_guild_member(guild, userID)
            if member is None:
                try:
                    member = await asyncio.wait_for(guild.fetch_member(userID), timeout=1)
                    if member is not None:
                        await self.bot.cache.store_guild_member(guild.id, member)
                except discord.NotFound:
                    await channel.send(embed=errorEmbed)
                    return
                except Exception:
                    errorEmbed.description="❌ Error fetching ticket opener. Please try again shortly."
                    await channel.send(embed=errorEmbed)
                    return
            
            await self.bot.cache.store_guild_member(guild.id, author)

            # Check if blacklisted
            entry = await self.bot.data_manager.get_or_load_blacklist_entry(guild.id, userID)
            if entry is not None:
                errorEmbed.description=("❌ Ticket opener is blacklisted. `+whitelist` them before "
                                        "attempting to send a message.")
                await channel.send(embed=errorEmbed)
                return
            
            content = message
            if isinstance(message, discord.Message):
                content = message.content

            # Clean remaining prefixes
            content = re.sub(r"^\+(?:(?:nonareply|areply|reply|nar|ar|r)\s+|\s*)", "", content, flags=re.IGNORECASE)
            content = await self.bot.helper.convert_mentions(content, guild)

            # Check if over 4000 characters
            if len(content) > 4000:
                errorEmbed.description=("❌ Message must be less than 4000 characters. Note that "
                                        "channel links add ~70 additional characters each.")
                await channel.send(embed=errorEmbed)
                return
            
            # gif_links = re.findall(r'https?://[^\s)]+', content, flags=re.IGNORECASE)
            # gif = None

            # for link in gif_links:
            #     gif_candidate = await self.bot.helper.convert_to_direct_gif(link)
            #     if gif_candidate:
            #         gif = gif_candidate
            #         break

            timestamp = datetime.now(timezone.utc)
            format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            files = []

            if anon is None:
                config = await self.bot.data_manager.get_or_load_config(guild.id)
                if config is not None:
                    if (config["anon"] == 'true'):
                        anon = True
                    else:
                        anon = False

            dm_channel = None
            try:
                dm_channel = member.dm_channel or await member.create_dm()
            except Exception:
                errorEmbed.description=("❌ Unable to find DM channel with the ticket opener. "
                                        "Please try again or close this ticket.")
                await channel.send(embed=errorEmbed)
                try:
                    member = await asyncio.wait_for(guild.fetch_member(userID), timeout=1)
                    if member is not None:
                        await self.bot.cache.store_guild_member(guild.id, member)
                except Exception:
                    pass
                return
            if dm_channel is None:
                errorEmbed.description=("❌ Unable to find DM channel with the ticket opener. "
                                        "Please close this ticket.")
                await channel.send(embed=errorEmbed)
                return

            # Process any attachments
            attachments = []
            final_attachments = []
            raw_files = [] 
            fileMessage = None
            fileEmbed = discord.Embed(title="", 
                                    description="**Processing files...**\n"
                                    "Please note that image / video files may not send if they are too "
                                    "large (>10MB). For the fastest processing, upload large files to "
                                    "hosting websites and share links to the uploads instead.",
                                    color=discord.Color.blue())
            skipped_files = False
            if isinstance(message, discord.Message):
                attachments = message.attachments

                if len(attachments) > 0:
                    fileMessage = await channel.send(embed=fileEmbed)

                total_size = 0
                for file in attachments:
                    if file.size + total_size > MAX_FILE_SIZE:
                        skipped_files = True
                        continue
                    else:
                        final_attachments.append(file.url)
                    saved_file = io.BytesIO()
                    await file.save(saved_file)
                    raw_files.append((saved_file.getvalue(), file.filename))  # store raw bytes + filename
                    total_size += file.size

            if isinstance(message, discord.Message):
                await message.delete()

            if len(content) == 0 and len(final_attachments) == 0:
                emptyEmbed = discord.Embed(description="❌ Message not sent, you cannot send an empty message.",
                                           color=discord.Color.red())
                await channel.send(embed=emptyEmbed)
                return

            receiptEmbed = discord.Embed(title=f"Message Sent [STAFF]", 
                                    description=content,
                                    color=discord.Color.blue())
            receiptEmbed.timestamp = datetime.now(timezone.utc)
            # Add attachment URLs to embed
            for count, url in enumerate(final_attachments, start=1):
                receiptEmbed.add_field(name=f"Attachment {count}", value=url, inline=False)

            name = f"{author.name} | {author.id}"
            if anon:
                name += " (Anonymous)"
        
            receiptEmbed.set_author(name=name, icon_url=(author.avatar and author.avatar.url) or author.display_avatar.url)

            if member:
                receiptEmbed.set_footer(text=f"{member.name} | {member.id}", icon_url=(member.avatar and member.avatar.url) or member.display_avatar.url)
            files = [discord.File(io.BytesIO(data), filename=filename) for data, filename in raw_files]
            sent_message = await channel.send(embed=receiptEmbed, files=files)

            if skipped_files:
                skipEmbed = discord.Embed(description="⚠️ Some attachments were skipped for being too "
                                          "large or exceeding the total file size limit (10MB).", 
                                          color=discord.Color.yellow())
                await channel.send(embed=skipEmbed)

            if fileMessage is not None:
                await fileMessage.delete()

            sendEmbed = discord.Embed(title=f"Message Received", 
                                    description=content,
                                    color=discord.Color.blue())
            sendEmbed.timestamp = datetime.now(timezone.utc)
            # Add attachment URLs to embed
            for count, url in enumerate(final_attachments, start=1):
                sendEmbed.add_field(name=f"Attachment {count}", value=url, inline=False)

            if guild.icon:
                sendEmbed.set_footer(text=f"{guild.name}", icon_url=guild.icon.url)
            else:
                sendEmbed.set_footer(text=f"{guild.name}")

            if not anon:
                sendEmbed.set_author(name=f"{author.name} | {author.id}", icon_url=(author.avatar and author.avatar.url) or author.display_avatar.url)

            files = [discord.File(io.BytesIO(data), filename=filename) for data, filename in raw_files]
            try:
                dm_message = await dm_channel.send(embed=sendEmbed, files=files, view=MessageReceivedButton())
            except Exception:
                errorEmbed.description=("❌ Unable to DM the ticket opener. Your last message was **not** sent. "
                                        "**Please try again.** If this error persists they have their DM closed or "
                                        "no longer share a server with the bot.")
                await channel.send(embed=errorEmbed)
                try:
                    member = await asyncio.wait_for(guild.fetch_member(userID), timeout=1)
                except Exception:
                    pass
                return

            thread = await self.bot.cache.get_channel(threadID)

            files = [discord.File(io.BytesIO(data), filename=filename) for data, filename in raw_files]
            try:
                thread_message = await thread.send(embed=receiptEmbed, files=files, allowed_mentions=discord.AllowedMentions(users=False))
            except Exception:
                pass

            await self.bot.data_manager.add_ticket_message(sent_message.id, 
                                                            None, 
                                                            channel.id, 
                                                            author.id, 
                                                            format_time, 
                                                            "Sent", True)
            await self.bot.channel_status.set_emoji(channel, "wait")
            await self.bot.data_manager.add_message_link(channel.id, sent_message.id, [dm_message.id, thread_message.id])

        except Exception as e:
            if isinstance(message, discord.Message):
                await message.reply("❌ An error occurred, please try again")
            logger.exception(f"got_dm sent an error: {e}")


    async def store_comment(self, message: discord.Message):
        author = message.author
        channel = message.channel
        id_list = (channel.topic).split()
        threadID = id_list[-1]

        thread = await self.bot.cache.get_channel(threadID)
        content = None
        snapshot_flag = False

        if message.type.name == "FORWARD":
            snapshots = getattr(message, "message_snapshots", None)
            if snapshots:
                snapshot_flag = True
                snapshot = snapshots[0].message
                content = snapshot.content
            else:
                return
        else:
            content = message.content

        # Process any attachments
        attachments = []
        raw_files = []  # <-- store raw data

        if message:
            if snapshot_flag:
                attachments = message.message_snapshots[0].message.attachments
            else:
                attachments = message.attachments

            total_size = 0
            for file in attachments:
                if file.size + total_size > MAX_FILE_SIZE:
                    continue
                saved_file = io.BytesIO()
                await file.save(saved_file)
                raw_files.append((saved_file.getvalue(), file.filename))  # store raw bytes + filename
                total_size += file.size

        files = [discord.File(io.BytesIO(data), filename=filename) for data, filename in raw_files]
        thread_message = await thread.send(f"**{author.name}**\n{content}\n"
                          f"-# `ID: {author.id}`", files=files, allowed_mentions=discord.AllowedMentions(users=False))
        
        await self.bot.data_manager.add_message_link(channel.id, message.id, [-1, thread_message.id])
        

    async def edit_comment(self, message):
        channel = message.channel
        author = message.author
        id_list = (channel.topic).split()
        threadID = id_list[-1]

        thread = await self.bot.cache.get_channel(threadID)

        _, thread_messageID = await self.bot.data_manager.get_linked_messages(channel.id, message.id)
        try:
            thread_message = await thread.fetch_message(thread_messageID)
        except Exception:
            pass
        if thread_message:
            await thread_message.edit(content=f"**{author.name}**\n{message.content}\n"
                                              f"-# `ID: {author.id}`")
            return
        return None
    

    async def delete_comment(self, message):
        channel = message.channel
        id_list = (channel.topic).split()
        threadID = id_list[-1]

        thread = await self.bot.cache.get_channel(threadID)

        _, thread_messageID = await self.bot.data_manager.get_linked_messages(channel.id, message.id)
        try:
            thread_message = await thread.fetch_message(thread_messageID)
        except Exception:
            pass
        if thread_message:
            await thread_message.delete()
            return
        return None


    # Populate queue with unprocessed messages
    async def catch_modmail_backlog(self):
        for guild in self.bot.guilds:
            search_monitor = [
                (channelID) for guildID, channelID, monitorType 
                in self.bot.data_manager.monitored_channels
                if (guildID == guild.id and monitorType == "Modmail log")]

            if (len(search_monitor) == 1):
                channel = guild.get_channel(int(search_monitor[0]))
                logger.log("SYSTEM", f"Scanning channel: {channel.name} in {guild.name}")
                try:
                    async for message in channel.history(limit=None, oldest_first=False):
                        if not self.has_mantis_reaction(message):
                            if (message.author.id == 575252669443211264):
                                await self.processing_queue.put(message)
                        else:
                            # Stop scanning this channel after finding the first processed message
                            break
                except Exception as e:
                        logger.error(f"Error fetching history in channel {channel.name}: {e}")


    # Check if the message has a Mantis reaction
    def has_mantis_reaction(self, message: discord.Message) -> bool:
        for reaction in message.reactions:
            if ((reaction.emoji.id == 1304887716370186330) or (reaction.emoji == "<:mantis:1304887716370186330>")):
                return True
        return False
    

    # Process all messages in the queue
    async def process_queue(self):
        # Drain the queue into a list
        items = []
        while not self.processing_queue.empty():
            items.append(await self.processing_queue.get())

        # Process items in reverse order, needed for later logic
        items.reverse()
        for message in items:
            try:
                await self.process_modmail(message, True)
            except Exception as e:
                logger.error(f"Error processing message {message.id}: {e}")
            finally:
                self.processing_queue.task_done()

    
    # Handles all potential Modmail ticket creation events
    async def process_modmail(self, message: discord.Message, isCatchup: bool):
        embed = message.embeds[0]
        title = embed.title
        if isCatchup:
            if (title == "New Ticket"):
                logger.debug("Processing open ticket with bad data")
                await self.log_open_ticket(message, "bad")

            if (title == "Ticket Closed"):
                logger.debug("Processing closed ticket with bad data")
                await self.log_closed_ticket(message, None)

        else:
            if (title == "New Ticket"):
                await self.log_open_ticket(message, "good")

            if (title == "Ticket Closed"):
                await message.add_reaction(emojis.mantis)


    # Stores opened Modmail tickets into the DB
    # Adds ticket to Redis cache if the ticket is still open
    async def log_open_ticket(self, message: discord.Message, status: str):
        try:
            guild = message.guild
            this_channel = message.channel
            this_channelID = this_channel.id
            embed = message.embeds[0]
            footer = embed.footer.text
            openID = (footer.split())[-1]
            open_name = ((footer.split())[0])[:-2]
            timestamp = message.created_at
            format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")

            # Check if associated ticket channel exists for 2 seconds, if not assume ticket has already closed
            ticket_channel = None
            start_time = time.time()
            while ((time.time() - start_time < 2) and (ticket_channel is None)):
                for channel in guild.channels:
                    if ((open_name).replace("_", "").replace(".", "") in channel.name):
                        ticket_channel = channel
                await asyncio.sleep(0.1)

            if ticket_channel is not None:
                ticket_channelID = ticket_channel.id                         
                ticket_channel_timestamp = ticket_channel.created_at

                # Check that found channel shares creation time (within one minute), if not assume this channel belongs to a different ticket
                difference = abs((timestamp - ticket_channel_timestamp).total_seconds())
                if difference <= 60:
                    await self.bot.data_manager.add_ticket(ticket_channelID, message.id)
                    await self.bot.channel_status.set_emoji(ticket_channel, "new")

                else:
                    logger.debug(f"Attempted to match incorrect channel ({ticket_channelID}) to modmail log 'New Ticket' message, ticket must have already closed")
                    pass
            else:
                logger.debug("Ticket channel is already closed")
                pass

            priority_values = [-1,-1]
            robloxID = None
            robloxUsername = None
            game_type = SERVER_TO_GAME.get(guild.id, None)

            if game_type is not None:
                robloxID, robloxUsername = await get_roblox_info(game_type, guild.id, openID)

            if game_type is not None and robloxUsername is not None:
                priority_values = await get_priority(game_type, guild.id, openID, robloxUsername)

            if not priority_values:
                priority_values = [-1,-1]

            query = f"""
                INSERT IGNORE INTO tickets VALUES 
                ({message.id}, 
                {guild.id}, 
                {this_channelID}, 
                '{format_time}', 
                NULL, 
                {openID}, 
                NULL, 
                NULL, 
                'open',
                '{status}',
                'false',
                1,
                {priority_values[0]},
                {priority_values[1]});
                """
            await self.bot.data_manager.execute_query(query, False)
            await message.add_reaction(emojis.mantis)

            if (status == 'good'):
                logger.success(f"*** Processed open modmail ticket (Message ID: {message.id}) GOOD DATA ***")
            else:
                logger.warning(f"*** Processed open modmail ticket (Message ID: {message.id}) BAD DATA ***")

        except Exception as e:
            logger.exception(f"Error processing new or caught modmail ticket: {e}")


    # Updates Modmail tickets as closed in the DB
    # Removes the ticket from the Redis cache if the ticket was still registered as open
    async def log_closed_ticket(self, message: discord.Message, modmail_messageID):
        try:   
            err = False
            guild = message.guild
            this_channelID = message.channel.id
            timestamp = message.created_at
            format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")

            if modmail_messageID is None:
                embed = message.embeds[0]
                footer = embed.footer.text
                openID = (footer.split())[-1]
                author_name = (embed.author.name).split()
                closeName = author_name[0][:-2]
                closeID = self.bot.data_manager.mod_ids.get(closeName, None)
                
                query = f"""
                    SELECT messageID FROM tickets WHERE 
                    (guildID = {guild.id}) AND 
                    (openByID = {openID}) AND 
                    (status = 'open') 
                    ORDER BY dateOpen Asc;
                    """
                result = await self.bot.data_manager.execute_query(query)

                # Check if results returned anything, if so select the oldest open ticket to associate the close with
                if len(result) != 0:
                    modmail_messageID = result[0][0]
                    if len(result) == 1:
                        logger.debug("Found one matching log in DB for a closed ticket")
                    else:
                        logger.debug("Found two or more matching open logs in DB, selected the oldest one")
                else: 
                    logger.error(f"Could not find open compliement to close embed {message.id}, sent on {format_time}")
                    err = True

                # Update ticket at modmail_messageID
                if not err and closeID:
                    query = f"""
                        UPDATE tickets SET 
                        dateClose = '{format_time}', 
                        closeByID = {closeID}, 
                        closeByUN = '{closeName}', 
                        status = 'closed',
                        flag = 'bad' WHERE (messageID = {modmail_messageID});
                        """
                    await self.bot.data_manager.execute_query(query, False)

                    # Remove from Redis if ticket is still present
                    await self.bot.data_manager.remove_ticket_modmail(modmail_messageID)
                    logger.warning(f"*** Processed closed modmail ticket (Message ID: {modmail_messageID}) BAD DATA ***")
                    #
                    
                else:
                    logger.error(f"Close embed not loggable")
                    await message.add_reaction(emojis.mantis)
            
            else:
                closeID = message.author.id
                closeName = message.author.name
                query = f"""
                    UPDATE tickets SET 
                    dateClose = '{format_time}', 
                    closeByID = {closeID}, 
                    closeByUN = '{closeName}', 
                    status = 'closed' WHERE (messageID = {modmail_messageID});
                    """
                await self.bot.data_manager.execute_query(query, False)
                logger.success(f"*** Processed closed modmail ticket (Message ID: {modmail_messageID}) GOOD DATA ***")
            
                # Remove from Redis 
                await self.bot.data_manager.remove_ticket(this_channelID)
                
        except Exception as e:
            logger.error(f"Error closing modmail ticket: {e}")


    # TODO add this: await self.bot.process_commands(message)
    # On-message event listener for messages in #modmail-log channels or modmail categories
    @commands.Cog.listener()
    async def on_message(self, message):
        # Temp, allows Mantid to still work (allows Modmail message processing)
        if (message.author.bot and message.author.id != 575252669443211264):
            return
        
        # Process valid commands
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        if (isinstance(message.channel, discord.DMChannel)):
            limited, retry, was_notified = self.bot.queue.check_user_action_cooldown("dm_start", message.author.id)

            if limited:
                if not was_notified:
                    self.bot.queue.user_action_cooldowns["dm_start"]["notified"][message.author.id] = True
                    errorEmbed = discord.Embed(
                        description=f"❌ You're messaging me too quickly — retry in {retry:.1f} seconds.",
                        color=discord.Color.red()
                    )
                    await message.channel.send(embed=errorEmbed)
                return

            await self.bot_dm(message)
            return
        
        this_channel = message.channel
        this_channelID = this_channel.id
        this_channel_catID = message.channel.category_id

        # check if chanel descrip is good, if so send mod message to dm
        # check permissions
        if (isinstance(this_channel, discord.TextChannel)):
            if (this_channel.topic):
                if ("Ticket channel" in this_channel.topic):
                    if (message.content.startswith("+")):
                        asyncio.create_task(self.staff_message(message, None))
                        return
                        
                    else:
                        # Process comment
                        timestamp = datetime.now(timezone.utc)
                        format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                        await self.bot.data_manager.add_ticket_message(message.id, 
                                                            None, 
                                                            this_channelID, 
                                                            message.author.id, 
                                                            format_time, 
                                                            "Discussion", True)
                        asyncio.create_task(self.store_comment(message))
                        return

        search_monitor = [
            (channelID, monitorType) for guildID, channelID, monitorType 
            in self.bot.data_manager.monitored_channels
            if (channelID == this_channelID or channelID == this_channel_catID)]

        if (len(search_monitor) == 0):
            return

        elif (len(search_monitor) == 1):
            channel = message.channel
            messageID = message.id
            guild = message.guild
            this_authorID = message.author.id
            this_authorName = message.author.name
            timestamp = message.created_at
            format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            monitor_type = ""
            monitor_type = search_monitor[0][1]

            # Check if channel is a Modmail log
            if (monitor_type == "Modmail log"):
                if (this_authorID == 575252669443211264):
                    if message.embeds:
                        await self.process_modmail(message, False)

            # Check if channel is in a tickets or overflow category
            if (monitor_type == "Tickets category" or monitor_type == "Overflow category"):

                # Check if channel is cached as a ticket
                modmail_messageID = (await self.bot.data_manager.get_ticket(this_channelID))
                if (modmail_messageID is not None):
                    if (this_authorID == 575252669443211264):
                        if message.embeds:
                            embed = message.embeds[0]

                            # Store received message (embed by Modmail bot from DM)
                            if (embed.title == "Message Received"):
                                footer = embed.footer.text
                                authorID = (footer.split())[-1]
                            
                                await self.bot.data_manager.add_ticket_message(messageID, 
                                                                               modmail_messageID, 
                                                                               this_channelID, 
                                                                               authorID, 
                                                                               format_time, 
                                                                               "Received")
                                await self.bot.channel_status.set_emoji(channel, "alert")

                            # Store sent message (embed from the Modmail bot to DM)
                            elif (embed.title == "Message Sent"):
                                author_name = (embed.author.name).split()
                                author_username = (author_name[0])[:-2]
                                authorID = self.bot.data_manager.mod_ids.get(author_username, None)

                                await self.bot.data_manager.add_ticket_message(messageID, 
                                                                               modmail_messageID, 
                                                                               this_channelID, 
                                                                               authorID, 
                                                                               format_time, 
                                                                               "Sent")
                                await self.bot.channel_status.set_emoji(channel, "wait")
                           
                            else:
                                pass
                                # Title has to be Message Received or Message Sent
                    else: 
                        # Chatting message, message to be sent by Modmail, OR =close 
                        if (message.content.startswith("=")):
                            # Chatting message or =close
                            if (message.content.startswith(("=c", "=ac"))):
                                self.bot.data_manager.mod_ids[this_authorName] = this_authorID

                                await self.log_closed_ticket(message, modmail_messageID)
                                # None argument indicates deleting channel from status queue
                                await self.bot.channel_status.set_emoji(channel, None)

                            elif (message.content.startswith(("=r ", "=reply ", "=ar ", "=areply ", "=air", "=aireply", 
                                                             "=s ", "=snippet ", "=as ", "=asnippet "))):
                                self.bot.data_manager.mod_ids[this_authorName] = this_authorID

                            else: 
                                # Store chatting message, label it as such
                                await self.bot.data_manager.add_ticket_message(messageID, 
                                                                               modmail_messageID, 
                                                                               this_channelID, 
                                                                               this_authorID, 
                                                                               format_time, 
                                                                               "Discussion")
                        else:
                            # Message to be sent by Modmail
                            self.bot.data_manager.mod_ids[this_authorName] = this_authorID
                else:
                    pass
        else: 
            # Calls if message is from the Modmail bot in a #modmail-log channel
            if (message.author.id == 575252669443211264):
                    if message.embeds:
                        await self.process_modmail(message, False)


    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        # Ignore bot edits to prevent loops
        if before.author.bot:
            return
        
        if before.content == after.content:
            return
        
        if (isinstance(before.channel, discord.TextChannel)):
            if (before.channel.topic):
                if ("Ticket channel" in before.channel.topic):
                    await self.edit_comment(after)


    @commands.Cog.listener()
    async def on_message_delete(self, message):
        # Ignore bot message deletions
        if message.author.bot:
            return
        
        if (isinstance(message.channel, discord.TextChannel)):
            if (message.channel.topic):
                if ("Ticket channel" in message.channel.topic):
                    if not (message.content.startswith("+")):
                        await self.delete_comment(message)


async def setup(bot):
    await bot.add_cog(Analytics(bot))