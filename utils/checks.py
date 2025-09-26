import discord
from discord import Interaction, app_commands
from discord.ext import commands

from classes.error_handler import *


# Checks if user is the owner of Mantid
def is_owner():
    def predicate(ctx):
        if ctx.author.id != 429711831695753237:
            raise commands.NotOwner()

        return True

    return commands.check(predicate)


# Is admin command for weighted permissions
# Checks if user has Admin permissions for that channel or their ID is set as bot admin in Mantid's permissions cache
def is_admin():
    async def predicate(ctx):
        result = await _check_admin_logic(
            guild_id=ctx.guild.id,
            user=ctx.author,
            channel=ctx.channel,
            command_name=ctx.command.name,
            data_manager=ctx.bot.data_manager,
        )
        if not result:
            raise AccessError(
                f"You do not have access to use the **{ctx.command.name}** command.",
                required_permission="Administrator or Bot Admin",
            )
        return result

    return commands.check(predicate)


def is_admin_app():
    async def predicate(interaction: Interaction):
        result = await _check_admin_logic(
            guild_id=interaction.guild.id,
            user=interaction.user,
            channel=interaction.channel,
            command_name=interaction.command.name,
            data_manager=interaction.client.data_manager,
        )
        if not result:
            raise AppAccessError(
                f"You do not have access to use the **{interaction.command.name}** command.",
                required_permission="Administrator or Bot Admin",
            )
        return result

    return app_commands.check(predicate)


async def _check_admin_logic(guild_id, user, channel, command_name, data_manager):
    usrRoles = getattr(user, "roles", [])

    search_access = [
        (role_id, permLevel)
        for guild_id, role_id, permLevel in data_manager.access_roles
        if guild_id == guild_id
    ]

    if channel.permissions_for(user).administrator:
        return True

    for role in usrRoles:
        if (role.id, "Bot Admin") in search_access:
            return True
    return False


# Is user command for weighted permissions
def is_user():
    async def predicate(ctx):
        bot = ctx.bot
        guild_id = ctx.guild.id
        user = ctx.author
        channel = ctx.channel
        command_name = ctx.command.name

        result = await _check_access(bot, guild_id, user, channel)
        if not result:
            raise AccessError(
                f"You do not have access to use the **{command_name}** command.",
                required_permission="Bot User",
            )
        return result

    return commands.check(predicate)


def is_user_app():
    async def predicate(interaction: Interaction):
        bot = interaction.client
        guild_id = interaction.guild.id
        user = interaction.user
        channel = interaction.channel
        command_name = interaction.command.name

        result = await _check_access(bot, guild_id, user, channel)
        if not result:
            raise AppAccessError(
                f"You do not have access to use the **{command_name}** command.",
                required_permission="Bot User",
            )
        return result

    return app_commands.check(predicate)


async def _check_access(bot, guild_id, user, channel):
    data_manager = bot.data_manager
    user_roles = user.roles

    search_access = [tup[1] for tup in data_manager.access_roles if tup[0] == guild_id]

    if channel.permissions_for(user).administrator:
        return True

    for role in user_roles:
        if role.id in search_access:
            return True

    return False


def is_guild():
    async def predicate(ctx):
        if ctx.guild is not None:
            return True
        raise commands.CheckFailure(
            "To reply to a ticket, type a message in DMs here. "
            "Any messages sent will be forwarded to server staff. If you want to open "
            "a new ticket, use `/create_ticket`.\n\n**Note:** If you can't reply and are "
            'stuck seeing the "Commands" button on mobile, tap the chat icon to open the '
            "message box."
        )

    return commands.check(predicate)


def is_guild_app():
    async def predicate(interaction: Interaction):
        if interaction.guild is not None:
            return True
        raise app_commands.CheckFailure(
            "To reply to a ticket, type a message in DMs here. "
            "Any messages sent will be forwarded to server staff. If you want to open "
            "a new ticket, use `/create_ticket`.\n\n**Note:** If you can't reply and are "
            'stuck seeing the "Commands" button on mobile, tap the chat icon to open the '
            "message box."
        )

    return app_commands.check(predicate)


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
