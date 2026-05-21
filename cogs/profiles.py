import discord
from discord import app_commands
from discord.app_commands import Range
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

    profile_group = app_commands.Group(name="profile", description="Manage profiles")

    @profile_group.command(
        name="list", description="List all available adjectives and nouns for profiles"
    )
    @app_commands.describe(type="Choose to list adjectives or nouns")
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Adjectives", value="Adjectives"),
            app_commands.Choice(name="Nouns", value="Nouns"),
        ]
    )
    @checks.is_user_app()
    @checks.is_guild_app()
    async def profile_list(self, interaction: discord.Interaction, type: str):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            pages = []

            if type == "Adjectives":
                adjs = await self.bot.data_manager.load_adjs_from_db()
                if not adjs:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ There are currently no adjectives in the database."
                        )
                    )
                else:
                    for i in range(0, len(adjs), 20):
                        chunk = adjs[i : i + 20]
                        ap_embed = Embeds.success(title=f"Anonymous Profile Adjectives")
                        ap_embed.set_author(
                            name=guild.name,
                            icon_url=guild.icon.url if guild.icon else None,
                        )

                        content = "\n".join(
                            [
                                f"{count + i + 1}) **{adj[1]}**"
                                for count, adj in enumerate(chunk)
                            ]
                        )
                        ap_embed.description = content
                        pages.append(ap_embed)

                    pages = add_footers(pages)
                    view = Paginator(pages)
                    view.message = await interaction.followup.send(
                        embed=pages[0], view=view
                    )

            elif type == "Nouns":
                nouns = await self.bot.data_manager.load_nouns_from_db(guild.id)
                if not nouns:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ There are currently no nouns for this server."
                        )
                    )
                else:
                    for i in range(0, len(nouns), 20):
                        chunk = nouns[i : i + 20]
                        ap_embed = Embeds.success(title=f"Anonymous Profile Nouns")
                        ap_embed.set_author(
                            name=guild.name,
                            icon_url=guild.icon.url if guild.icon else None,
                        )

                        content = "\n".join(
                            [
                                f"{count + i + 1}) **{noun[1]}**"
                                for count, noun in enumerate(chunk)
                            ]
                        )
                        ap_embed.description = content
                        pages.append(ap_embed)

                    pages = add_footers(pages)
                    view = Paginator(pages)
                    view.message = await interaction.followup.send(
                        embed=pages[0], view=view
                    )

        except Exception as e:
            logger.exception(f"/profile list sent an error: {e}")
            raise BotError(
                "An error occurred while fetching profiles. Please try again later."
            )

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
            await interaction.response.defer(ephemeral=True)
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
                    adjective, noun, url = (ap["adj"], ap["noun"], ap["url"])

                    if adjective == "None":
                        adjective = ""
                    embed = Embeds.success(description=f"### {adjective} {noun}")
                    if url is not None:
                        embed.set_thumbnail(url=url)
                        embed.description += f"\n[Image Link]({url})"
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
                            adjective, noun, url, mod_id = (
                                entry[0],
                                entry[1],
                                entry[2],
                                entry[3],
                            )

                            if adjective == "None":
                                adjective = ""
                            ap_embed.add_field(
                                name=f"{adjective} {noun}\n",
                                value=f"**Moderator:** <@{mod_id}>\n"
                                f"**Image:** {'[Link](' + url + ')' if url else 'None'}",
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
                    )
                )
            else:
                adjective = ap["adj"]
                noun = ap["noun"]
                url = ap["url"]

                if adjective == "None":
                    adjective = ""
                profileEmbed = discord.Embed(
                    description=f"### {adjective} {noun}",
                    color=discord.Color.green(),
                )
                if url is not None:
                    profileEmbed.set_thumbnail(url=url)
                    profileEmbed.description += f"\n[Image Link]({url})"
                await interaction.followup.send(embed=profileEmbed)
        except Exception as e:
            logger.exception(f"/profile random sent an error: {e}")

    @profile_group.command(name="add", description="Add a new adjective or noun")
    @app_commands.describe(
        adjective="Adjective for any profile",
        noun="Noun for any profile",
        image_url="Optional image URL for the noun",
    )
    @checks.is_admin_app()
    @checks.is_guild_app()
    async def profile_add(
        self,
        interaction: discord.Interaction,
        adjective: Range[str, 1, 32] = None,
        noun: Range[str, 1, 32] = None,
        image_url: str = None,
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            guild_id = interaction.guild.id

            if image_url and (noun is None):
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ You cannot add an image URL without specifying a noun."
                    )
                )
                return

            if image_url and not is_valid_image_url(image_url):
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ The image URL is not valid. Please provide a direct link to an image (starting with https:// and ending in .jpg, .png, etc.)."
                    )
                )
                return

            embed = Embeds.success()
            output = "✅ Anonymous profiles updated:\n"

            if adjective:
                if not bool(re.fullmatch(r"[A-Za-z0-9 ]+", adjective.casefold())):
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ Adjectives must be alphanumeric only."
                        )
                    )
                    return
                await self.bot.data_manager.add_adj_to_db(adjective)
                output += f"- Adjective **{adjective}** added\n"

            if noun:
                if not bool(re.fullmatch(r"[A-Za-z0-9 ]+", noun.casefold())):
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ Nouns must be alphanumeric only."
                        )
                    )
                    return
                await self.bot.data_manager.add_noun_to_db(guild_id, noun, image_url)
                output += f"- Noun **{noun}** added\n"

            if image_url:
                output += f"- Image URL for noun **{noun}** set to {image_url}\n"
                embed.set_thumbnail(url=image_url)

            embed.description = output
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"/profile add sent an error: {e}")

    @profile_group.command(name="remove", description="Remove an adjective or noun")
    @app_commands.describe(
        adjective="Adjective to remove",
        noun="Noun to remove",
    )
    @checks.is_admin_app()
    @checks.is_guild_app()
    async def profile_remove(
        self,
        interaction: discord.Interaction,
        adjective: str = None,
        noun: str = None,
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            guild_id = interaction.guild.id
            adjective_id, adjective_text = (
                adjective.split(",") if adjective else (None, None)
            )
            noun_id, noun_text = noun.split(",") if noun else (None, None)

            output = "✅ Anonymous profiles updated:\n"

            if adjective_id:
                await self.bot.data_manager.delete_adj_from_db(adjective_id)
                output += f"- Adjective **{adjective_text}** removed\n"

            if noun_id:
                await self.bot.data_manager.delete_noun_from_db(guild_id, noun_id)
                output += f"- Noun **{noun_text}** removed\n"

            await interaction.followup.send(embed=Embeds.success(description=output))
        except Exception as e:
            logger.exception(f"/profile remove sent an error: {e}")

    @profile_remove.autocomplete("adjective")
    async def profile_set_adjective_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        adjectives = await self.bot.data_manager.load_adjs_from_db()
        return [
            app_commands.Choice(name=adj, value=f"{id},{adj}")
            for id, adj in adjectives
            if current.lower() in adj.lower()
        ][:25]

    @profile_remove.autocomplete("noun")
    async def profile_set_noun_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        guild_id = interaction.guild.id
        nouns = await self.bot.data_manager.load_nouns_from_db(guild_id)
        return [
            app_commands.Choice(name=noun, value=f"{id},{noun}")
            for id, noun in nouns
            if current.lower() in noun.lower()
        ][:25]

    @profile_group.command(
        name="assign", description="Assign a user an anonymous profile"
    )
    @app_commands.describe(
        user="User to set the profile for",
        adjective="Adjective for the profile",
        noun="Noun for the profile",
    )
    @checks.is_admin_app()
    @checks.is_guild_app()
    async def profile_assign(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        adjective: str,
        noun: str,
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            adjective_id, adjective_text = adjective.split(",")
            noun_id, noun_text = noun.split(",")

            link = await self.bot.data_manager.find_link(
                guild.id, adjective_id, noun_id
            )
            if link:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description=f"❌ This anonymous profile is already in use "
                        "in this server. Please choose a different adjective and "
                        "noun combination."
                    )
                )
                return

            await self.bot.data_manager.add_link_to_db(
                guild.id, user.id, adjective_id, noun_id
            )

            await interaction.followup.send(
                embed=Embeds.success(
                    description=f"✅ Set anonymous profile for {user.mention} "
                    f"to **{adjective_text if adjective_text != 'None' else ''} {noun_text}**."
                )
            )

        except Exception as e:
            logger.exception(f"/profile set sent an error: {e}")

    @profile_assign.autocomplete("adjective")
    async def profile_set_adjective_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        guild = interaction.guild
        adjectives = await self.bot.data_manager.load_adjs_from_db()
        return [
            app_commands.Choice(name=adj, value=f"{id},{adj}")
            for id, adj in adjectives
            if current.lower() in adj.lower()
        ][:25]

    @profile_assign.autocomplete("noun")
    async def profile_set_noun_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        guild = interaction.guild
        nouns = await self.bot.data_manager.load_nouns_from_db(guild.id)
        return [
            app_commands.Choice(name=noun, value=f"{id},{noun}")
            for id, noun in nouns
            if current.lower() in noun.lower()
        ][:25]

    @profile_group.command(name="clear", description="Clear a user's anonymous profile")
    @app_commands.describe(user="User to clear the profile for")
    @checks.is_admin_app()
    @checks.is_guild_app()
    async def profile_clear(
        self, interaction: discord.Interaction, user: discord.Member
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild

            ap = await self.bot.data_manager.get_or_load_ap(guild.id, user.id)
            if ap is not None:
                await self.bot.data_manager.delete_link_from_db(guild.id, user.id)
                await interaction.followup.send(
                    embed=Embeds.success(
                        description=f"✅ Anonymous profile for {user.mention} has been cleared."
                    )
                )
            else:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description=f"❌ {user.mention} does not currently have an anonymous profile to clear."
                    )
                )
        except Exception as e:
            logger.exception(f"/profile clear sent an error: {e}")

    @profile_group.command(
        name="test", description="Test if an image URL is valid for profiles"
    )
    @app_commands.describe(image_url="Image URL to test")
    @checks.is_user_app()
    @checks.is_guild_app()
    async def profile_test(self, interaction: discord.Interaction, image_url: str):
        try:
            await interaction.response.defer(ephemeral=True)

            if is_valid_image_url(image_url):
                embed = Embeds.success(description="✅ The image URL is valid.")
                embed.set_thumbnail(url=image_url)
                await interaction.followup.send(embed=embed)

            else:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ The image URL is not valid. Please provide a direct link to an image (starting with https:// and ending in .jpg, .png, etc.)."
                    )
                )
        except Exception as e:
            logger.exception(f"/profile test sent an error: {e}")


async def setup(bot):
    await bot.add_cog(Profiles(bot))
