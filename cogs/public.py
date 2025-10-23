import os
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from classes.embeds import Embeds
from classes.error_handler import *
from classes.ticket_submitter import ServerSelectView
from utils import checks
from utils.logger import *

# CLIENT_ID = os.getenv("CLIENT_ID")
# REDIRECT_URI = "http://localhost:5000/callback"
# SCOPES = "identify guilds"

# async def verify():
#     user = ctx.author
#     oauth_url = (
#         f"https://discord.com/api/oauth2/authorize"
#         f"?client_id={CLIENT_ID}"
#         f"&redirect_uri={REDIRECT_URI}"
#         f"&response_type=code"
#         f"&scope={SCOPES.replace(' ', '%20')}"
#     )

#     embed = discord.Embed(
#         title="Verification Required",
#         description="Click the button below to verify and share your servers with the bot.",
#         color=discord.Color.blue()
#     )

#     try:
#         await user.send(embed=embed, view=OAuthView(oauth_url))
#         await ctx.send("I've sent you a DM with the verification link.")
#     except discord.Forbidden:
#         await ctx.send("I couldn't send you a DM. Please enable DMs from server members.")


class Public(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Create ticket command
    @app_commands.command(
        name="create_ticket", description="Open a support ticket with a server"
    )
    async def create_ticket(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=False)
            guild = interaction.guild
            channel = interaction.channel
            channel_id = channel.id
            user = interaction.user

            await self.bot.cache.store_user(user)

            # Ensure command is DM only
            if isinstance(channel, discord.DMChannel) or not guild:

                shared_guilds = []
                for guild in self.bot.guilds:
                    shared_guilds.append(guild)

                if not shared_guilds:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ You do not share any servers with the bot"
                        ),
                        ephemeral=True,
                    )
                    return

                # Send server selection embed
                serverEmbed = Embeds.info(
                    title="Choose A Server",
                    description="Please select a server for your ticket. Use "
                    'the provided drop-down menu by clicking **"Choose a server..."**\n\n'
                    "If you don't see your server, wait a moment and run `/create_ticket` again.",
                )

                view = ServerSelectView(self.bot, shared_guilds, channel_id)
                message = await interaction.followup.send(embed=serverEmbed, view=view)
                view.message = message
                pass

            else:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Cannot open ticket outside of bot DMs"
                    ),
                    ephemeral=True,
                )
                return

        except discord.Forbidden:
            print("dm failed, user has dms off")
            return

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/create_ticket sent an error: {e}")


async def setup(bot):
    await bot.add_cog(Public(bot))
