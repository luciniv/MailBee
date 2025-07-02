import discord
from discord.ext import commands
from discord import app_commands
from classes.error_handler import *


# Checks if user is the owner of Mantid
def is_owner():
    def predicate(ctx):
        if (ctx.author.id != 429711831695753237):
            raise commands.NotOwner()
        
        return True
    return commands.check(predicate)


# Is admin command for weighted permissions
# Checks if user has Admin permissions for that channel or their ID is set as bot admin in Mantid's permissions cache
def is_admin():
    def predicate(ctx):
        try:
            data_manager = ctx.bot.data_manager
            guild = ctx.guild
            usrRoles = ctx.author.roles

            search_access = [
                (roleID, permLevel) for guildID, roleID, permLevel 
                in data_manager.access_roles if (guildID == guild.id)]

            if (ctx.channel.permissions_for(ctx.author).administrator):
                return True
            
            for role in usrRoles:
                if ((role.id, "Bot Admin") in search_access):
                    return True
            raise AccessError(f"You do not have access to use the **{ctx.command.name}** command.", 
                            required_permission="Administrator or Bot Admin")
        except Exception:
            return False
    return commands.check(predicate)


# Is user command for weighted permissions
# Checks if user has Admin permissions for that channel or their ID is in Mantid's permissions cache at all
def is_user():
    async def predicate(ctx_or_interaction):
        try:
            if isinstance(ctx_or_interaction, commands.Context):
                # Prefix or hybrid command
                bot = ctx_or_interaction.bot
                guild_id = ctx_or_interaction.guild.id
                user = ctx_or_interaction.author
                channel = ctx_or_interaction.channel
                command_name = ctx_or_interaction.command.name

            else:
                # App command (Interaction)
                bot = ctx_or_interaction.client
                guild_id = ctx_or_interaction.guild.id
                user = ctx_or_interaction.user
                channel = ctx_or_interaction.channel
                command_name = ctx_or_interaction.command.name

            data_manager = bot.data_manager
            user_roles = user.roles

            search_access = [
                tup[1] for tup 
                in data_manager.access_roles
                if tup[0] == guild_id]

            if channel.permissions_for(user).administrator:
                return True

            for role in user_roles:
                if role.id in search_access:
                    return True

            raise AccessError(f"You do not have access to use the **{command_name}** command.",
                            required_permission="Bot User or Bot Admin")
        except Exception:
            return False
    return commands.check(predicate)


def is_guild():
    async def predicate(ctx_or_interaction):
        if isinstance(ctx_or_interaction, commands.Context):
            # Prefix or hybrid command
            guild = ctx_or_interaction.guild
        else:
            # App command (Interaction)
            guild = ctx_or_interaction.guild

        if guild is not None:
            return True
        
        raise AccessError("This command can only be used in a server.")
    return commands.check(predicate)


def is_setup():
    async def predicate(ctx_or_interaction):
        try:
            if isinstance(ctx_or_interaction, commands.Context):
                # Prefix or hybrid command
                guild_id = ctx_or_interaction.guild.id
                bot = ctx_or_interaction.bot
            else:
                # App command (Interaction)
                guild_id = ctx_or_interaction.guild.id
                bot = ctx_or_interaction.client

            data_manager = bot.data_manager
            config = await data_manager.get_or_load_config(guild_id)
            if config is not None:
                return True

            raise AccessError("You must run `/setup` before using this command.")
        except Exception:
            return False

    return commands.check(predicate)


