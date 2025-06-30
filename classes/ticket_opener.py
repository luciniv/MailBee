import discord
import asyncio
import re
import os
from copy import deepcopy
from discord import Embed
from discord.permissions import PermissionOverwrite
from datetime import datetime, timezone
from typing import Dict, List
from utils.logger import *
from roblox_data.helpers import *


SERVER_TO_GAME = {
    714722808009064492: ("Creatures of Sonaria", 1831550657, os.getenv("COS_KEY")),
    346515443869286410: ("Dragon Adventures", 1235188606, os.getenv("DA_KEY")),
    1196293227976863806: ("Horse Life", 5422546686, os.getenv("HL_KEY")),
    549701425958223895: ("World // Zero", 0, os.getenv("WZ_KEY")),
    1007432760027250740: ("Drive World", 0, os.getenv("DW_KEY")),
    1301233303734718474: ("Dungeon Heroes", 0, os.getenv("DH_KEY"))}


async def get_overwrites(guild, roles) -> Dict:
    overwrites = {
        guild.default_role: PermissionOverwrite(read_messages=False)}

    for role in roles:
        if role is not None:
            overwrites[role] = PermissionOverwrite(
                read_messages=True,
                read_message_history=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True)
    return dict(overwrites)


class TicketOpener:
    def __init__(self, bot):
        self.bot = bot


    async def open_ticket(self, user, guild, category, typeID, values, title, time_taken, NSFW):
        try:
            NSFW_flag = "🔞"
            if not NSFW:
                NSFW_flag = ""

            errorEmbed = discord.Embed(description="", color=discord.Color.red())

            # Generate ticket ID
            ticketID = await self.bot.data_manager.get_next_ticket_id(guild.id)
            dm_channel = user.dm_channel or await user.create_dm()

            # Send log embed
            log_message = await self.send_log(guild, user, title, NSFW_flag)

            # Create logging thread
            if log_message is not None:
                try:
                    thread = await log_message.create_thread(name=f"Ticket Log {user.name} - {ticketID}", auto_archive_duration=1440)
                except discord.HTTPException as e:
                    if "Contains words not allowed" in e.text:
                        thread = await log_message.create_thread(name=f"Ticket Log {user.id} - {ticketID}", auto_archive_duration=1440)
                except Exception:
                    pass

                if thread is not None:
                    await self.bot.cache.store_channel(thread)
                else:
                    errorEmbed.description="❌ Unable to create logging thread. Contact a server admin with this error."
                    await dm_channel.send(embed=errorEmbed)
                    return
            else:
                errorEmbed.description="❌ Unable to send opening log. Contact a server admin with this error."
                await dm_channel.send(embed=errorEmbed)
                return

            # Create ticket channel
            channel = await self.create_ticket_channel(guild, category, user, thread.id, NSFW_flag)
            if channel is None:
                errorEmbed.description="❌ Unable to create ticket channel. Contact a server admin with this error."
                await dm_channel.send(embed=errorEmbed)
                return

            await self.bot.cache.store_channel(channel)

            logEmbed = deepcopy(log_message.embeds[0])
            logEmbed.add_field(name="Ticket Channel", value=f"<#{channel.id}>", inline=True)
            logEmbed.add_field(name="Ticket ID", value=ticketID, inline=True)

            await log_message.edit(embed=logEmbed)

            if channel:
                # Send opening embed, and greeting if it exists
                await self.send_opener(guild, dm_channel, user, values, title)

                roblox_data = []
                priority_values = [-1,-1]
                robloxID = None
                robloxUsername = None
                game_type = SERVER_TO_GAME.get(guild.id, None)
                if game_type is not None:
                    robloxID, robloxUsername = await get_roblox_info(game_type, guild.id, user.id)

                if robloxID is None:
                    roblox_data.append("ID not found")
                else:
                    roblox_data.append(robloxID)
                if robloxUsername is None:
                    roblox_data.append("Username not found")
                else:
                    roblox_data.append(robloxUsername)

                if game_type is not None and robloxUsername is not None:
                    result = await get_priority(game_type, guild.id, user.id, robloxUsername)
                    if result is None:
                        roblox_data.append("Error fetching data")
                        roblox_data.append("Error fetching data")
                    else:
                        priority_values = result
                        roblox_data.append(result[0])
                        roblox_data.append(result[1])
                else:
                    roblox_data.append("No data")
                    roblox_data.append("No data")

                # Send in-channel embeds
                await self.send_ticket_embeds(guild, channel, thread, user, values, title, time_taken, roblox_data, ticketID)

                # Add new ticket to database
                await self.bot.data_manager.create_ticket(guild.id, ticketID, channel.id, user.id, thread.id, typeID, 
                                                        time_taken, priority_values[0], priority_values[1])
                await self.bot.data_manager.get_or_load_user_tickets(user.id, False)
                return True

            else:
                print("failed to create ticket channel")
                return False
        except Exception as e:
            print("ticket_opener sent an exception:", e)
        

    async def send_log(self, guild, user, title, NSFW_flag):
        config = await self.bot.data_manager.get_or_load_config(guild.id)

        if config is None:
            return
        
        logID = config["logID"] 
        log_channel = await self.bot.cache.get_channel(logID)

        openLogEmbed = discord.Embed(title=f"{NSFW_flag} New \"{title}\" Ticket", description="", 
                                    color=discord.Color.green())
        openLogEmbed.timestamp = datetime.now(timezone.utc)

        openLogEmbed.set_footer(text=f"{user.name} | {user.id}", icon_url=user.display_avatar.url)

        try:
            message = await log_channel.send(embed=openLogEmbed)
            return message
        except Exception:
            return None


    async def create_ticket_channel(self, guild, category, user, threadID, NSFW_flag):
        try:
            # Check for any permitted roles (user or admin)
            # roles = []
            # permissions = await self.bot.data_manager.get_or_load_permissions(guild.id)
            # print("permissions is", permissions)
            # print("keys are", permissions.keys())
            # for roleID in permissions.keys():
            #     print("roleID is", roleID)
            #     role = guild.get_role(roleID)
            #     roles.append(role)
            
            # overwrites = await get_overwrites(guild, roles)
            # print(overwrites)
            # FIXME re-use this overwrites code to apply on category creation

            channel_name = re.sub(r"[./]", "", user.name.lower())
            if NSFW_flag == "":
                try:
                    ticket_channel = await guild.create_text_channel(
                        name=channel_name,
                        category=category,
                        overwrites=category.overwrites,
                        topic=f"Ticket channel {user.id} {threadID}")
                    
                except discord.HTTPException as e:
                    if "Contains words not allowed" in e.text:
                        ticket_channel = await guild.create_text_channel(
                            name=str(user.id),
                            category=category,
                            overwrites=category.overwrites,
                            topic=f"Ticket channel {user.id} {threadID}")
                except Exception:
                    return None
            else:
                try:
                    ticket_channel = await guild.create_text_channel(
                        name=f"{NSFW_flag}{channel_name}",
                        nsfw=True,
                        category=category,
                        overwrites=category.overwrites,
                        topic=f"Ticket channel {user.id} {threadID}")
                
                except discord.HTTPException as e:
                    if "Contains words not allowed" in e.text:
                        ticket_channel = await guild.create_text_channel(
                            name=f"{NSFW_flag}{str(user.id)}",
                            nsfw=True,
                            category=category,
                            overwrites=category.overwrites,
                            topic=f"Ticket channel {user.id} {threadID}")
                except Exception:
                    return None

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
            submissionEmbed.set_footer(text=f"{member.name} | {member.id}", icon_url=member.display_avatar.url)
        else:
            if guild.icon:
                submissionEmbed.set_footer(text=guild.name, icon_url=guild.icon.url)
            else:
                submissionEmbed.set_footer(text=guild.name)
            
        return submissionEmbed


    async def send_ticket_embeds(self, guild, channel, thread, user, values, title, time_taken, roblox_data, ticketID):
        member = await self.bot.cache.get_guild_member(guild, user.id)

        if member is None:
            logger.error("Failed to find member object for user: ", user.id)
            return
        
        count = await self.bot.data_manager.get_ticket_count(guild.id, user.id)
        print(count)
        if count is not None:
            count = int(count[0][0])
            if count != 0:
                count -= 1
        else:
            count = 0
         
        roles = member.roles
        default = guild.default_role

        ticketEmbed = discord.Embed(title=f"New \"{title}\" Ticket [ID {ticketID}]",
                                    description="To reply, send a message in this channel prefixed with `+`. "
                                    "Any other messages will send as a comment (not visible to the ticket opener). "
                                    "To use commands, prefix with `+` or type `/` and select from the displayed "
                                    "list.\n\n`+close [reason]` will close a ticket. `+inactive [hours] [reason]` "
                                    "will close a ticket after X hours of inactivity from the ticket opener.")
        ticketEmbed.timestamp = datetime.now(timezone.utc)
        ticketEmbed.set_footer(text=f"{member.name} | {member.id}", icon_url=member.display_avatar.url)
 
        ticketEmbed.add_field(name="Opener", value=f"<@{user.id}> {user.name}\n({user.id})", inline=True)
        ticketEmbed.add_field(
                        name="Roles",
                        value=(
                            "*None*"
                            if len(roles) <= 1  # Only @everyone
                            else ((
                                " ".join([f"<@&{role.id}>" for role in roles if role != default])
                                if len(" ".join([f"<@&{role.id}>" for role in roles if role != default])) <= 1024
                                else f"*{len([r for r in roles if r != default])} roles*"
                                ))),
                        inline=True)
        ticketEmbed.add_field(name="", value="", inline=False)
        ticketEmbed.add_field(name="Join Date", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
        ticketEmbed.add_field(name="Account Age", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
        ticketEmbed.add_field(name="", value="", inline=False)
        ticketEmbed.add_field(name="Roblox Username", value=roblox_data[1], inline=True)
        ticketEmbed.add_field(name="Roblox ID", value=roblox_data[0], inline=True)
        ticketEmbed.add_field(name="", value="", inline=False)
        ticketEmbed.add_field(name="Robux Spent", value=roblox_data[2], inline=True)
        ticketEmbed.add_field(name="Hours Ingame", value=roblox_data[3], inline=True)
        ticketEmbed.add_field(name="", value="", inline=False)
        ticketEmbed.add_field(name="Time Taken on Form", value=f"`{time_taken}` seconds", inline=True)
        ticketEmbed.add_field(name="Prior Tickets", value=count, inline=True)

        submissionEmbed = await self.create_submission_embed(None, member, values, title)
            
        await channel.send(embed=ticketEmbed)
        await channel.send(embed=submissionEmbed)

        await thread.send(embed=ticketEmbed)
        await thread.send(embed=submissionEmbed)


    async def priority(guild, openID):
        priority_values = [-1,-1]
        game_type = SERVER_TO_GAME.get(guild.id, None)

        if game_type is not None:
            priority_values = await get_priority(game_type, guild.id, openID)

        if not priority_values:
            priority_values = [-1,-1]
