import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import MailBee
from utils import checks, emojis
from utils.logger import *
from classes.error_handler import AccessError, AppAccessError, BotError

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

bot_token = os.getenv("BOT_TOKEN")
owners = list(map(int, os.getenv("OWNERS").split(",")))

bot = MailBee()
bot._patch_api_routes(bot.queue)


@bot.command(name="shutdown", aliases=["sh"])
@checks.is_owner()
async def shutdown(ctx):
    """
    Shuts down the bot safely, closing database connections and saving necessary data.
    """
    await ctx.send("Shutting down...")
    await bot.close()


@bot.command(name="reload", aliases=["rel"])
@checks.is_owner()
async def reload(ctx, cog: str):
    """
    Reloads a specified cog.
    """
    try:
        await bot.unload_extension(f"cogs.{cog}")
        await bot.load_extension(f"cogs.{cog}")

        await ctx.send(f"{emojis.mantis} Cog **{cog}** has been reloaded")
        logger.success(f"Reloaded cog: {cog}.py")

    except Exception as e:
        await ctx.send(f"❌ Error reloading cog **{cog}**: {e}")
        logger.error(f"Failed to reload {cog}.py: {e}")


@bot.command(name="sync")
@checks.is_owner()
async def sync_commands(ctx):
    """
    Syncs the bot's command tree globally.
    """
    message = await ctx.send(f"{emojis.mantis} Syncing global tree...")
    try:
        await bot.wait_until_ready()
        synced = await bot.tree.sync()
        logger.success(
            f"{bot.user.name} has been synced globally, "
            "please wait for Discord's API to update"
        )
    except Exception as e:
        await message.edit(content=f"❌ An error has occurred: {e}")
    else:
        await message.edit(
            content=f"{emojis.mantis} Main tree globally synced {len(synced)} commands."
        )


@bot.event
async def on_command_error(ctx, error: commands.CommandError):
    """
    Centralized command error handling event.
    """
    try:
        errorMsg = "❌ An error occurred."

        if ctx.author.id in owners:
            errorMsg = f"❌ An unexpected error occurred: {error}"

        if isinstance(error, commands.NotOwner):
            errorMsg = (
                "❌ Ownership error: You need ownership of MailBee to use this command"
            )

        elif isinstance(error, commands.MissingRequiredArgument):
            errorMsg = "❌ Command error: You are missing arguments"

        elif isinstance(error, commands.UserNotFound):
            errorMsg = "❌ Command error: Unable to find user"

        elif isinstance(error, commands.CommandNotFound):
            return

        elif isinstance(error, AccessError):
            errorMsg = f"❌ Access error: {error}"

        elif isinstance(error, commands.CheckFailure):
            errorMsg = str(error)

        elif isinstance(error, BotError):
            if ctx.author.id in owners:
                errorMsg = f"❌ An error occurred: {error}"
            logger.exception(f"❌ General command error: {error}")

        else:
            logger.error(f"❌ Command error: {error}")

        errorEmbed = discord.Embed(
            title="", description=f"{errorMsg}", color=discord.Color.red()
        )
        await ctx.send(embed=errorEmbed)

    except discord.errors.NotFound:
        logger.warning("Failed to send error message: Message context no longer exists")


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    """
    Centralized application command error handling event.
    """
    try:
        errorMsg = "❌ An error occurred."

        if interaction.user.id in owners:
            errorMsg = f"❌ An error occurred: {error}"

        if isinstance(error, app_commands.errors.MissingPermissions):
            errorMsg = "❌ You do not have the required permissions to use this command"

        elif isinstance(error, app_commands.errors.CommandNotFound):
            return

        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            errorMsg = (
                f"❌ This command is on cooldown. "
                f"Try again in {error.retry_after:.2f} seconds"
            )

        elif isinstance(error, commands.NotOwner):
            errorMsg = (
                "❌ Ownership error: You need ownership of MailBee to use this command"
            )

        elif isinstance(error, AppAccessError):
            errorMsg = f"❌ Access error: {error}"

        elif isinstance(error, app_commands.CheckFailure):
            errorMsg = str(error)

        elif isinstance(error, BotError):
            if interaction.user.id in owners:
                errorMsg = f"❌ An error occurred: {error}"
            logger.exception(f"❌ General command error: {error}")

        else:
            logger.error(f"❌ Unexpected command error: {error}")

        errorEmbed = discord.Embed(
            title="", description=errorMsg, color=discord.Color.red()
        )

        # Ensure the interaction is still valid before responding
        if interaction.response.is_done():
            await interaction.followup.send(embed=errorEmbed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=errorEmbed, ephemeral=True)

    except discord.errors.NotFound:
        logger.warning("Failed to send error message: Interaction no longer exists.")

    except Exception as e:
        logger.error(f"Unexpected error in on_app_command_error: {e}")


bot.run(bot_token)
