import discord
import asyncio
from discord.ext import commands
from roblox_data.helpers import *
from utils import emojis, checks
from utils.logger import *

SERVER_TO_GAME_ID = {
    1196293227976863806: 5422546686
}

class Analytics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.processing_queue = asyncio.Queue()


    async def cog_load(self):
        logger.log("SYSTEM", "------- CATCHING BACKLOG -----------------")
        await self.catch_modmail_backlog()
        await self.process_queue()


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
            timestamp = message.created_at
            format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")

            priority_values = [-1,-1]
            game_type = SERVER_TO_GAME_ID.get(guild.id, 0)

            if (game_type != 0):
                priority_values = await get_priority(game_type, guild.id, openID)

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
                NULL,
                {priority_values[0]},
                {priority_values[1]});
                """
            await self.bot.data_manager.execute_query(query, False)
            await asyncio.sleep(0.5)

            # Check if associated ticket channel exists, if not assume ticket has already closed
            ticket_channel = None
            for channel in guild.channels:
                if (((guild.get_member(int(openID))).name).replace("_", "").replace(".", "") in channel.name):
                    ticket_channel = channel

            if ticket_channel is not None:
                ticket_channelID = ticket_channel.id                         
                ticket_channel_timestamp = ticket_channel.created_at

                # Check that found channel shares creation time (within one minute), if not assume this channel belongs to a different ticket
                difference = abs((timestamp - ticket_channel_timestamp).total_seconds())
                if difference <= 60:
                    await self.bot.data_manager.add_ticket(ticket_channelID, message.id)
                    await self.bot.channel_status.set_emoji(ticket_channel, "new")
                    await message.add_reaction(emojis.mantis)

                else:
                    logger.debug(f"Attempted to match incorrect channel ({ticket_channelID}) to modmail log 'New Ticket' message, ticket must have already closed")
                    await message.add_reaction(emojis.mantis)
                    pass
            else:
                logger.debug("Ticket channel is already closed")
                await message.add_reaction(emojis.mantis)
                pass
            if (status == 'good'):
                logger.success(f"*** Processed open modmail ticket (Message ID: {message.id}) GOOD DATA ***")
            else:
                logger.warning(f"*** Processed open modmail ticket (Message ID: {message.id}) BAD DATA ***")

        except Exception as e:
            logger.exception(f"Error processing caught modmail ticket: {e}")


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
                closeID = guild.get_member_named(closeName).id

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
                if not err:
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
                    await message.add_reaction(emojis.mantis)
                    
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
        if (isinstance(message.channel, discord.DMChannel) or not message.guild):
            return
        # Check to ensure Mantid doesnt store its own messages
        if (message.author.id == 1304609006379073628):
            return

        this_channel = message.channel
        this_channelID = this_channel.id
        this_channel_catID = message.channel.category_id

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
                                logger.debug("Modmail DM message received")
                            
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
                                authorID = guild.get_member_named(author_username).id
                                logger.debug(f"Modmail bot sent message from {author_username}, {authorID}")

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
                                logger.debug(f"Modmail channel {this_channel.name} ({this_channelID}) closed")
                                await self.log_closed_ticket(message, modmail_messageID)
                                # None argument indicates deleting channel from status queue
                                await self.bot.channel_status.set_emoji(channel, None)

                            elif (message.content.startswith(("=r ", "=reply ", "=ar ", "=areply ", "=air", "=aireply", 
                                                             "=s ", "=snippet ", "=as ", "=asnippet "))):
                                pass

                            else: 
                                logger.debug(f"Chatting message in ticket {this_channel.name}")
                                # Store chatting message, label it as such
                                await self.bot.data_manager.add_ticket_message(messageID, 
                                                                               modmail_messageID, 
                                                                               this_channelID, 
                                                                               this_authorID, 
                                                                               format_time, 
                                                                               "Discussion")
                        else:
                            pass
                            # Message to be sent by Modmail (IGNORE)
                else:
                    logger.debug("Ticket channel message NOT within a logged ticket")
        else: 
            # Calls if message is from the Modmail bot in a #modmail-log channel
            if (message.author.id == 575252669443211264):
                    if message.embeds:
                        await self.process_modmail(message, False)


async def setup(bot):
    await bot.add_cog(Analytics(bot))