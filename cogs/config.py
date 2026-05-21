import asyncio
import json
import re

import discord
import emoji as emj
from discord import SelectOption, app_commands
from discord.app_commands import Range
from discord.ext import commands

from ai_integration.prompt import build_server_context
from classes.embeds import Embeds
from classes.error_handler import *
from classes.paginator import *
from classes.ticket_opener import get_overwrites
from classes.ticket_submitter import TimeoutSafeView
from utils import checks
from utils.emojis import *
from utils.helpers import *
from utils.logger import *


class ExampleMessage(TimeoutSafeView):
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


class TypeOrderView(TimeoutSafeView):
    def __init__(self, bot, guild_id, type_id, neighbors):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.type_id = type_id
        self.neighbors = neighbors
        self.add_item(OrderSelect(bot, guild_id, type_id, neighbors))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class OrderSelect(discord.ui.Select):
    def __init__(self, bot, guild_id, type_id, neighbors):
        options = [
            SelectOption(label=f"Position {i + 1}", value=str(i))
            for i in range(len(neighbors))
        ]

        super().__init__(
            placeholder="Choose a new position...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.bot = bot
        self.guild_id = guild_id
        self.type_id = type_id
        self.neighbors = neighbors

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        new_index = int(self.values[0])

        type_data = await self.bot.data_manager.get_ticket_type(
            self.guild_id, self.type_id
        )
        emoji = type_data["type_emoji"]
        name = type_data["type_name"]
        current_index = type_data["order_id"]

        if new_index == current_index:
            await interaction.followup.send(
                embed=Embeds.error(
                    description="❌ This type is already in the selected position."
                )
            )
            return

        config = self.bot.get_cog("Config")
        await config._reorder_types(
            current_index, new_index, self.neighbors, self.guild_id
        )
        await self.bot.data_manager.get_or_load_guild_types(self.guild_id, False)
        await interaction.channel.send(
            embed=Embeds.success(
                description=f"✅ Moved type **{emoji} {name}** to position {new_index + 1}."
            )
        )
        try:
            await interaction.message.delete()
        except discord.errors.HTTPException:
            pass
        if self.view:
            self.view.stop()


class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _key_format_types(self, guild_id):
        types = await self.bot.data_manager.get_or_load_guild_types(guild_id)
        type_dict = {str(type["type_id"]): type for type in types}
        return type_dict

    async def _list_format_types(self, guild_id):
        types = await self.bot.data_manager.get_or_load_guild_types(guild_id)

        parent_list = []
        subtype_list = []
        subtypes_to_remove = []
        for type in types:
            if type["sub_type"] == -1:
                parent_list.append(
                    {
                        "data": type,
                        "sub_types": [],
                    }
                )
            else:
                subtype_list.append({"data": type})

        for parent in parent_list:
            for subtype in subtype_list:
                if subtype["data"]["sub_type"] == parent["data"]["category_id"]:
                    parent["sub_types"].append(subtype)
                    subtypes_to_remove.append(subtype)

            for subtype in subtypes_to_remove:
                subtype_list.remove(subtype)
            subtypes_to_remove = []

        return parent_list

    # list of parents, data field gives type, subtype field gives subtype list
    # each subtype in list has a data field as well that gives the type

    async def _load_type_choices(
        self, guild: discord.Guild
    ) -> List[app_commands.Choice[str]]:
        if not guild:
            return []

        types_raw = await self.bot.data_manager.get_or_load_guild_types(guild.id)
        types = [
            (
                f"{safe_partial_emoji(type['type_emoji'])} {type['type_name']}",
                f"{safe_partial_emoji(type['type_emoji'])} {type['type_name']},{type['type_id']},{type['sub_type']}",
            )
            for type in types_raw
        ]
        choices = [app_commands.Choice(name=type[0], value=type[1]) for type in types]

        return choices

    async def _load_parent_type_choices(
        self, guild: discord.Guild
    ) -> List[app_commands.Choice[str]]:
        if not guild:
            return []

        types_raw = await self.bot.data_manager.get_or_load_guild_types(guild.id)
        types = [
            (
                f"{safe_partial_emoji(type['type_emoji'])} {type['type_name']}",
                f"{safe_partial_emoji(type['type_emoji'])} {type['type_name']},{type['type_id']},{type['category_id']}",
            )
            for type in types_raw
            if not type["redirectText"] and type["sub_type"] == -1
        ]
        choices = [app_commands.Choice(name=type[0], value=type[1]) for type in types]

        return choices

    async def _categorize_type(self, type_data, guild_id):
        if type_data["category_id"] == 0:
            return "redirect"

        elif type_data["sub_type"] == -1:
            types = await self.bot.data_manager.get_or_load_guild_types(guild_id)
            for ticket_type in types:
                if ticket_type["sub_type"] == type_data["category_id"]:
                    return "parent"
            return "normal"
        else:
            return "subtype"

    async def _reorder_types(self, current_index, new_index, neighbors, guild_id):
        new_list = neighbors.copy()
        item = new_list.pop(current_index)

        if new_index is not None:
            new_list.insert(new_index, item)

        updates = []
        for idx, entry in enumerate(new_list):
            type_id = entry["data"]["type_id"]
            if entry["data"]["order_id"] != idx:
                updates.append((type_id, idx))

        if updates:
            await self.bot.data_manager.update_type_order(guild_id, updates)

    def _check_emoji(self, emoji_str):
        if emoji_str in emj.EMOJI_DATA:
            return emoji_str
        return None

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

        return {"title": title, "fields": fields}, None, None

    async def _make_form_embed(self, form_json):
        title = form_json["title"]
        fields = form_json["fields"]

        embed = Embeds.success(title=f"Title: {title}")

        for index, field in enumerate(fields, start=1):
            embed.add_field(
                name=f"{index}) {field['label']}",
                value=f"**Placeholder:** {field.get('placeholder', 'N/A')}\n"
                f"**Style:** {field['style'].capitalize()}\n"
                f"**Min Length:** {field.get('min_length', 1)}\n"
                f"**Max Length:** {field.get('max_length', 1024)}\n"
                f"**Required:** {field.get('required', True)}",
                inline=False,
            )
        return embed

    async def _fetch_ping_roles(self, guild, role_ids):
        role_ids = role_ids.split()
        valid_role_ids = []
        for role_id in role_ids:
            try:
                role = guild.get_role(int(role_id))
                if role:
                    valid_role_ids.append(role_id)
                else:
                    return [], f"❌ Role ID {role_id} not found in this server"

            except ValueError:
                return [], f"❌ Invalid role ID: {role_id}"

        return valid_role_ids, None

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

    # TODO: Rework ticket type system, notably use of "-1" values and subtyping logic
    # Also create better data calls, pull one ticket type by ID from the cache
    # There's a lot to improve, but it'll help a ton in the long run

    @type_group.command(name="view", description="View one or all ticket types")
    @checks.is_user_app()
    @checks.is_setup()
    @checks.is_guild_app()
    @app_commands.describe(type="Ticket type to view, leave blank to view all types")
    async def type_view(self, interaction: discord.Interaction, type: str = None):
        try:
            await interaction.response.defer()
            guild_id = interaction.guild.id
            sorted_types = await self._list_format_types(guild_id)

            if type:
                type_name, type_id, type_subtype_id = type.split(",")
                type_data = None
                subtypes = None
                type_parent = None
                for parent in sorted_types:
                    if parent["data"]["type_id"] == int(type_id):
                        type_data = parent["data"]
                        subtypes = parent["sub_types"]
                        break
                    for subtype in parent["sub_types"]:
                        if subtype["data"]["type_id"] == int(type_id):
                            type_data = subtype["data"]
                            type_parent = parent["data"]
                            break

                embed = Embeds.success(
                    title=f"Ticket Type: {type_data['type_emoji']} {type_data['type_name']}",
                    description=type_data["type_descrip"],
                )
                if subtypes:
                    sub_type_list = ""
                    for sub_type in subtypes:
                        emoji = sub_type["data"]["type_emoji"]
                        name = sub_type["data"]["type_name"]
                        sub_type_list += f"{emoji} " f"{name}\n"
                    embed.add_field(
                        name="Sub Types",
                        value=sub_type_list,
                        inline=False,
                    )
                elif type_parent:
                    emoji = type_parent["type_emoji"]
                    name = type_parent["type_name"]
                    embed.add_field(
                        name="Parent Type",
                        value=f"{emoji} {name}",
                        inline=False,
                    )

                if type_data["category_id"] == 0:
                    embed.add_field(
                        name="Redirect Text",
                        value=type_data["redirectText"],
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name="Category",
                        value=(
                            f"<#{type_data['category_id']}>"
                            if type_data["category_id"] != -1
                            else f"<#{type_data['sub_type']}>"
                        ),
                        inline=True,
                    )
                    embed.add_field(
                        name="NSFW Category",
                        value=(
                            f"<#{type_data['nsfw_category_id']}>"
                            if (
                                type_data["nsfw_category_id"]
                                and type_data["nsfw_category_id"] != -1
                            )
                            else "N/A"
                        ),
                        inline=True,
                    )
                    embed.add_field(
                        name="Ping Roles",
                        value=(
                            " ".join(
                                [
                                    f"<@&{role_id}>"
                                    for role_id in type_data["ping_roles"]
                                ]
                            )
                            if type_data["ping_roles"]
                            else "N/A"
                        ),
                        inline=True,
                    )
                await interaction.followup.send(embed=embed)

            else:
                pages = []
                for parent in sorted_types:
                    emoji = parent["data"]["type_emoji"]
                    name = parent["data"]["type_name"]
                    description = parent["data"]["type_descrip"]
                    embed = Embeds.success(
                        title=f"Main Type: {emoji} {name}",
                        description=f"{description}\n\n** **",
                    )

                    if parent["sub_types"]:
                        for sub_type in parent["sub_types"]:
                            emoji = sub_type["data"]["type_emoji"]
                            name = sub_type["data"]["type_name"]
                            description = sub_type["data"]["type_descrip"]
                            embed.add_field(
                                name=f"Sub Type: {emoji} {name}",
                                value=description,
                                inline=False,
                            )
                    pages.append(embed)

                pages = add_footers(pages)
                view = Paginator(pages)
                view.message = await interaction.followup.send(
                    embed=pages[0], view=view
                )

        except Exception as e:
            logger.exception(f"/type_view error: {e}")
            raise BotError(f"/type_view sent an error: {e}")

    @type_view.autocomplete("type")
    async def type_view_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        choices = await self._load_type_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    @type_group.command(name="add", description="Add a new ticket type")
    @checks.is_admin_app()
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
        ping_roles="SPACE SEPARATED list of role IDs",
    )
    async def type_add(
        self,
        interaction: discord.Interaction,
        name: Range[str, 1, 45],
        description: Range[str, 1, 100],
        emoji: str,
        category: discord.CategoryChannel = None,
        parent: str = None,
        nsfw: discord.CategoryChannel = None,
        redirect: str = None,
        ping_roles: str = None,
    ):
        try:
            await interaction.response.defer()
            guild = interaction.guild
            guild_id = guild.id
            channel = interaction.channel
            category_id = category.id if category else None
            parent_category_id = None

            emoji = self._check_emoji(emoji)
            if not emoji:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Invalid emoji. Please provide a valid Unicode emoji (Discord default emojis)."
                    )
                )
                return

            sorted_types = await self._list_format_types(guild_id)

            parent_id = None
            if parent:
                parent_name, parent_id, parent_category_id = parent.split(",")

            if category:
                for parent_type in sorted_types:
                    if parent_type["data"]["category_id"] == category.id:
                        if parent_id and parent_type["data"]["type_id"] == int(
                            parent_id
                        ):
                            continue
                        emoji = parent_type["data"]["type_emoji"]
                        name = parent_type["data"]["type_name"]
                        await interaction.followup.send(
                            embed=Embeds.error(
                                description=f"❌ This category is already assigned to the **{emoji} {name}** parent ticket type."
                            )
                        )
                        return

            if ping_roles:
                ping_roles, error = await self._fetch_ping_roles(guild, ping_roles)
                if error:
                    await interaction.followup.send(
                        embed=Embeds.error(description=error)
                    )
                    return
            else:
                ping_roles = []

            if redirect:
                category_id = 0
                nsfw = None
                ping_roles = []

                if redirect.isdigit():
                    message, response = await fetch_channel_message(channel, redirect)
                    if not message:
                        await interaction.followup.send(
                            embed=Embeds.error(description=response)
                        )
                        return
                    else:
                        redirect = message.content

                redirect, response = await verify_text(self.bot, guild, redirect, 4000)
                if not redirect:
                    await interaction.followup.send(
                        embed=Embeds.error(description=response)
                    )
                    return
            else:
                if not category_id:
                    if parent_category_id:
                        category_id = -1
                    else:
                        roles = []
                        permissions = (
                            await self.bot.data_manager.get_or_load_permissions(
                                guild_id
                            )
                        )
                        for role_id in permissions.keys():
                            role = guild.get_role(role_id)
                            roles.append(role)
                        overwrites = await get_overwrites(guild, roles)

                        config = await self.bot.data_manager.get_or_load_config(
                            guild_id
                        )
                        inbox_category = await self.bot.cache.get_channel(
                            config["inbox_id"]
                        )
                        if inbox_category:
                            try:
                                new_category = await guild.create_category(
                                    name=name,
                                    overwrites=overwrites,
                                    position=(inbox_category.position),
                                )
                                category_id = new_category.id
                            except Exception:
                                await interaction.followup.send(
                                    embed=Embeds.error(
                                        description="❌ Failed to create new ticket category."
                                    )
                                )
                                return
                        else:
                            await interaction.followup.send(
                                embed=Embeds.error(
                                    description="❌ Ticket inbox category not found. "
                                    "Please re-run the /setup command."
                                )
                            )
                            return

            order_id = None
            if parent:
                for parent_type in sorted_types:
                    if parent_type["data"]["type_id"] == int(parent_id):
                        order_id = len(parent_type["sub_types"])
                        break
            else:
                order_id = len(sorted_types)

            await self.bot.data_manager.add_type_to_db(
                guild_id,
                order_id,
                category_id,
                name,
                description,
                emoji,
                parent_category_id if parent_category_id else -1,
                redirect,
                nsfw.id if nsfw else -1,
                ping_roles,
            )
            await self.bot.data_manager.get_or_load_guild_types(guild.id, False)
            await interaction.followup.send(
                embed=Embeds.success(
                    description=f"✅ Added ticket type **{emoji} {name}**"
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
        choices = await self._load_parent_type_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    @type_group.command(
        name="remove",
        description="Remove a ticket type",
    )
    @checks.is_admin_app()
    @checks.is_guild_app()
    async def type_remove(self, interaction: discord.Interaction, type: str):
        try:
            await interaction.response.defer()
            guild_id = interaction.guild.id
            type_name, type_id, type_subtype_id = type.split(",")
            type_data = await self.bot.data_manager.get_ticket_type(guild_id, type_id)
            current_index = type_data["order_id"]

            is_parent = False
            sorted_types = await self._list_format_types(guild_id)
            for parent in sorted_types:
                if parent["data"]["type_id"] == int(type_id):
                    if parent["sub_types"]:
                        is_parent = True
                    break

            if is_parent:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Cannot remove a ticket type that has sub-types. "
                        "Please remove all sub-types first."
                    )
                )
                return

            await self.bot.data_manager.delete_type_from_db(type_id)
            await self._reorder_types(current_index, None, sorted_types, guild_id)
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
        ping_roles="SPACE SEPARATED list of role IDs",
    )
    async def type_edit(
        self,
        interaction: discord.Interaction,
        type: str,
        name: Range[str, 1, 45] = None,
        description: Range[str, 1, 100] = None,
        emoji: str = None,
        category: discord.CategoryChannel = None,
        parent: str = None,
        nsfw: discord.CategoryChannel = None,
        redirect: str = None,
        ping_roles: str = None,
    ):
        try:
            await interaction.response.defer()
            guild = interaction.guild
            guild_id = guild.id
            channel = interaction.channel
            type_name, type_id, type_subtype_id = type.split(",")
            type_data = await self.bot.data_manager.get_ticket_type(guild_id, type_id)
            type_category = await self._categorize_type(type_data, guild_id)
            type_emoji = type_data["type_emoji"]

            # Set variables to either new or existing values
            new_name = name if name else type_data["type_name"]
            new_description = description if description else type_data["type_descrip"]
            new_emoji = emoji if emoji else type_data["type_emoji"]
            if not self._check_emoji(new_emoji):
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Invalid emoji. Please provide a valid Unicode emoji (Discord default emojis)."
                    )
                )
                return
            new_category_id = category.id if category else type_data["category_id"]
            new_nsfw_id = nsfw.id if nsfw else type_data["nsfw_category_id"]
            new_redirect_text = redirect if redirect else type_data["redirectText"]

            # Set parent category ID
            new_parent_category_id = type_data["sub_type"]
            if parent:
                parent_name, parent_id, new_parent_category_id = parent.split(",")

            # Special handling for ping roles
            new_ping_roles = type_data["ping_roles"]
            if ping_roles:
                new_ping_roles, error = await self._fetch_ping_roles(guild, ping_roles)
                if error:
                    await interaction.followup.send(
                        embed=Embeds.error(description=error)
                    )
                    return

            # Handle category, redirect, and parent based on type category
            if type_category == "redirect":
                if category:
                    new_redirect_text = None

            elif type_category == "parent":
                if redirect:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ Cannot set redirect text for a parent ticket type."
                        )
                    )
                    return
                if parent:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ Cannot set a parent for a parent ticket type."
                        )
                    )
                    return
                if category:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ Cannot change the category for a parent ticket type. "
                            "Remove all sub-types first to change the category. "
                            "(This logic will be changed in the future.)"
                        )
                    )
                    return

            else:
                if redirect:
                    new_category_id = 0

            if new_redirect_text:
                if redirect and redirect.isdigit():
                    message, response = await fetch_channel_message(channel, redirect)
                    if not message:
                        await interaction.followup.send(
                            embed=Embeds.error(description=response)
                        )
                        return
                    else:
                        redirect = message.content

                new_redirect_text, response = await verify_text(
                    self.bot, guild, redirect, 4000
                )
                if not new_redirect_text:
                    await interaction.followup.send(
                        embed=Embeds.error(description=response)
                    )
                    return

            await self.bot.data_manager.update_type_in_db(
                type_id,
                new_category_id,
                new_name,
                new_description,
                new_emoji,
                new_parent_category_id,
                new_redirect_text,
                new_nsfw_id,
                new_ping_roles,
            )
            await self.bot.data_manager.get_or_load_guild_types(guild.id, False)
            await interaction.followup.send(
                embed=Embeds.success(
                    description=f"✅ Updated ticket type **{new_emoji} {new_name}**"
                )
            )

        except Exception as e:
            logger.exception(f"/type_edit error: {e}")
            raise BotError(f"/type_edit sent an error: {e}")

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
        choices = await self._load_parent_type_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    @type_group.command(name="order", description="Reorder ticket types")
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(type="Ticket type to reorder")
    async def type_order(self, interaction: discord.Interaction, type: str):
        try:
            guild_id = interaction.guild.id
            type_name, type_id, type_subtype_id = type.split(",")

            type_structure = await self._list_format_types(guild_id)
            neighbors = []
            if int(type_subtype_id) == -1:
                neighbors = type_structure
            else:
                for parent in type_structure:
                    if parent["data"]["category_id"] == int(type_subtype_id):
                        neighbors = parent["sub_types"]
                        break

            if len(neighbors) == 1:
                await interaction.response.send_message(
                    embed=Embeds.error(
                        description="❌ Cannot reorder this ticket type as it has no "
                        "neighboring types."
                    )
                )
                return

            embed = Embeds.success(
                title=f"**Reordering:** {type_name}",
                description="**Current Order:**",
            )
            count = 0
            for ticket_type in neighbors:
                emoji = ticket_type["data"]["type_emoji"]
                name = ticket_type["data"]["type_name"]
                count += 1
                embed.add_field(
                    name=f"**{count}.** {emoji} {name}",
                    value=" ",
                    inline=False,
                )

            await interaction.response.send_message(
                embed=embed, view=TypeOrderView(self.bot, guild_id, type_id, neighbors)
            )

        except Exception as e:
            logger.exception(f"/type_order error: {e}")
            raise BotError(f"/type_order sent an error: {e}")

    @type_order.autocomplete("type")
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
    @checks.is_admin_app()
    @checks.is_guild_app()
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
                await interaction.followup.send_message(
                    embed=Embeds.error(description=response)
                )
                return

            form_content, index, error = self._parse_form(message.content)
            if error:
                await interaction.followup.send(
                    embed=Embeds.error(description=f"{error} (line {index})")
                )
                return

            type_name, type_id, type_subtype_id = type.split(",")
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
    @checks.is_admin_app()
    @checks.is_guild_app()
    @app_commands.describe(type="Ticket type to view the form of")
    async def form_view(self, interaction: discord.Interaction, type: str):
        try:
            await interaction.response.defer(ephemeral=False)
            guild_id = interaction.guild.id
            type_name, type_id, type_subtype_id = type.split(",")
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
    @checks.is_admin_app()
    @checks.is_guild_app()
    @app_commands.describe(message_id="ID of the message containing the form template")
    async def form_preview(self, interaction: discord.Interaction, message_id: str):
        try:
            await interaction.response.defer(ephemeral=True)
            channel = interaction.channel
            message, response = await fetch_channel_message(channel, message_id)
            if response:
                await interaction.followup.send_message(
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
        name="template", description="View the text template for a pre-existing form"
    )
    @checks.is_admin_app()
    @checks.is_guild_app()
    @app_commands.describe(type="Ticket type to view the form template of")
    async def form_template(self, interaction: discord.Interaction, type: str):
        try:
            await interaction.response.defer(ephemeral=True)
            guild_id = interaction.guild.id
            type_name, type_id, type_subtype_id = type.split(",")
            form = None

            types = await self._key_format_types(guild_id)
            form = types[type_id]["form"]

            template_lines = [f"Title: {form['title']}"]
            for field in form["fields"]:
                template_lines.append(f"Question: {field['label']}")
                template_lines.append(f"Placeholder: {field.get('placeholder', '')}")
                template_lines.append(f"Style: {field['style']}")
                template_lines.append(f"Min: {field.get('min_length', '')}")
                template_lines.append(f"Max: {field.get('max_length', '')}")
                template_lines.append(
                    f"Required: {str(field.get('required', '')).lower()}"
                )
                template_lines.append("")

            template_text = "\n".join(template_lines).strip()
            template_embed = Embeds.info(
                title=f"Form Template for {type_name}",
                description=f"```{template_text}```",
            )
            await interaction.followup.send(embed=template_embed)

        except Exception as e:
            logger.exception(f"form view error: {e}")
            raise BotError(f"/form view sent an error: {e}")

    @form_group.command(
        name="example", description="Display an example template and form"
    )
    @checks.is_admin_app()
    @checks.is_guild_app()
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

    status_group = app_commands.Group(
        name="status", description="Manage ticket statuses"
    )

    # Manually update the status of a ticket channel
    @status_group.command(name="set", description="Change the emoji status of a ticket")
    @checks.is_ticket_app()
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(status="Select an emoji from the provided list")
    async def status_set(self, interaction, status: str):
        try:
            await interaction.response.defer(ephemeral=True)
            channel = interaction.channel
            status_emoji, status_name = status.split(";")

            new_status = status_name if (status_name in emoji_map) else status_emoji

            if self.bot.channel_status.get_timer(channel.id):
                errorEmbed = discord.Embed(
                    description="❌ Cannot change the status of an **inactive** ticket",
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=errorEmbed, ephemeral=True)
                return

            result = await self.bot.channel_status.set_emoji(channel, new_status, True)

            statusEmbed = Embeds.success(
                description=f"✅ Channel status set to **{status_emoji} {status_name}**"
                "\n(*Please wait up to 5 minutes for edits to appear*)",
            )
            if not result:
                statusEmbed.description = (
                    f"❌ Failed to set channel status to **{status_emoji} {status_name}**, "
                    "current or pending status is already set as this"
                )
                statusEmbed.color = discord.Color.red()
            await interaction.followup.send(embed=statusEmbed, ephemeral=True)
            return

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/status set sent an error: {e}")

    @status_set.autocomplete("status")
    async def status_remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        guild_statuses = await self.bot.data_manager.get_statuses(guild.id)
        statuses = default_statuses + guild_statuses

        choices = [
            app_commands.Choice(
                name=f"{status['emoji']} {status['name']}",
                value=f"{status['emoji']};{status['name']}",
            )
            for status in statuses
        ]

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    @status_group.command(name="add", description="Add a new ticket status")
    @checks.is_admin_app()
    @checks.is_guild_app()
    @app_commands.describe(
        emoji="Emoji to show for this status",
        name="Status name",
    )
    async def status_add(
        self, interaction: discord.Interaction, emoji: str, name: Range[str, 1, 45]
    ):
        try:
            await interaction.response.defer()
            guild = interaction.guild
            guild_id = guild.id

            statuses = await self.bot.data_manager.get_statuses(guild_id)
            if len(statuses) >= 20:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Maximum of 20 ticket statuses allowed."
                    )
                )
                return

            emoji = self._check_emoji(emoji)
            if not emoji:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Invalid emoji. Please provide a valid Unicode emoji (Discord default emojis)."
                    )
                )
                return

            if ";" in name:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Status names cannot contain semicolons."
                    )
                )
                return

            await self.bot.data_manager.add_status(guild_id, emoji, name)
            await interaction.followup.send(
                embed=Embeds.success(
                    description=f"✅ Added ticket status **{emoji} {name}**"
                )
            )

        except Exception as e:
            logger.exception(f"status_add error: {e}")
            raise BotError(f"/status_add sent an error: {e}")

    @status_group.command(name="remove", description="Remove a ticket status")
    @checks.is_admin_app()
    @checks.is_guild_app()
    @app_commands.describe(status="Status to remove")
    async def status_remove(self, interaction: discord.Interaction, status: str):
        try:
            await interaction.response.defer()
            status_emoji, status_name, status_id = status.split(";")

            await self.bot.data_manager.delete_status(status_id)

            await interaction.followup.send(
                embed=Embeds.success(
                    description=f"✅ Removed ticket status **{status_emoji} {status_name}**"
                )
            )

        except Exception as e:
            logger.exception(f"/status_remove error: {e}")
            raise BotError(f"/status_remove sent an error: {e}")

    @status_remove.autocomplete("status")
    async def status_remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        statuses = await self.bot.data_manager.get_statuses(guild.id)

        choices = [
            app_commands.Choice(
                name=f"{status['emoji']} {status['name']}",
                value=f"{status['emoji']};{status['name']};{status['status_id']}",
            )
            for status in statuses
        ]

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    @status_group.command(name="view", description="View all ticket statuses")
    @checks.is_admin_app()
    @checks.is_guild_app()
    async def status_view(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            guild_id = interaction.guild.id

            statuses = await self.bot.data_manager.get_statuses(guild_id)

            if not statuses:
                await interaction.followup.send(
                    embed=Embeds.success(description="No ticket statuses set.")
                )
                return

            embed = Embeds.success(title="Ticket Statuses")
            for status in statuses:
                emoji = status["emoji"]
                name = status["name"]
                embed.add_field(
                    name=f"{emoji} {name}",
                    value=" ",
                    inline=False,
                )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"/status_view error: {e}")
            raise BotError(f"/status_view sent an error: {e}")

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
            aps = config["aps"]
            # logging = config["logging"]
            # analytics = config["analytics"]

            def convert_state(state):
                if state and state.casefold() == "true":
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
                f"Anonymous profiles: **{convert_state(aps)}**\n",
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
                success_embed.description = "✅ Moderator anonyminity setting changed to: **Default non-anonymous**"
                await self.bot.data_manager.set_anon_status(guild.id, "false")
                await ctx.send(embed=success_embed)
            else:
                success_embed.description = (
                    "✅ Moderator anonyminity setting changed to: **Default anonymous**"
                )
                await self.bot.data_manager.set_anon_status(guild.id, "true")
                await ctx.send(embed=success_embed)

            await self.bot.data_manager.get_or_load_config(guild.id, False)

        except Exception as e:
            logger.exception(f"/anon error: {e}")
            raise BotError(f"/anon sent an error: {e}")

    @commands.command(name="aps")
    @checks.is_admin()
    @checks.is_guild()
    async def aps(self, ctx):
        try:
            guild = ctx.guild
            config = await self.bot.data_manager.get_or_load_config(guild.id)
            success_embed = discord.Embed(description="", color=discord.Color.green())
            if config["aps"] == "true":
                success_embed.description = (
                    f"✅ Anonymous profiles setting changed to: **Disabled**"
                )
                await self.bot.data_manager.set_aps(guild.id, "false")
                await ctx.send(embed=success_embed)
            else:
                success_embed.description = (
                    f"✅ Anonymous profiles setting changed to: **Enabled**"
                )
                await self.bot.data_manager.set_aps(guild.id, "true")
                await ctx.send(embed=success_embed)

            await self.bot.data_manager.get_or_load_config(guild.id, False)

        except Exception as e:
            logger.exception(f"/aps error: {e}")
            raise BotError(f"/aps sent an error: {e}")

    # change pingrole to be a slash command with ticket type selection
    @commands.command(name="pingrole")
    @checks.is_admin()
    @checks.is_guild()
    async def pingrole(self, ctx, *, role_ids=None):
        try:
            guild = ctx.guild
            if role_ids is None:
                await self.bot.data_manager.set_all_ping_roles(guild.id, [])
                await ctx.send(
                    embed=discord.Embed(
                        description="✅ Cleared ping roles", color=discord.Color.green()
                    )
                )
                return

            valid_role_ids, error = await self._fetch_ping_roles(guild, role_ids)
            if error:
                await ctx.send(embed=Embeds.error(description=error))
                return

            await self.bot.data_manager.set_all_ping_roles(guild.id, valid_role_ids)
            await ctx.send(
                embed=discord.Embed(
                    description=f"✅ Set ping role(s) to: {' '.join(f'<@&{id}>' for id in valid_role_ids)}",
                    color=discord.Color.green(),
                )
            )

        except Exception as e:
            logger.exception(f"/pingrole error: {e}")
            raise BotError(f"/pingrole sent an error: {e}")

    ai_group = app_commands.Group(name="ai", description="Manage ai context")

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

    # Rewrite the role permission commands to be application commands + more modern
    perms_group = app_commands.Group(
        name="permissions", description="Manage role permissions"
    )

    @perms_group.command(name="view", description="View this server's role permissions")
    @checks.is_admin_app()
    @checks.is_guild_app()
    async def view_permissions(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            guild_id = interaction.guild.id

            perms = await self.bot.data_manager.get_or_load_permissions(guild_id)

            embed = Embeds.success(title=f"Server Role Permissions")
            if not perms:
                embed.color = discord.Color.red()
                embed.add_field(
                    name="",
                    value="No permissions set, run **/permissions add** to add one",
                    inline=False,
                )
            else:
                for key, value in perms.items():
                    embed.add_field(
                        name="",
                        value=f"<@&{key}> - **{value}**",
                        inline=False,
                    )
            await interaction.followup.send(embed=embed)

        except Exception as e:
            raise BotError(f"/permissions view sent an error: {e}")

    @perms_group.command(name="add", description="Add permissions to a role")
    @checks.is_admin_app()
    @checks.is_guild_app()
    @app_commands.describe(role="Selected role")
    @app_commands.describe(
        level="Permission level. Users can only use moderation-specific commands"
    )
    @app_commands.choices(
        level=[
            app_commands.Choice(name="User", value="Bot User"),
            app_commands.Choice(name="Admin", value="Bot Admin"),
        ]
    )
    async def add_permissions(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        level: discord.app_commands.Choice[str],
    ):
        try:
            await interaction.response.defer()
            guild_id = interaction.guild.id
            role_id = role.id
            new_level_name = level.name
            new_level_value = level.value

            perms = await self.bot.data_manager.get_or_load_permissions(guild_id)

            if perms.get(role_id, None):
                curr_perm_level = perms[role_id]
                if curr_perm_level == new_level_value:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description=f"Unable to add permissions, <@&{role_id}> already has **{new_level_name}** permissions."
                        )
                    )
                else:
                    await self.bot.data_manager.update_permission_in_db(
                        guild_id, role_id, new_level_value
                    )
                    await interaction.followup.send(
                        embed=Embeds.success(
                            description=f"Updated <@&{role_id}>'s permissions to **{new_level_name}**."
                        )
                    )

            else:
                await self.bot.data_manager.add_permission_to_db(
                    guild_id, role_id, new_level_value
                )
                await interaction.followup.send(
                    embed=Embeds.success(
                        description=f"Added **{new_level_name}** permissions to <@&{role_id}>."
                    )
                )

        except Exception as e:
            raise BotError(f"/permissions add sent an error: {e}")

    @perms_group.command(name="remove", description="Remove permissions from a role")
    @checks.is_admin_app()
    @checks.is_guild_app()
    @app_commands.describe(role="Selected role")
    async def remove_permissions(
        self, interaction: discord.Interaction, role: discord.Role
    ):
        try:
            await interaction.response.defer()
            guild_id = interaction.guild.id
            role_id = role.id

            perms = await self.bot.data_manager.get_or_load_permissions(guild_id)
            curr_perm_level = perms.get(role_id, None)

            if not curr_perm_level:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description=f"Unable to remove permissions, <@&{role_id}> does not have any permissions set."
                    )
                )

            else:
                await self.bot.data_manager.delete_permission_from_db(guild_id, role_id)
                await interaction.followup.send(
                    embed=Embeds.success(
                        description=f"Removed <@&{role_id}>'s permissions."
                    )
                )

        except Exception as e:
            raise BotError(f"/permissions add sent an error: {e}")


async def setup(bot):
    await bot.add_cog(Config(bot))
