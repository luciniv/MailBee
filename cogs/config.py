import asyncio
import json
import re

import discord
from discord import app_commands
from discord.app_commands import Range
from discord.ext import commands

from ai_integration.prompt import build_server_context
from classes.embeds import Embeds
from classes.error_handler import *
from classes.helpers import *
from classes.paginator import *
from classes.ticket_opener import get_overwrites
from utils import checks, emojis
from utils.logger import *


class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setup")
    @checks.is_admin()
    @checks.is_guild()
    async def setup(self, ctx):
        try:
            guild = ctx.guild
            bot_member = ctx.guild.me
            inbox_category = None
            log_channel = None
            responses_channel = None
            feedback_thread = None
            reports_thread = None

            # Check for any permitted roles (user or admin)
            roles = []
            permissions = await self.bot.data_manager.get_or_load_permissions(guild.id)
            for role_id in permissions.keys():
                role = guild.get_role(role_id)
                roles.append(role)

            overwrites = await get_overwrites(guild, roles)

            setup_embed = Embeds.success(
                title="Bot Setup",
                description="Run this command to setup the bot. Setup includes creating "
                "the ticketing category, tickets log channel, and responses channel. If "
                "any of these categories or channels do not exist, the bot will create new "
                "ones. To re-create setup items, first delete the channel or category, then "
                "run this command.",
            )
            setup_embed.add_field(name="Setup Results", value="", inline=False)

            if not bot_member.guild_permissions.administrator:
                setup_embed.add_field(
                    name="",
                    value="❌ Could not run setup. I need the administrator permission to configure "
                    "myself properly.",
                    inline=False,
                )
                await ctx.send(embed=setup_embed)
                return

            config = await self.bot.data_manager.get_or_load_config(guild.id)
            if config is not None:
                pass
                # inbox_id = config["inbox_id"]
                # if inbox_id:
                #     inbox_category = self.bot.get_channel(inbox_id)
                #     if inbox_category and (isinstance(inbox_category, discord.CategoryChannel)):
                #         pass
                #     else:
                # else:

                # if (isinstance(inbox_category, discord.CategoryChannel)):
                #     # Define permission overwrites

                #     # Create the new category
                #     new_category = await guild.create_category(name=name,
                #                                                overwrites=overwrites,
                #                                                position=(inbox_category.position + 1))
                #     if not category:
                #         try:
                #             category = await asyncio.wait_for(self.bot.fetch_channel(inbox_id), timeout=1)
                #         except Exception:
                #             category = None
                # else:
                #     # NO INBOX --> create this
                # log_id = config["log_id"]

            # No config, create all items
            else:
                if len(guild.categories) == 50:
                    setup_embed.add_field(
                        name="",
                        value="❌ This server is not set up. I was unable to create the ticketing "
                        "category as this server is at 50 total categories already.",
                        inline=False,
                    )
                    await ctx.send(embed=setup_embed)
                    return
                else:
                    # Create the inbox category
                    inbox_category = await guild.create_category(
                        name="Tickets", overwrites=overwrites
                    )
                    if inbox_category:
                        setup_embed.add_field(
                            name="",
                            value="Created the ticketing category: **Tickets**",
                            inline=False,
                        )
                    else:
                        setup_embed.add_field(
                            name="",
                            value="❌ An error occurred on Discord's end. Please retry this command. No "
                            "setup was completed.",
                            inline=False,
                        )
                        await ctx.send(embed=setup_embed)
                        return

                if len(guild.text_channels) > 498:
                    setup_embed.add_field(
                        name="",
                        value="❌ This server is not set up. I was unable to create the log or close "
                        "responses channels as this server is at 499 or above total channels already.",
                    )
                    await ctx.send(embed=setup_embed)
                    return
                else:
                    log_channel = await guild.create_text_channel(
                        name="ticket-log",
                        overwrites=overwrites,
                        category=inbox_category,
                    )
                    if log_channel:
                        setup_embed.add_field(
                            name="",
                            value=f"Created the log channel: <#{log_channel.id}>",
                            inline=False,
                        )

                    responses_channel = await guild.create_text_channel(
                        name="close-responses",
                        overwrites=overwrites,
                        category=inbox_category,
                    )
                    if responses_channel:
                        setup_embed.add_field(
                            name="",
                            value=f"Created the close responses channel: <#{responses_channel.id}>",
                            inline=False,
                        )
                        feedback = await responses_channel.send("**Ticket Feedback**")
                        reports = await responses_channel.send("**Ticket Reports**")

                        # Create threads from each message
                        feedback_thread = await feedback.create_thread(
                            name="Ticket Feedback", auto_archive_duration=10080
                        )
                        setup_embed.add_field(
                            name="",
                            value=f"Created the ticket feedback thread: <#{feedback_thread.id}>",
                            inline=False,
                        )

                        reports_thread = await reports.create_thread(
                            name="Ticket Reports", auto_archive_duration=10080
                        )
                        setup_embed.add_field(
                            name="",
                            value=f"Created the ticket reports thread: <#{reports_thread.id}>",
                            inline=False,
                        )

            await self.bot.data_manager.add_config_to_db(
                guild.id,
                log_channel.id,
                inbox_category.id,
                responses_channel.id,
                feedback_thread.id,
                reports_thread.id,
            )
            await ctx.send(embed=setup_embed)

        except Exception as e:
            raise BotError(f"/setup sent an error: {e}")

    type_group = app_commands.Group(name="type", description="Add a ticket type")

    @type_group.command(name="add", description="Add a new ticket type")
    @checks.is_user_app()
    @checks.is_setup()
    @checks.is_guild_app()
    @app_commands.describe(name="Type name")
    @app_commands.describe(description="Type description")
    @app_commands.describe(emoji="Emoji to show for select option")
    async def add(
        self,
        interaction: discord.Interaction,
        name: Range[str, 1, 45],
        description: Range[str, 1, 200],
        emoji: str = None,
        nsfw: discord.CategoryChannel = None,
        parent: discord.CategoryChannel = None,
        redirect: str = None,
    ):
        try:
            await interaction.response.defer()

            guild = interaction.guild
            config = await self.bot.data_manager.get_or_load_config(guild.id)

            if nsfw and redirect:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Redirect types do not need NSFW categories."
                    )
                )
                return

            if parent:
                types = await self.bot.data_manager.get_or_load_guild_types(guild.id)
                for type in types:
                    if type["category_id"] == parent.id:
                        if type["redirectText"]:
                            await interaction.followup.send(
                                embed=Embeds.error(
                                    description="❌ Cannot use a redirect category as a parent."
                                )
                            )
                            return
                        elif type["sub_type"] != -1:
                            await interaction.followup.send(
                                embed=Embeds.error(
                                    description="❌ Cannot use a sub-type category as a parent."
                                )
                            )
                            return

            inbox_category = guild.get_channel(config["inbox_id"])
            if inbox_category:
                roles = []
                permissions = await self.bot.data_manager.get_or_load_permissions(
                    guild.id
                )
                for role_id in permissions.keys():
                    role = guild.get_role(role_id)
                    roles.append(role)

                overwrites = await get_overwrites(guild, roles)

                # Create the new category
                new_category = await guild.create_category(
                    name=name,
                    overwrites=overwrites,
                    position=(inbox_category.position + 1),
                )

                if new_category:
                    await self.bot.data_manager.add_type_to_db(
                        guild.id,
                        new_category.id,
                        name,
                        description,
                        emoji,
                        parent,
                        redirect,
                        nsfw,
                    )
                    await self.bot.data_manager.get_or_load_guild_types(guild.id, False)

                else:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ Failed to create new category. Please ensure "
                            "bot has **administrator permissions** and this server "
                            "is not at the maximum category / channel limit."
                        )
                    )
            else:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Ticket inbox category not found, please run `/setup` first."
                    )
                )

        except Exception as e:
            logger.exception(f"add_type error: {e}")
            raise BotError(f"/add_type sent an error: {e}")

    @type_group.command(
        name="remove",
        description="Remove a tickets category type, deleting the category",
    )
    @checks.is_admin()
    @checks.is_guild()
    async def remove(self, ctx, category: discord.CategoryChannel):
        return
        try:
            name = category.name
            await self.bot.data_manager.delete_guild_type(ctx.guild.id, category.id)
            await category.delete(reason="Deleted ticket type")

            response_embed = discord.Embed(
                title="", description=f"✅ Removed tickets type for {name}"
            )

            await ctx.send(embed=response_embed)

        except Exception as e:
            raise BotError(f"/remove_type sent an error: {e}")

    @type_group.command(
        name="update", description="Update a ticket type's configuration"
    )
    @checks.is_admin()
    @checks.is_guild()
    async def update(self, ctx, category: discord.CategoryChannel):
        return
        try:
            name = category.name
            await self.bot.data_manager.delete_guild_type(ctx.guild.id, category.id)
            await category.delete(reason="Deleted ticket type")

            response_embed = discord.Embed(
                title="", description=f"✅ Removed tickets type for {name}"
            )

            await ctx.send(embed=response_embed)

        except Exception as e:
            raise BotError(f"/remove_type sent an error: {e}")

    form_group = app_commands.Group(name="form", description="Manage ticket forms")

    @form_group.command(name="set", description="Change the form used by a ticket type")
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(category="Ticket category ID to edit the form for")
    @app_commands.describe(
        form_template="Template for the form, use /form_template to view a pre-made template"
    )
    async def set(self, ctx, category: discord.CategoryChannel, form_template: str):
        return
        try:
            try:
                parsed_form = json.loads(form_template)
            except json.JSONDecodeError as decode_err:
                raise BotError(
                    f"❌ Invalid form template. Please ensure it is valid JSON.\n\nError: `{decode_err}`"
                )

            cleaned_form = validate_and_clean_form_template(parsed_form)
            await self.bot.data_manager.set_form(
                ctx.guild.id, category.id, cleaned_form
            )
            await self.bot.data_manager.get_or_load_guild_types(ctx.guild.id, False)

            response_embed = discord.Embed(
                description=f"✅ Updated form for ticket type `{category.name}`"
            )
            await ctx.send(embed=response_embed)

        except Exception as e:
            logger.exception(f"set_form error: {e}")
            raise BotError(f"/set_form sent an error: {e}")

    @form_group.command(
        name="view", description="Preview how a form template will look"
    )
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(form_template="Form template JSON string")
    async def preview(self, ctx, form_template: str):
        return
        await preview_form_template(ctx, form_template)

    @form_group.command(
        name="preview", description="Preview how a form template will look"
    )
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(form_template="Form template JSON string")
    async def preview(self, ctx, form_template: str):
        return
        await preview_form_template(ctx, form_template)

    @commands.command(name="config")
    @checks.is_admin()
    @checks.is_guild()
    async def config(self, ctx):
        try:
            guild = ctx.guild
            config = await self.bot.data_manager.get_or_load_config(guild.id)
            ai_context = await self.bot.data_manager.get_ai_context(guild.id)

            config_embed = discord.Embed(
                title="Server Config", color=discord.Color.green()
            )
            if guild.icon:
                config_embed.set_author(name=f"{guild.name}", icon_url=guild.icon.url)
            else:
                config_embed.set_author(name=f"{guild.name}")

            log = config["log_id"]
            responses = config["responses_id"]
            feedback = config["feedback_id"]
            reports = config["report_id"]

            accepting = config["accepting"]
            anon = config["anon"]
            logging = config["logging"]
            analytics = config["analytics"]

            def convert_state(state):
                if state.casefold() == "true":
                    return "Enabled"
                else:
                    return "Disabled"

            greeting = config["greeting"]
            if len(greeting) == 0:
                greeting = (
                    "Hi {mention}, thanks for reaching out! We'll get back to you "
                    "as soon as we can.\n\nIn the meantime, please refer to the "
                    "informational channels in our server regarding MailBee and its "
                    "rules."
                )
            closing = config["closing"]
            if len(closing) == 0:
                closing = (
                    "Your ticket has been closed. Please do not reply to this message. "
                    "\n\nIf you require support again in the future, you may open a new ticket."
                    "\n\nHow did we do? Let us know below!"
                )

            config_embed.add_field(
                name="MailBee Channels",
                value=f"Ticket log: <#{log}>\n"
                f"Close responses: <#{responses}>\n"
                f"Feedback thread: <#{feedback}>\n"
                f"Reports thread: <#{reports}>",
                inline=True,
            )
            config_embed.add_field(
                name="Server Settings",
                value=f"Accepting tickets: **{convert_state(accepting)}**\n"
                f"Default anonymous: **{convert_state(anon)}**\n"
                f"History logging: **{convert_state(logging)}**\n"
                f"Analytics: **{convert_state(analytics)}**",
                inline=True,
            )
            config_embed.add_field(name="Greeting", value=greeting, inline=False)
            config_embed.add_field(name="Closing", value=closing, inline=False)

            if ai_context:
                config_embed.add_field(
                    name="AI Context",
                    value=f"Name: {ai_context['name']}\n"
                    f"Description: {ai_context['description']}\n"
                    f"Tone: {ai_context['tone']}\n"
                    f"Reply Guidelines: {ai_context['guidelines']}",
                    inline=False,
                )
            else:
                config_embed.add_field(name="AI Context", value="Not set", inline=False)
            await ctx.send(embed=config_embed)

        except Exception as e:
            logger.exception(f"/config error: {e}")
            raise BotError(f"/config sent an error: {e}")

    @commands.command(name="greeting")
    @checks.is_admin()
    @checks.is_guild()
    async def greeting(self, ctx, *, greeting: str):
        try:
            guild = ctx.guild
            moderation = self.bot.get_cog("Moderation")
            if moderation is not None:
                greeting = await convert_mentions(self.bot, greeting, guild)

            if len(greeting) > 1000:
                error_embed = discord.Embed(
                    description="❌ Greeting text is too long, must be at most 1000 characters",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=error_embed)
                return

            await self.bot.data_manager.set_greeting(guild.id, greeting)
            await self.bot.data_manager.get_or_load_config(guild.id, False)

            success_embed = discord.Embed(
                description=f"✅ **Greeting set:**\n{greeting}",
                color=discord.Color.green(),
            )
            await ctx.send(embed=success_embed)

        except Exception as e:
            logger.exception(f"/greeting error: {e}")
            raise BotError(f"/greeting sent an error: {e}")

    @commands.command(name="closing")
    @checks.is_admin()
    @checks.is_guild()
    async def closing(self, ctx, *, closing: str):
        try:
            guild = ctx.guild
            moderation = self.bot.get_cog("Moderation")
            if moderation is not None:
                closing = await convert_mentions(self.bot, closing, guild)

            if len(closing) > 1000:
                error_embed = discord.Embed(
                    description="❌ Closing text is too long, must be at most 1000 characters",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=error_embed)
                return

            await self.bot.data_manager.set_closing(guild.id, closing)
            await self.bot.data_manager.get_or_load_config(guild.id, False)

            success_embed = discord.Embed(
                description=f"✅ **Closing set:**\n{closing}",
                color=discord.Color.green(),
            )
            await ctx.send(embed=success_embed)

        except Exception as e:
            logger.exception(f"/closing error: {e}")
            raise BotError(f"/closing sent an error: {e}")

    @commands.command(name="accepting")
    @checks.is_admin()
    @checks.is_guild()
    async def accepting(
        self,
        ctx,
        *,
        accepting: str = (
            "The server you are attempting to contact is not "
            "currently accepting new tickets. Please try again "
            "later."
        ),
    ):
        try:
            guild = ctx.guild
            moderation = self.bot.get_cog("Moderation")
            if moderation is not None:
                accepting = await convert_mentions(self.bot, accepting, guild)

            if len(accepting) > 2000:
                error_embed = discord.Embed(
                    description="❌ Accepting text is too long, must be at most 2000 characters",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=error_embed)
                return

            success_embed = discord.Embed(description="", color=discord.Color.green())

            config = await self.bot.data_manager.get_or_load_config(guild.id)
            if config["accepting"] == "true":
                success_embed.description = (
                    f"✅ Ticket creation disabled with message:\n{accepting}"
                )
                await self.bot.data_manager.set_ticket_accepting(guild.id, accepting)
                await ctx.send(embed=success_embed)
            else:
                success_embed.description = "✅ Ticket creation enabled"
                await self.bot.data_manager.set_ticket_accepting(guild.id, "true")
                await ctx.send(embed=success_embed)

            await self.bot.data_manager.get_or_load_config(guild.id, False)

        except Exception as e:
            logger.exception(f"/accepting error: {e}")
            raise BotError(f"/accepting sent an error: {e}")

    @commands.command(name="anon")
    @checks.is_admin()
    @checks.is_guild()
    async def anon(self, ctx):
        try:
            guild = ctx.guild
            config = await self.bot.data_manager.get_or_load_config(guild.id)
            success_embed = discord.Embed(description="", color=discord.Color.green())
            if config["anon"] == "true":
                success_embed.description = f"✅ Moderator anonyminity setting changed to: **default non-anonymous**"
                await self.bot.data_manager.set_anon_status(guild.id, "false")
                await ctx.send(embed=success_embed)
            else:
                success_embed.description = f"✅ Moderator anonyminity setting changed to: **default anonymous**"
                await self.bot.data_manager.set_anon_status(guild.id, "true")
                await ctx.send(embed=success_embed)

            await self.bot.data_manager.get_or_load_config(guild.id, False)

        except Exception as e:
            logger.exception(f"/anon error: {e}")
            raise BotError(f"/anon sent an error: {e}")

    @commands.command(name="pingrole")
    @checks.is_admin()
    @checks.is_guild()
    async def pingrole(self, ctx, *, role_ids=None):
        try:
            guild = ctx.guild
            if role_ids is None:
                await self.bot.data_manager.set_ping_roles(guild.id, [])
                await ctx.send(
                    embed=discord.Embed(
                        description="✅ Cleared ping roles", color=discord.Color.green()
                    )
                )
                return

            role_ids = role_ids.split()
            valid_role_ids = []
            for role_id in role_ids:
                try:
                    role = guild.get_role(int(role_id))
                    if role:
                        valid_role_ids.append(role_id)
                    else:
                        await ctx.send(
                            embed=discord.Embed(
                                description=f"❌ Role ID {role_id} not found in this server",
                                color=discord.Color.red(),
                            )
                        )
                        return
                except ValueError:
                    await ctx.send(
                        embed=discord.Embed(
                            description=f"❌ Invalid role ID: {role_id}",
                            color=discord.Color.red(),
                        )
                    )
                    return

            await self.bot.data_manager.set_ping_roles(guild.id, valid_role_ids)
            await self.bot.data_manager.get_or_load_guild_types(guild.id, False)
            await ctx.send(
                embed=discord.Embed(
                    description=f"✅ Set ping role(s) to: {' '.join(f'<@&{id}>' for id in valid_role_ids)}",
                    color=discord.Color.green(),
                )
            )

        except Exception as e:
            logger.exception(f"/pingrole error: {e}")
            raise BotError(f"/pingrole sent an error: {e}")

    ai_group = app_commands.Group(name="ai_context", description="Manage ai context")

    @ai_group.command(name="set", description="Set the AI response context")
    @checks.is_admin_app()
    @checks.is_guild_app()
    @app_commands.describe(name="Name of this server or organization")
    @app_commands.describe(description="Description of your server or organization")
    @app_commands.describe(tone="Tone to use in AI responses")
    @app_commands.describe(guidelines="Guidelines for the AI to follow in responses")
    async def ai_context(
        self,
        interaction: discord.Interaction,
        name: Range[str, 1, 100],
        description: Range[str, 1, 300],
        tone: Range[str, 1, 100],
        guidelines: Range[str, 1, 500],
    ):
        try:
            await interaction.response.defer()
            guild = interaction.guild

            context = {
                "name": name,
                "description": description,
                "tone": tone,
                "guidelines": guidelines,
            }

            await self.bot.data_manager.set_ai_context(guild.id, context)

            response = Embeds.success(
                description=f"✅ Updated AI context settings:"
                f"\n{build_server_context(context)}"
            )
            await interaction.followup.send(embed=response)

        except Exception as e:
            logger.exception(f"/ai_context error: {e}")
            raise BotError(f"/ai_context sent an error: {e}")

    @ai_group.command(name="remove", description="Remove the AI response context")
    @checks.is_admin_app()
    @checks.is_guild_app()
    async def ai_context_remove(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            guild = interaction.guild

            await self.bot.data_manager.remove_ai_context(guild.id)

            response = Embeds.success(description="✅ Cleared AI context settings.")
            await interaction.followup.send(embed=response)

        except Exception as e:
            logger.exception(f"/ai_context_remove error: {e}")
            raise BotError(f"/ai_context_remove sent an error: {e}")

    # Show roles with the 'Bot Admin' permission or all monitored channels / categories
    @commands.hybrid_command(
        name="show",
        description="List this server's role permissions or monitored channels and categories",
    )
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(
        selection="Select to show either server role permissions or monitored channels"
    )
    @app_commands.choices(
        selection=[
            app_commands.Choice(name="role permissions", value="role permissions"),
        ]
    )
    async def show(self, ctx, selection: discord.app_commands.Choice[str]):
        try:
            choice = selection.value
            this_guild_id = ctx.guild.id
            guildName = (self.bot.get_guild(this_guild_id)).name

            if choice == "role permissions":
                search_access = [
                    (role_id, perm_level)
                    for guild_id, role_id, perm_level in self.bot.data_manager.access_roles
                    if guild_id == this_guild_id
                ]
                perms_embed = discord.Embed(
                    title=f"Server Role Permissions",
                    description=f"Roles with access to Mantid in: **{guildName}** ({this_guild_id})",
                    color=discord.Color.green(),
                )

                if len(search_access) == 0:
                    perms_embed.description = ""
                    perms_embed.color = discord.Color.red()
                    perms_embed.add_field(
                        name="",
                        value="No permissions set, run **/edit permissions** to add one",
                        inline=False,
                    )
                else:
                    for row in search_access:
                        perms_embed.add_field(
                            name="",
                            value=f"{emojis.mantis} <@&{row[0]}> - **{row[1]}**",
                            inline=False,
                        )

                await ctx.send(embed=perms_embed)

        except Exception as e:
            raise BotError(f"/show sent an error: {e}")

    # Edit roles with the 'Bot Admin' permission
    @commands.hybrid_command(
        name="edit_permissions",
        description="Add or remove roles that can use Mantid in this server",
    )
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(
        action="Desired edit action. Use 'add' to grant permissions and 'remove' to delete them"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
        ]
    )
    @app_commands.describe(role="Selected role")
    @app_commands.describe(
        level="Permission level. Bot users can only use moderation-specific commands"
    )
    @app_commands.choices(
        level=[
            app_commands.Choice(name="Bot User", value="user"),
            app_commands.Choice(name="Bot Admin", value="admin"),
        ]
    )
    async def edit_permissions(
        self,
        ctx,
        action: discord.app_commands.Choice[str],
        role: discord.Role,
        level: discord.app_commands.Choice[str],
    ):
        try:
            this_guild_id = ctx.guild.id
            choice = action.value
            level_name = level.name
            level_value = level.value
            this_role_id = role.id

            edit_embed = discord.Embed(
                title=f"Edit Results", description="", color=discord.Color.green()
            )

            # Check if access is already given, if not add it
            if choice == "add":
                search_access = [
                    (role_id, perm_level)
                    for guild_id, role_id, perm_level in self.bot.data_manager.access_roles
                    if (role_id == this_role_id)
                ]
                if len(search_access) != 0:
                    perm = search_access[0][1]
                    if perm == level_name:
                        edit_embed.description = f"Unable to add permissions, <@&{this_role_id}> already has **{perm}**"
                        edit_embed.color = discord.Color.red()
                    else:
                        query = f"""
                        UPDATE permissions 
                        SET permissions.perm_level = '{level_name}'
                        WHERE (permissions.role_id = {this_role_id});
                        """
                        await self.bot.data_manager.execute_query(query, False)
                        await self.bot.data_manager.update_cache(0)
                        await self.bot.data_manager.get_or_load_permissions(
                            this_guild_id, False
                        )
                        edit_embed.description = f"Updated permissions to **{level_name}** for <@&{this_role_id}>"
                else:
                    query = f"""
                        INSERT INTO permissions VALUES 
                        ({this_guild_id}, 
                        {this_role_id}, 
                        '{level_name}');
                        """
                    await self.bot.data_manager.execute_query(query, False)
                    await self.bot.data_manager.update_cache(0)
                    await self.bot.data_manager.get_or_load_permissions(
                        this_guild_id, False
                    )
                    edit_embed.description = (
                        f"Added **{level_name}** permissions to <@&{this_role_id}>"
                    )

            # Check if user has access, if not do nothing
            if choice == "remove":
                search_access = [
                    (role_id, perm_level)
                    for guild_id, role_id, perm_level in self.bot.data_manager.access_roles
                    if (role_id == this_role_id)
                ]
                if len(search_access) != 0:
                    perm = search_access[0][1]
                    if perm == level_name:
                        query = f"""
                            DELETE FROM permissions WHERE 
                            (permissions.role_id = {this_role_id});
                            """
                        await self.bot.data_manager.execute_query(query, False)
                        await self.bot.data_manager.update_cache(0)
                        await self.bot.data_manager.get_or_load_permissions(
                            this_guild_id, False
                        )
                        edit_embed.description = f"Removed **{level_name}** permissions from <@&{this_role_id}>"
                else:
                    edit_embed.description = f"Unable to remove permissions, <@&{this_role_id}> does not have this permission"
                    edit_embed.color = discord.Color.red()

            await ctx.send(embed=edit_embed)

        except Exception as e:
            raise BotError(f"/edit_permissions sent an error: {e}")


async def setup(bot):
    await bot.add_cog(Config(bot))
