import discord
from discord import app_commands
from discord.ext import commands

from classes.embeds import Embeds
from classes.error_handler import *
from classes.paginator import Paginator
from utils import checks
from utils.helpers import *
from utils.logger import *


class Profiles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _read_ap_content(self, ap):
        return (ap["adj"], ap["noun"], ap["date"], ap["url"])

    def _read_db_ap_content(self, ap):
        return (ap[0], ap[1], ap[2], ap[3], ap[4])

    profile_group = app_commands.Group(name="profile", description="Manage profiles")

    @profile_group.command(
        name="view", description="View one or all anonymous profiles"
    )
    @app_commands.describe(
        user="User's profile to view, leave blank to view all profiles"
    )
    @checks.is_user_app()
    @checks.is_guild_app()
    async def profile_view(
        self, interaction: discord.Interaction, user: discord.Member = None
    ):
        try:
            await interaction.response.defer()
            guild = interaction.guild

            if user:
                ap = await self.bot.data_manager.get_or_load_ap(guild.id, user.id)
                if ap is None:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ The user you selected does not currently have an anonymous profile."
                        )
                    )
                else:
                    adjective, noun, date, url = self._read_ap_content(ap)

                    if adjective == "none":
                        adjective = ""
                    embed = Embeds.success(
                        description=f"### {adjective} {noun}\n"
                        f"**Acquired:** <t:{date}:D> (<t:{date}:R>)",
                    )
                    if url is not None:
                        embed.set_thumbnail(url=url)
                    embed.set_author(
                        name=f"{user.name} | {user.id}",
                        icon_url=(user.avatar and user.avatar.url)
                        or user.display_avatar.url,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                pages = []
                aps = await self.bot.data_manager.load_all_aps(guild.id)
                if not aps:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ There are currently no anonymous profiles in this server."
                        )
                    )
                else:
                    for i in range(0, len(aps), 5):
                        chunk = aps[i : i + 5]
                        ap_embed = Embeds.success(title=f"Anonymous Profiles")
                        ap_embed.set_author(
                            name=guild.name,
                            icon_url=guild.icon.url if guild.icon else None,
                        )

                        for index, entry in enumerate(chunk, start=i + 1):
                            adjective, noun, date, url, mod_id = (
                                self._read_db_ap_content(entry)
                            )

                            if adjective == "none":
                                adjective = ""
                            ap_embed.add_field(
                                name=f"{adjective} {noun}\n",
                                value=f"**Moderator:** <@{mod_id}>\n"
                                f"**Image:** {'[Link](' + url + ')' if url else 'None'}\n"
                                f"**Acquired:** <t:{date}:D> (<t:{date}:R>)",
                                inline=False,
                            )
                        pages.append(ap_embed)

                    pages = add_footers(pages)
                    view = Paginator(pages)
                    view.message = await interaction.followup.send(
                        embed=pages[0], view=view
                    )

        except Exception as e:
            logger.exception(f"/profile view sent an error: {e}")
            raise BotError(
                "An error occurred while fetching profiles. Please try again later."
            )

    @profile_group.command(
        name="random", description="Generate a random, available profile to use"
    )
    @checks.is_user_app()
    @checks.is_guild_app()
    async def profile_random(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild

            ap = await self.bot.data_manager.generate_random_ap(guild.id)
            if ap is None:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ There are no available anonymous profiles at this time. Please contact a moderator to create more profiles.",
                    ),
                    ephemeral=True,
                )
            else:
                adjective = ap["adj"]
                noun = ap["noun"]
                url = ap["url"]

                if adjective == "none":
                    adjective = ""
                profileEmbed = discord.Embed(
                    description=f"### {adjective} {noun}",
                    color=discord.Color.green(),
                )
                if url is not None:
                    profileEmbed.set_thumbnail(url=url)
                profileEmbed.set_author(
                    name=f"Random Anonymous Profile",
                    icon_url=guild.icon.url if guild.icon else None,
                )
                await interaction.followup.send(embed=profileEmbed, ephemeral=True)
        except Exception as e:
            logger.exception(f"/profile random sent an error: {e}")

    @profile_group.command(name="add", description="Add a new adjective or noun")
    @app_commands.describe(
        adjective="Adjective for the profile",
        noun="Noun for the profile",
        image_url="Optional image URL for the profile",
    )
    @checks.is_admin_app()
    @checks.is_guild_app()
    async def profile_add(
        self,
        interaction: discord.Interaction,
        adjective: str,
        noun: str,
        image_url: str = None,
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild

            success = await self.bot.data_manager.add_ap(
                guild.id, adjective, noun, image_url
            )
            if success:
                await interaction.followup.send(
                    embed=Embeds.success(
                        description="✅ Anonymous profile added successfully."
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ An anonymous profile with that adjective and noun already exists."
                    ),
                    ephemeral=True,
                )
        except Exception as e:
            logger.exception(f"/profile add sent an error: {e}")


async def setup(bot):
    await bot.add_cog(Profiles(bot))
