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
        raise AccessError(f"You do not have access to use the **{ctx.command.name}** command", required_permission="Administrator or Bot Admin")
    return commands.check(predicate)


# Is user command for weighted permissions
# Checks if user has Admin permissions for that channel or their ID is in Mantid's permissions cache at all
def is_user():
    def predicate(ctx):
        data_manager = ctx.bot.data_manager
        guildID = ctx.guild.id
        usrRoles = ctx.author.roles
   
        search_access = [
            tup[1] for tup 
            in data_manager.access_roles
            if tup[0] == guildID]

        if (ctx.channel.permissions_for(ctx.author).administrator):
            return True
        
        for role in usrRoles:
            if role.id in search_access:
                return True
        raise AccessError(f"You do not have access to use the **{ctx.command.name}** command", required_permission="Bot User or Bot Admin")
    return commands.check(predicate)


# Is user command for weighted APPLICATION COMMAND permissions
# Checks if user has Admin permissions for that channel or their ID is in Mantid's permissions cache at all
def is_user_app():
    def predicate(interaction: discord.Interaction):
        data_manager = interaction.client.data_manager
        guildID = interaction.guild.id
        usrRoles = interaction.user.roles
   
        search_access = [
            tup[1] for tup 
            in data_manager.access_roles
            if tup[0] == guildID]

        if (interaction.channel.permissions_for(interaction.user).administrator):
            return True
        
        for role in usrRoles:
            if role.id in search_access:
                print("User was in search access")
                return True
        raise AccessError(f"You do not have access to use the **{interaction.command.name}** command", required_permission="Bot User or Bot Admin")
    return app_commands.check(predicate)
