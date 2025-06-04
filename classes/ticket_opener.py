import discord
import asyncio
import os
from discord import Embed
from discord.permissions import PermissionOverwrite
from datetime import datetime, timezone
from typing import Dict, List
from utils.logger import *
from roblox_data.helpers import *


SERVER_TO_GAME = {
    714722808009064492: ("Creatures of Sonaria", 1831550657, os.getenv("COS_KEY")),
    346515443869286410: ("Dragon Adventures", 1235188606, os.getenv("DA_KEY")),
    1196293227976863806: ("Horse Life", 5422546686, os.getenv("HL_KEY"))
}


async def get_overwrites(guild, roles) -> Dict:
    overwrites = {
        guild.default_role: PermissionOverwrite(read_messages=False)
    }

    for role in roles:
        if role is not None:
            overwrites[role] = PermissionOverwrite(
                read_messages=True,
                read_message_history=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True
            )

    return dict(overwrites)


class TicketOpener:
    def __init__(self, bot):
        self.bot = bot

    # create ticket
    # create channel --> given category
    # storage is now viable --> given channel + whatever else
    # create and send embeds --> given destination channel 
    # (ticket channel info and submission embed)
    # (dm channel info, submission embed, greeting (if real))

    # if this returns false, failed to make the ticket
    # potentially supply context

    async def open_ticket(self, user, guild, category, typeID, dm_channelID, values, title):
        logger.debug("ticket creation started")

        # Send log embed
        log_message = await self.send_log(guild, user, title)
        logger.debug("sent opening log")

        # Create logging thread
        thread = await log_message.create_thread(name=f"Ticket {user.name} - {log_message.id}", auto_archive_duration=1440)
        logger.debug("created logging thread")

        # Create ticket channel
        channel = await self.create_ticket_channel(guild, category, user, dm_channelID, thread.id)
        logger.debug("created ticket channel")

        dm_channel = user.dm_channel or await user.create_dm()

        if channel:
            # Send opening embed, and greeting if it exists
            await self.send_opener(guild, dm_channel, user, values, title)
            logger.debug("sent opening embeds to user")

            # Send in-channel embeds
            await self.send_ticket_embeds(guild, channel, dm_channel, thread, user, values, title)
            logger.debug("sent ticket channel embeds")

            # Add new ticket to database
            await self.bot.data_manager.create_ticket(guild.id, channel.id, user.id, thread.id, typeID)
            logger.debug("added ticket to DB")
            tickets = await self.bot.data_manager.get_or_load_user_tickets(user.id, False)
            logger.debug("ticket creation done")
            return True

        else:
            print("failed to create ticket channel")
            return False
        

    async def send_log(self, guild, user, title):
            config = await self.bot.data_manager.get_or_load_config(guild.id)
            logger.debug("got config")

            if config is None:
                return
            
            logID = config["logID"] 
            log_channel = await self.bot.cache.get_channel(logID)
            logger.debug("got log channel")

            openLogEmbed = discord.Embed(title=f"New \"{title}\" Ticket", description="", 
                                        color=discord.Color.green())
            openLogEmbed.timestamp = datetime.now(timezone.utc)

            if user.avatar:
                openLogEmbed.set_footer(text=f"{user.name} | {user.id}", icon_url=user.avatar.url)
            else:
                openLogEmbed.set_footer(text=f"{user.name} | {user.id}")

            message = await log_channel.send(embed=openLogEmbed)
            return message


    async def create_ticket_channel(self, guild, category, user, dm_channelID, threadID):
        try:
            logger.warning("CALLED CREATE TICKET CHANNEL")
            # Check for any permitted roles (user or admin)
            roles = []
            permissions = await self.bot.data_manager.get_or_load_permissions(guild.id)
            print("permissions is", permissions)
            print("keys are", permissions.keys())
            for roleID in permissions.keys():
                print("roleID is", roleID)
                role = guild.get_role(roleID)
                roles.append(role)
            
            overwrites = await get_overwrites(guild, roles)
            print(overwrites)

            # FIXME check if category has space
            if (len(category.channels) > 2):
                print("overflow hit, handle eventually, modify category as needed")

            channel_name = f"{user.name}".lower().replace(".", "")
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket channel {user.id} {dm_channelID} {threadID}")

            # Set channel status
            await self.bot.channel_status.set_emoji(ticket_channel, "new")
            return ticket_channel
        
        except Exception as e:
            logger.exception(f"create channel exception: {e}")
            return None
        

    async def send_opener(self, guild, dm_channel, user, values, title):
        config = await self.bot.data_manager.get_or_load_config(guild.id)

        dmEmbed = discord.Embed(title=f"New \"{title}\" Ticket", 
                                description=f"You have opened a new ticket with {guild.name}\n\n"
                                            f"Send a message in this DM to speak to "
                                            f"the server's staff team. Run `/create_ticket` "
                                            f"to open a ticket with a different server. You may "
                                            f"only have one ticket open per server at a time.",
                                            color=discord.Color.blue())
        dmEmbed.timestamp = datetime.now(timezone.utc)

        if guild.icon:
            dmEmbed.set_footer(text=guild.name, icon_url=guild.icon.url)
        else:
            dmEmbed.set_footer(text=guild.name)

        greetingEmbed = None
        if config is not None:
            greeting_text = config["greeting"] 
            if (len(greeting_text) < 1):
                return
            
            try:
                greeting = greeting_text.format(
                    mention=f"<@{user.id}>",
                    name=user.name,
                    id=user.id)
            except KeyError:
                return

            greetingEmbed = discord.Embed(title="Greeting Message", 
                                        description=greeting,
                                        color=discord.Color.blue())
            greetingEmbed.timestamp = datetime.now(timezone.utc)

            if guild.icon:
                greetingEmbed.set_footer(text=guild.name, icon_url=guild.icon.url)
            else:
                greetingEmbed.set_footer(text=guild.name)

        submissionEmbed = await self.create_submission_embed(guild, None, values, title)

        await dm_channel.send(embed=dmEmbed)
        if greetingEmbed:
            await dm_channel.send(embed=greetingEmbed)
        await dm_channel.send(embed=submissionEmbed)


    async def create_submission_embed(self, guild, member, values, title):
        submissionEmbed = discord.Embed(title=f"\"{title}\" Form Submission", color=discord.Color.green())
        submissionEmbed.timestamp = datetime.now(timezone.utc)

        for label, answer in values.items():
            submissionEmbed.add_field(
                            name=label,
                            value=answer if answer.strip() else "N/A",
                            inline=False)

        if guild is None:
            if member.avatar:
                submissionEmbed.set_footer(text=f"{member.name} | {member.id}", icon_url=member.avatar.url)
            else:
                submissionEmbed.set_footer(text=f"{member.name} | {member.id}")
        else:
            if guild.icon:
                submissionEmbed.set_footer(text=guild.name, icon_url=guild.icon.url)
            else:
                submissionEmbed.set_footer(text=guild.name)
            
        return submissionEmbed


    async def send_ticket_embeds(self, guild, channel, dm_channel, thread, user, values, title):
        print("user id is", user.id)
        member = await self.bot.cache.get_guild_member(guild, user.id)

        if member is None:
            logger.error("Failed to find member object for user: ", user.id)
            return
           
        print("got the member", member)
        await self.bot.cache.store_guild_member(guild.id, member)
         
        roles = member.roles
        default = guild.default_role

        priority_values = ["No data","No data"]
        game_type = SERVER_TO_GAME.get(guild.id, None)

        result = None
        if game_type is not None:
            result = await get_priority(game_type, guild.id, user.id)

        if result is not None:
            priority_values = result


        ticketEmbed = discord.Embed(title=f"New \"{title}\" Ticket",
                                    description="To reply, send a message in this channel prefixed with `+`. "
                                    "Any other messages will send as a comment (not visible to the ticket opener). "
                                    "To use commands, type `/` and select from the displayed list.\n\n`/close "
                                    "[reason]` will close a ticket. `/inactive [reason] [hours]` will close a "
                                    "ticket after X hours of inactivity from the ticket opener.")
        ticketEmbed.timestamp = datetime.now(timezone.utc)
 
        ticketEmbed.add_field(name="Opener", value=f"<@{user.id}>\n{user.name}\n{user.id}", inline=True)
        ticketEmbed.add_field(
                        name="Roles",
                        value=(
                            "*None*"
                            if len(roles) <= 1  # Only @everyone
                            else (
                                (
                                    " ".join([f"<@&{role.id}>" for role in roles if role != default])
                                    if len(" ".join([f"<@&{role.id}>" for role in roles if role != default])) <= 1024
                                    else f"*{len([r for r in roles if r != default])} roles*"
                                )
                            )
                        ),
                        inline=True
                    )

        ticketEmbed.add_field(name=f"Account Age", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
        ticketEmbed.add_field(name="", value="", inline=False)
        ticketEmbed.add_field(name=f"Robux Spent", value=priority_values[0], inline=True)
        ticketEmbed.add_field(name=f"Hours Ingame", value=priority_values[1], inline=True)

        submissionEmbed = await self.create_submission_embed(None, member, values, title)
            
        await channel.send(embed=ticketEmbed)
        await channel.send(embed=submissionEmbed)

        await thread.send(embed=ticketEmbed)
        await thread.send(embed=submissionEmbed)


    async def priority(guild, openID):
        priority_values = [-1,-1]
        game_type = SERVER_TO_GAME.get(guild.id, None)
        print(game_type)

        if game_type is not None:
            priority_values = await get_priority(game_type, guild.id, openID)
            print(f"priority values: {priority_values}")

        if not priority_values:
            priority_values = [-1,-1]
            print("priority values set to default")

        print(f"ending priority values: {priority_values}")
