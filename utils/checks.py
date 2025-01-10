import discord
from discord.ext import commands
from classes.data_manager import DataManager
from classes.error_handler import *


# Checks if user is the owner of Mantid
def is_owner():
    def predicate(ctx):
        if (ctx.author.id != 429711831695753237):
            raise commands.NotOwner()
        
        return True
    return commands.check(predicate)


# Has access command for weighted permissions
# Checks if user has Admin permissions for that channel or their ID is in Mantid's permissions cache
def has_access():
    def predicate(ctx):
        data_manager = DataManager()
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
        raise AccessError(f"You do not have access to use the **{ctx.command.name}** command", required_permission="Administrator or Bot Admin")
    return commands.check(predicate)

