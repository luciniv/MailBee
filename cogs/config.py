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
from utils.helpers import *
from classes.paginator import *
from classes.ticket_opener import get_overwrites
from utils import checks, emojis
from utils.logger import *


class ExampleMessage(discord.ui.View):
    def __init__(self, form):
        super().__init__(timeout=300)
        self.add_item(ExampleButton(form))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class ExampleButton(discord.ui.Button):
    def __init__(self, modal_template):
        super().__init__(style=discord.ButtonStyle.success, label="Open Example Form")
        self.modal_template = modal_template

    async def callback(self, interaction: discord.Interaction):
        await send_modal(interaction, self.modal_template)


async def send_modal(interaction, modal_template):
    title = modal_template.get("title", "Form")
    fields = modal_template.get("fields", [])
    await interaction.response.send_modal(ExampleFormModal(title, fields))


class ExampleFormModal(discord.ui.Modal):
    def __init__(self, title, fields):
        super().__init__(title=title)
        self.values = {}

        for field in fields:
            input = discord.ui.TextInput(
                label=field["label"],
                placeholder=field.get("placeholder", ""),
                style=(
                    discord.TextStyle.paragraph
                    if field["style"] == "paragraph"
                    else discord.TextStyle.short
                ),
                min_length=field.get("min_length", 1),
                max_length=field.get("max_length", 1024),
                required=field.get("required", True),
            )
            self.add_item(input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=Embeds.success(description="Mock submission sent"), ephemeral=True
        )


class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _key_format_types(self, guild_id):
        types = await self.bot.data_manager.get_or_load_guild_types(guild_id)
        type_dict = {str(type["type_id"]): type for type in types}
        return type_dict

    def _validate_subtype(self, types, parent_id):
        type = types[str(parent_id)]

        if type["redirect_text"]:
            return False, "❌ Cannot use a redirect category as a parent."
        elif type["parent_id"]:
            return False, "❌ Cannot use a sub-type category as a parent."
        return True, None

    async def _load_type_choices(
        self, guild: discord.Guild
    ) -> List[app_commands.Choice[str]]:
        if not guild:
            return []

        types_raw = await self.bot.data_manager.get_or_load_guild_types(guild.id)
        types = [
            (
                f"{safe_partial_emoji(type['type_emoji'])} {type['type_name']}",
                f"{safe_partial_emoji(type['type_emoji'])} {type['type_name']},{type['type_id']}",
            )
            for type in types_raw
        ]
        choices = [app_commands.Choice(name=type[0], value=type[1]) for type in types]

        return choices

    def _get_line(self, form_text_list):
        if form_text_list:
            return form_text_list.pop(0).strip()
        else:
            return None

    def _check_prefix(self, line, prefix):
        if not line:
            return False
        return re.match(rf"^{prefix}:", line, re.IGNORECASE)

    def _remove_prefix(self, line, prefix):
        return re.sub(rf"^{prefix}:\s*", "", line, flags=re.IGNORECASE).strip()

    def _parse_form(self, form_text):
        if not form_text or form_text.strip() == "":
            return None, None, "❌ Form text cannot be empty."

        form_text = form_text.splitlines()
        line = self._get_line(form_text)
        index = 1
        fields = []

        if not self._check_prefix(line, "Title"):
            return None, index, "❌ Expected 'Title:' line."
        else:
            title = self._remove_prefix(line, "Title")
            if len(title) == 0:
                return None, index, "❌ Title cannot be empty."
            elif len(title) > 45:
                return None, index, "❌ Title cannot exceed 45 characters."

            line = self._get_line(form_text)
            index += 1

        while line or line == "":
            print(f"entered while loop, line: {line}")
            if line == "":
                pass

            elif self._check_prefix(line, "Question"):
                question = self._remove_prefix(line, "Question")
                if len(question) == 0:
                    return None, index, "❌ Question text cannot be empty."
                elif len(question) > 45:
                    return None, index, "❌ Question text cannot exceed 45 characters."

                line = self._get_line(form_text)
                index += 1
                print(f"after question, line: {line}")
                if self._check_prefix(line, "Placeholder"):
                    placeholder = self._remove_prefix(line, "Placeholder")
                    if len(placeholder) == 0:
                        placeholder = None
                    elif len(placeholder) > 100:
                        return (
                            None,
                            index,
                            "❌ Placeholder text cannot exceed 100 characters.",
                        )

                    line = self._get_line(form_text)
                    index += 1
                    print(f"after placeholder, line: {line}")
                    if self._check_prefix(line, "Style"):
                        style = self._remove_prefix(line, "Style").lower()
                        if style not in ["paragraph", "short"]:
                            return (
                                None,
                                index,
                                "❌ Style field must be either 'paragraph' or 'short'.",
                            )

                        line = self._get_line(form_text)
                        index += 1
                        print(f"after style, line: {line}")
                        if self._check_prefix(line, "Min"):
                            min = self._remove_prefix(line, "Min").lower()
                            if not min.isdigit():
                                return (
                                    None,
                                    index,
                                    "❌ Min field must be an integer.",
                                )
                            elif int(min) < 0 or int(min) > 1024:
                                return (
                                    None,
                                    index,
                                    "❌ Min field must be between 0 and 1024.",
                                )

                            line = self._get_line(form_text)
                            index += 1
                            print(f"after min, line: {line}")
                            if self._check_prefix(line, "Max"):
                                max = self._remove_prefix(line, "Max").lower()
                                if not max.isdigit():
                                    return (
                                        None,
                                        index,
                                        "❌ Max field must be an integer.",
                                    )
                                elif int(max) < 1 or int(max) > 1024:
                                    return (
                                        None,
                                        index,
                                        "❌ Max field must be between 1 and 1024.",
                                    )
                                elif int(max) < int(min):
                                    return (
                                        None,
                                        index,
                                        "❌ Max field must be greater than or equal to Min field.",
                                    )

                                line = self._get_line(form_text)
                                index += 1
                                print(f"after max, line: {line}")
                                if self._check_prefix(line, "Required"):
                                    required = self._remove_prefix(
                                        line, "Required"
                                    ).lower()
                                    if required == "true":
                                        required = True
                                    elif required == "false":
                                        required = False
                                    else:
                                        return (
                                            None,
                                            index,
                                            "❌ Required field must be either 'true' or 'false'.",
                                        )

                                    field = {
                                        "label": question,
                                        "placeholder": placeholder,
                                        "style": style,
                                        "min_length": min,
                                        "max_length": max,
                                        "required": required,
                                    }
                                    fields.append(field)
                                    if len(fields) > 5:
                                        return (
                                            None,
                                            index,
                                            "❌ Cannot have more than 5 questions in a form.",
                                        )
                                    print(
                                        f"after fields append, fields: {fields}, line: {line}"
                                    )

                                else:
                                    return None, index, "❌ Expected 'Required:' line."
                            else:
                                return None, index, "❌ Expected 'Max:' line."
                        else:
                            return None, index, "❌ Expected 'Min:' line."
                    else:
                        return None, index, "❌ Expected 'Style:' line."
                else:
                    return None, index, "❌ Expected 'Placeholder:' line."
            else:
                return None, index, "❌ Expected 'Question:' line."

            line = self._get_line(form_text)
            index += 1
            print(f"end of while loop, line: {line}")

        print(f"returning, fields: {fields}, line: {line}")
        return {"title": title, "fields": fields}, None, None

    async def _make_form_embed(self, form_json):
        title = form_json["title"]
        fields = form_json["fields"]

        embed = Embeds.success(title=title)

        for field in fields:
            embed.add_field(
                name=f"{field['label']}",
                value=f"**Placeholder:** {field.get('placeholder', 'N/A')}\n"
                f"**Style:** {field['style'].capitalize()}\n"
                f"**Min Length:** {field.get('min_length', 1)}\n"
                f"**Max Length:** {field.get('max_length', 1024)}\n"
                f"**Required:** {field.get('required', True)}",
                inline=False,
            )
        return embed

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
    @app_commands.describe(
        name="Type name",
        description="Type description",
        emoji="Emoji to show for select option",
        category="Destination category for this ticket type",
        parent="Parent type if this is a sub-type",
        nsfw="NSFW category for this type",
        redirect="Redirect text or message ID for redirect types",
        ping_role="Role(s) to ping when a ticket is created with this type",
    )
    async def type_add(
        self,
        interaction: discord.Interaction,
        name: Range[str, 1, 45],
        description: Range[str, 1, 200],
        emoji: str = None,
        category: discord.CategoryChannel = None,
        parent: str = None,
        nsfw: discord.CategoryChannel = None,
        redirect: str = None,
        ping_role: discord.Role = None,
    ):
        try:
            await interaction.response.defer()
            guild = interaction.guild
            category_id = category.id if category else None
            config = await self.bot.data_manager.get_or_load_config(guild.id)

            if nsfw and redirect:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Redirect types do not need NSFW categories."
                    )
                )
                return

            types = await self._key_format_types(guild.id)

            parent_id = None
            if parent:
                types = await self.bot.data_manager.get_or_load_ticket_types(guild.id)
                for type in types:
                    if type["category_id"] == parent.id:
                        if type["redirect_text"]:
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
                if not category_id:
                    if parent_id:
                        category_id = types[str(parent_id)]["category_id"]
                    else:
                        roles = []
                        permissions = (
                            await self.bot.data_manager.get_or_load_permissions(
                                guild.id
                            )
                        )
                        for role_id in permissions.keys():
                            role = guild.get_role(role_id)
                            roles.append(role)

                        overwrites = await get_overwrites(guild, roles)

                        try:
                            # Create the new category
                            new_category = await guild.create_category(
                                name=name,
                                overwrites=overwrites,
                                position=(inbox_category.position + 1),
                            )
                        except Exception:
                            await interaction.followup.send(
                                embed=Embeds.error(
                                    description="❌ Failed to create ticket category."
                                )
                            )
                            return

                if new_category:
                    await self.bot.data_manager.add_type_to_db(
                        parent_id,
                        None,
                        guild.id,
                        new_category.id,
                        nsfw.id if nsfw else None,
                        name,
                        description,
                        emoji,
                        redirect,
                        ping_role,
                    )
                    await self.bot.data_manager.get_or_load_ticket_types(
                        guild.id, False
                    )

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
            logger.exception(f"type_add error: {e}")
            raise BotError(f"/type_add sent an error: {e}")

    @type_add.autocomplete("parent")
    async def type_add_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        choices = await self._load_type_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    @type_group.command(
        name="remove",
        description="Remove a ticket type",
    )
    @checks.is_admin()
    @checks.is_guild()
    async def type_remove(self, interaction: discord.Interaction, type: str):
        try:
            await interaction.response.defer()
            guild_id = interaction.guild.id
            type_name, type_id = type.split(",")

            await self.bot.data_manager.delete_type_from_db(type_id)
            await self.bot.data_manager.get_or_load_guild_types(guild_id, False)

            await interaction.followup.send(
                embed=Embeds.success(description=f"✅ Removed ticket type {type_name}")
            )

        except Exception as e:
            raise BotError(f"/type_remove sent an error: {e}")

    @type_remove.autocomplete("type")
    async def type_remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        choices = await self._load_type_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    @type_group.command(name="edit", description="Edit a ticket type's configuration")
    @checks.is_user_app()
    @checks.is_setup()
    @checks.is_guild_app()
    @app_commands.describe(
        type="Ticket type to edit",
        name="Type name",
        description="Type description",
        emoji="Emoji to show for select option",
        category="Destination category for this ticket type",
        parent="Parent type if this is a sub-type",
        nsfw="NSFW category for this type",
        redirect="Redirect text for redirect types",
        ping_role="Role to ping when a ticket is created with this type",
    )
    async def type_edit(
        self,
        interaction: discord.Interaction,
        type: str,
        name: Range[str, 1, 45] = None,
        description: Range[str, 1, 200] = None,
        emoji: str = None,
        category: discord.CategoryChannel = None,
        parent: str = None,
        nsfw: discord.CategoryChannel = None,
        redirect: str = None,
        ping_role: discord.Role = None,
    ):
        try:
            await interaction.response.defer()
            guild = interaction.guild
            type_name, type_id = type.split(",")

            if nsfw and redirect:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Redirect types do not need NSFW categories."
                    )
                )
                return

            parent_id = None
            if parent:
                parent_id = parent.value
                self._validate_subtype(type, parent_id)
                # FIXME MORE TO DO HERE!!!

            await self.bot.data_manager.update_type(
                type_id,
                parent_id,
                category.id,
                nsfw.id if nsfw else None,
                name,
                description,
                emoji,
                redirect,
                ping_role,
            )
            await self.bot.data_manager.get_or_load_guild_types(guild.id, False)

        except Exception as e:
            logger.exception(f"/type_update error: {e}")
            raise BotError(f"/type_update sent an error: {e}")

    @type_edit.autocomplete("type")
    async def type_update_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        choices = await self._load_type_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    @type_edit.autocomplete("parent")
    async def type_update_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        choices = await self._load_type_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    form_group = app_commands.Group(name="form", description="Manage ticket forms")

    @form_group.command(
        name="edit", description="Change the form used by a ticket type"
    )
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(type="Ticket type to edit the form for")
    @app_commands.describe(message_id="ID of the message containing the form template")
    async def form_edit(
        self, interaction: discord.Interaction, type: str, message_id: str
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            channel = interaction.channel
            message, response = await fetch_channel_message(channel, message_id)
            if response:
                await interaction.response.send_message(
                    embed=Embeds.error(description=response)
                )
                return

            form_content, index, error = self._parse_form(message.content)
            if error:
                await interaction.followup.send(
                    embed=Embeds.error(description=f"{error} (line {index})")
                )
                return

            type_name, type_id = type.split(",")
            await self.bot.data_manager.set_form(type_id, form_content)
            await self.bot.data_manager.get_or_load_guild_types(
                interaction.guild.id, False
            )
            await interaction.followup.send(
                embed=Embeds.success(
                    description=f"✅ Updated form for ticket type {type_name}"
                )
            )

        except Exception as e:
            logger.exception(f"form edit error: {e}")
            raise BotError(f"/form edit sent an error: {e}")

    @form_edit.autocomplete("type")
    async def form_edit_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        choices = await self._load_type_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    @form_group.command(name="view", description="View the form for a ticket type")
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(type="Ticket type to view the form of")
    async def form_view(self, interaction: discord.Interaction, type: str):
        try:
            await interaction.response.defer(ephemeral=False)
            guild_id = interaction.guild.id
            type_name, type_id = type.split(",")
            form = None

            types = await self._key_format_types(guild_id)
            form = types[type_id]["form"]

            form_embed = await self._make_form_embed(form)
            await interaction.followup.send(embed=form_embed, view=ExampleMessage(form))

        except Exception as e:
            logger.exception(f"form view error: {e}")
            raise BotError(f"/form view sent an error: {e}")

    @form_view.autocomplete("type")
    async def form_view_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        choices = await self._load_type_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    @form_group.command(
        name="preview", description="Preview how a form template will look"
    )
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(message_id="ID of the message containing the form template")
    async def form_preview(self, interaction: discord.Interaction, message_id: str):
        try:
            await interaction.response.defer(ephemeral=True)
            channel = interaction.channel
            message, response = await fetch_channel_message(channel, message_id)
            if response:
                await interaction.response.send_message(
                    embed=Embeds.error(description=response)
                )
                return

            form, index, error = self._parse_form(message.content)
            if error:
                await interaction.followup.send(
                    embed=Embeds.error(description=f"{error} (line {index})")
                )
                return

            form_embed = await self._make_form_embed(form)
            await interaction.followup.send(embed=form_embed, view=ExampleMessage(form))

        except Exception as e:
            logger.exception(f"form edit error: {e}")
            raise BotError(f"/form edit sent an error: {e}")

    @form_group.command(
        name="example", description="Display an example template and form"
    )
    @checks.is_admin()
    @checks.is_guild()
    async def form_example(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            explanation = (
                "**Editing a form? Use the example template below as a reference.**\n"
                "Forms are created from text templates (similar to snips) "
                "and must follow these rules:\n"
                "- Maximum of **5** questions\n"
                "- **Question:** up to 45 characters\n"
                "- **Placeholder:** up to 100 characters\n"
                "- **Style:** short or paragraph\n"
                "- **Min:** 0–1024\n"
                "- **Max:** 1–1024\n"
                "- **Required:** true or false\n\n"
                "Leaving a field blank will result in an error or a default value "
                "(it’s recommended to fill out every field). "
                "When formatting your input:\n"
                "- The title must be the first line\n"
                "- Each field must start with its indicator "
                "(e.g., Question: or Placeholder:)\n"
                "- Follow the same field order as the example\n"
                "- Do not add line breaks within a field — each new line is treated "
                "as a new field\n"
                "- Extra blank lines between questions are allowed"
            )
            explanation_embed = Embeds.info(description=explanation)

            form_text = (
                "Title: Example Support Form\n"
                "Question: What is your issue?\n"
                "Placeholder: Describe your issue here...\n"
                "Style: paragraph\n"
                "Min: 10\n"
                "Max: 500\n"
                "Required: true\n\n"
                "Question: How urgent is this?\n"
                "Placeholder: From 1 to 10\n"
                "Style: short\n"
                "Min: 1\n"
                "Max: 50\n"
                "Required: false"
            )

            form, index, error = self._parse_form(form_text)
            if error:
                await interaction.followup.send(
                    embed=Embeds.error(description=f"{error} (line {index})")
                )
                return

            text_embed = Embeds.info(description=f"```{form_text}```")
            form_embed = await self._make_form_embed(form)
            await interaction.followup.send(
                embeds=[
                    explanation_embed,
                    text_embed,
                    form_embed,
                ],
                view=ExampleMessage(form),
            )

        except Exception as e:
            logger.exception(f"form view error: {e}")
            raise BotError(f"/form view sent an error: {e}")

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
            await self.bot.data_manager.get_or_load_ticket_types(guild.id, False)
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
