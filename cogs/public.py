import discord
import os
from discord.ext import commands
from discord import app_commands
from typing import List
from classes.error_handler import *
from classes.embeds import *
from classes.ticket_creator import ServerSelectView
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
    @commands.hybrid_command(name="create_ticket", description="Open a support ticket with a server")
    async def create_ticket(self, ctx):
        try:
            channel = ctx.channel
            channelID = channel.id
            user = ctx.author
            errorEmbed = discord.Embed(title="", description="", color=discord.Color.red())

            await self.bot.cache.store_user(user)
            
            # Ensure command is DM only
            if (isinstance(channel, discord.DMChannel) or not ctx.guild):

                # Check if verified, skip for now
                if (True):
                    shared_guilds = []
                    for guild in self.bot.guilds:
                        shared_guilds.append(guild)
    
                    if not shared_guilds:
                        errorEmbed.description = "❌ You do not share any servers with the bot"
                        await ctx.send(embed=errorEmbed)
                        return

                    # Send server selection embed
                    serverEmbed = discord.Embed(title="Choose A Server",
                                                description="Please select a server for your ticket. Use "
                                                "the provided drop-down menu by clicking **\"Choose a server...\"**\n\n"
                                                "If you don't see your server, use `/verify` to re-verify your server "
                                                "list with the bot, then run `/create_ticket` again.",
                                                color=discord.Color.blue())
                    
                    view = ServerSelectView(self.bot, shared_guilds, channelID)
                    message = await ctx.send(embed=serverEmbed, view=view)
                    view.message = message

                # Not verified
                else:
                    verifyEmbed = discord.Embed(title="Verify Your Servers", 
                                                description="Click the button below to verify your servers. The bot must "
                                                "know which servers you are in before you can open a ticket.",
                                                color=discord.Color.blue())
                    
                    
                    pass
            else:
                errorEmbed.description="❌ Cannot open ticket outside of bot DMs"
                await ctx.send(embed=errorEmbed, ephemeral=True)
                return
            
        except discord.Forbidden:
            print("dm failed, user has dms off")
            return

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/create_ticket sent an error: {e}")
    

async def setup(bot):
    await bot.add_cog(Public(bot))
