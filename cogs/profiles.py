import discord
from discord import app_commands
from discord.ext import commands

from classes.error_handler import *
from utils import checks
from utils.logger import *


class Profiles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.adjs = {}
        self.nouns = {}
        self.links = {}

    @app_commands.command(
        name="profile", description="View a user's current anonymous profile"
    )
    @app_commands.describe(user="Leave this field empty to view your own profile")
    @checks.is_user_app()
    @checks.is_guild_app()
    async def profile(
        self, interaction: discord.Interaction, user: discord.Member = None
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild

            if user is None:
                user = interaction.user

            ap = await self.bot.data_manager.get_or_load_ap(guild.id, user.id)
            if ap is None:
                errorEmbed = discord.Embed(
                    description="❌ The user you selected does not currently have an anonymous profile.",
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=errorEmbed, ephemeral=True)
            else:
                adjective = ap["adj"]
                noun = ap["noun"]
                date = ap["date"]
                url = ap["url"]

                if adjective == "none":
                    adjective = ""
                profileEmbed = discord.Embed(
                    description=f"### {adjective} {noun}\n"
                    f"**Moderator:** <@{user.id}>\n"
                    f"**Acquired:** <t:{date}:D> (<t:{date}:R>)",
                    color=discord.Color.green(),
                )
                if url is not None:
                    profileEmbed.set_thumbnail(url=url)
                profileEmbed.set_author(
                    name=f"{user.name} | {user.id}",
                    icon_url=(user.avatar and user.avatar.url)
                    or user.display_avatar.url,
                )
                await interaction.followup.send(embed=profileEmbed, ephemeral=True)
        except Exception as e:
            logger.exception(f"/profile sent an error: {e}")

    # profile_group = app_commands.Group(name="profile", description="Manage profiles")

    # @profile_group.command(name="random", description="Generate a random, available profile to use")


async def setup(bot):
    await bot.add_cog(Profiles(bot))
