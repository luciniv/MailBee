import asyncio
import time
from datetime import datetime, timezone

import discord
from discord import SelectOption
from discord.ext import commands
from discord.ui import Button, View

from classes.ticket_opener import TicketOpener
from utils.helpers import *
from roblox_data.roblox import *
from classes.embeds import Embeds


async def processing_embed():
    process_time = int(time.time()) + 31
    return Embeds.info(
        title="Processing your ticket...",
        description=(
            "This may take a moment! Please wait up to `30 seconds` "
            f"for your ticket to be processed: <t:{process_time}:R>"
        ),
    )


async def roblox_data_fetch(ticket, guild_id, user_id):
    game_type = SERVER_TO_GAME.get(guild_id, None)
    roblox_data = None
    if game_type:
        roblox_data = await get_roblox_data(game_type, guild_id, user_id)
        if roblox_data:
            ticket.roblox_username = roblox_data[0]
            ticket.roblox_id = roblox_data[1]
            ticket.robux_spent = roblox_data[2]
            ticket.hours_played = roblox_data[3]

    return None


class TimeoutSafeView(discord.ui.View):
    def __init__(self, timeout=500):
        super().__init__(timeout=timeout)
        self.message = None

    async def on_timeout(self):
        try:
            if self.message:
                for item in self.children:
                    item.disabled = True
                try:
                    await self.message.edit(view=self)
                except discord.HTTPException:
                    pass

                try:
                    timeout_embed = Embeds.error(
                        description="Embed has timed out. Repeat your prior command or action if you need more time.",
                    )
                    await self.message.edit(embed=timeout_embed)
                except discord.Forbidden:
                    pass
        except Exception:
            pass


class TicketSelect(discord.ui.Select):
    def __init__(self, bot, tickets: list[dict], message):
        self.bot = bot
        self.selected_ticket = None
        self.message = message

        options = []

        for ticket in tickets:
            guild = self.bot.get_guild(ticket["guild_id"])

            if guild:
                options.append(
                    SelectOption(
                        label=f"{guild.name}",
                        value=f"{ticket['guild_id']} {ticket['channel_id']}",
                    )
                )

        super().__init__(
            placeholder="Select a destination server",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.selected_ticket = self.values[0]
        guild_id = (self.selected_ticket.split())[0]
        channel_id = (self.selected_ticket.split())[1]
        analytics = self.bot.get_cog("Analytics")
        if analytics is not None:
            await analytics.route_to_server(
                self.message, int(guild_id), int(channel_id)
            )
        else:
            error_embed = Embeds.error(
                description="❌ Internal error, please try sending your message again.",
            )
            await interaction.channel.send(embed=error_embed)
        self.view.stop()
        await self.view.message.delete()


class TicketSelectView(TimeoutSafeView):
    def __init__(self, bot, tickets: list[dict], message):
        super().__init__()
        self.bot = bot
        self.selected_ticket = None
        self.add_item(TicketSelect(bot, tickets, message))


class ServerSelect(discord.ui.Select):
    def __init__(self, bot, shared_guilds, dm_channel_id):
        # List of guild names
        options = [
            SelectOption(label=guild.name, value=str(guild.id))
            for guild in shared_guilds
        ]

        super().__init__(
            placeholder="Choose a server...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.bot = bot
        self.dm_channel_id = dm_channel_id

    async def error_out(
        self, interaction: discord.Interaction, title: str, description: str
    ):
        error_embed = Embeds.error(title=title, description=description)
        await interaction.channel.send(embed=error_embed)

        try:
            await interaction.message.delete()
        except discord.errors.HTTPException:
            pass

        if self.view:
            self.view.stop()

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild_id = int(self.values[0])
        guild = self.bot.get_guild(guild_id)
        dm_channel_id = self.dm_channel_id
        user = interaction.user

        blacklisted = await self.bot.data_manager.get_blacklist_entry(guild.id, user.id)
        if blacklisted:
            await self.error_out(
                interaction,
                "",
                "❌ You are blacklisted from opening tickets with this server.",
            )
            return

        # Check if user is in this guild
        member = guild.get_member(interaction.user.id)
        if member is None:
            try:
                member = await asyncio.wait_for(
                    guild.fetch_member(interaction.user.id), timeout=1
                )

            except discord.errors.NotFound:
                await self.error_out(
                    interaction,
                    "",
                    "❌ You are not in that server. If you would like to open a "
                    "ticket there, please join that server first.",
                )
                return

            except Exception:
                await self.error_out(
                    interaction,
                    "",
                    "❌ An error occurred while verifying your membership in "
                    "that server. Please try again.",
                )
                return

        await self.bot.cache.store_guild_member(guild_id, member)

        # Check if user has an open or pending ticket already
        pending_ticket = await self.bot.ticket_queue.has_pending_ticket(
            guild_id, member.id
        )
        current_ticket = await self.bot.data_manager.has_current_ticket(
            guild_id, member.id
        )
        if pending_ticket or current_ticket:
            await self.error_out(
                interaction,
                "",
                "❌ You already have a ticket pending or open with this server.\n\n"
                "Send a message in that ticket to reply to it instead.",
            )
            return

        # Check if guild is set up / accepting tickets
        config = await self.bot.data_manager.get_or_load_config(guild_id)
        if not config:
            await self.error_out(
                interaction,
                "Ticket Creation is Disabled",
                ("This server has not set up ticket creation yet."),
            )
            return
        else:
            accepting = config["accepting"]
            if accepting != "true":
                await interaction.followup.send(
                    embed=Embeds.error(
                        title="Ticket Creation is Disabled",
                        description=accepting,
                    ),
                    ephemeral=True,
                )
                return

        # Load available ticket types
        types = await self.bot.data_manager.get_or_load_guild_types(guild_id)
        if not types:
            await self.error_out(
                interaction,
                "",
                "❌ This server has not set up any ticket types yet.\n\n"
                "Please contact a server admin if you believe this is a mistake.",
            )
            return

        loading_embed = Embeds.info(description="Loading ticket types...")
        await interaction.message.edit(embed=loading_embed)

        # Build the category select embed
        category_embed = Embeds.info(
            title="Select a Ticket Type",
            description="Please select a type for your ticket with the drop-down menu below.\n\n"
            "Your ticket will not be created until you select a type and complete the resulting "
            "form, so explore the available types as needed!",
        )
        if guild.icon:
            category_embed.set_author(name=guild.name, icon_url=guild.icon.url)
            category_embed.set_thumbnail(url=guild.icon.url)
        else:
            category_embed.set_author(name=guild.name)

        # Build and send the category select view
        view = CategorySelectView(self.bot, guild.id, dm_channel_id, types)
        await view.setup()

        try:
            message = await interaction.message.edit(embed=category_embed, view=view)
            view.message = message
        except discord.HTTPException:
            message = await interaction.channel.send(embed=category_embed, view=view)
            view.message = message


class ServerSelectView(TimeoutSafeView):
    def __init__(self, bot, shared_guilds, dm_channel_id):
        super().__init__()
        self.bot = bot
        self.add_item(ServerSelect(bot, shared_guilds, dm_channel_id))


class DMCategoryButtonView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Open a Ticket",
        style=discord.ButtonStyle.blurple,
        custom_id="persistent_dm_button",
        emoji="✉️",
    )
    async def send_dm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            await interaction.response.defer(ephemeral=True)

            user = interaction.user
            guild = interaction.guild
            limited, retry_after, was_notified = (
                self.bot.queue.check_user_action_cooldown("open_ticket_button", user.id)
            )

            if limited:
                if not was_notified:
                    self.bot.queue.user_action_cooldowns["open_ticket_button"][
                        "notified"
                    ][user.id] = True
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ You're clicking a bit too quickly — "
                            f"please wait `{retry_after:.1f}` seconds."
                        ),
                        ephemeral=True,
                    )
                return

            if not guild:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ This button must be used in a server."
                    ),
                    ephemeral=True,
                )
                return

            guild_id = guild.id

            blacklisted = await self.bot.data_manager.get_blacklist_entry(
                guild_id, user.id
            )

            if blacklisted:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ You are blacklisted from opening tickets "
                        "with this server."
                    ),
                    ephemeral=True,
                )
                return

            pending_ticket = await self.bot.ticket_queue.has_pending_ticket(
                guild_id, user.id
            )
            current_ticket = await self.bot.data_manager.has_current_ticket(
                guild_id, user.id
            )
            if pending_ticket or current_ticket:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ You already have a ticket open with this "
                        "server. Direct message me to reply to that ticket instead."
                    ),
                    ephemeral=True,
                )
                return

            config = await self.bot.data_manager.get_or_load_config(guild_id)
            accepting = config["accepting"]
            if accepting != "true":
                await interaction.followup.send(
                    embed=Embeds.error(
                        title="Ticket Creation is Disabled",
                        description=accepting,
                    ),
                    ephemeral=True,
                )
                return

            try:
                dm_channel = user.dm_channel or await user.create_dm()

                types = await self.bot.data_manager.get_or_load_guild_types(guild_id)
                if not types:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ This server has not set up any ticket "
                            "types yet.\n\nPlease contact a server admin if you believe "
                            "this is a mistake.",
                        ),
                        ephemeral=True,
                    )
                    return

                embed = Embeds.info(
                    title="Select Ticket Type",
                    description="Please select a type for your ticket with the "
                    "drop-down menu below.",
                )
                if guild.icon:
                    embed.set_author(name=guild.name, icon_url=guild.icon.url)
                    embed.set_thumbnail(url=guild.icon.url)
                else:
                    embed.set_author(name=guild.name)

                view = CategorySelectView(self.bot, guild.id, dm_channel.id, types)
                await view.setup()
                sent_msg = await dm_channel.send(embed=embed, view=view)

                if sent_msg is None:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ I couldn’t message you! Please enable "
                            "direct messages and try again."
                        ),
                        ephemeral=True,
                    )
                    return

                view.message = sent_msg

                start_view = View()
                start_view.add_item(
                    Button(
                        label="Jump to ticket",
                        url=f"https://discord.com/channels/@me/{dm_channel.id}/{sent_msg.id}",
                    )
                )

                start_embed = Embeds.success(
                    title="Ticket Started",
                    description="A ticket has been started in your direct messages!",
                )

                await interaction.followup.send(
                    embed=start_embed, view=start_view, ephemeral=True
                )

            except discord.Forbidden:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ I couldn’t message you! Please enable "
                        "direct messages and try again."
                    ),
                    ephemeral=True,
                )

        except Exception as e:
            logger.exception(e)
            await interaction.followup.send(
                embed=Embeds.error(
                    description="❌ An error occurred. Please wait a bit and try again."
                ),
                ephemeral=True,
            )


class CategorySelect(discord.ui.Select):
    def __init__(
        self, bot, guild_id, dm_channel_id, types, options, parent_category_id=None
    ):
        self.bot = bot
        self.guild_id = guild_id
        self.dm_channel_id = dm_channel_id
        self.types = types
        self.parent_category_id = parent_category_id  # If selecting a subtype
        super().__init__(
            placeholder=(
                "Choose a ticket type..."
                if parent_category_id is None
                else "Choose a sub-type..."
            ),
            options=options,
        )

    async def message_out(self, interaction: discord.Interaction, embed: discord.Embed):
        await interaction.channel.send(embed=embed)

        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass

        if self.view:
            self.view.stop()

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0].split()
        selected_type_id = int(value[0])
        selected_category_id = int(value[1])
        selected_nsfw_id = int(value[2])
        dm_channel_id = self.dm_channel_id
        guild_id = self.guild_id
        guild = self.bot.get_guild(guild_id)

        type = next(
            (entry for entry in self.types if entry["type_id"] == selected_type_id),
            None,
        )
        if not type:
            print("type_id wasnt an int for some reason")
            return
        name = type["type_name"]
        emoji = type["type_emoji"]

        # FIXME rework this system based on database updates to ticket types
        # Check if the subtype embed needs sent
        if self.parent_category_id is None:
            for entry in self.types:
                if entry["sub_type"] == selected_category_id:
                    await interaction.response.defer(thinking=False)
                    subtype_embed = Embeds.success(
                        title="Select a Ticket Sub-Type",
                        description=f"You selected ticket type **{emoji} {name}**.\n\nPlease choose "
                        "the ticket sub-type that best fits your situation below.",
                    )
                    if guild.icon:
                        subtype_embed.set_author(
                            name=guild.name, icon_url=guild.icon.url
                        )
                        subtype_embed.set_thumbnail(url=guild.icon.url)
                    else:
                        subtype_embed.set_author(name=guild.name)

                    # Show subtypes select
                    newView = CategorySelectView(
                        self.bot,
                        self.guild_id,
                        self.dm_channel_id,
                        self.types,
                        parent_category_id=selected_category_id,
                    )
                    await newView.setup()
                    await interaction.edit_original_response(
                        embed=subtype_embed, view=newView
                    )
                    newView.message = await interaction.original_response()
                    return
        else:
            selected_category_id = (
                type["category_id"]
                if type["category_id"] != -1
                else self.parent_category_id
            )

        # Now handle ticket responses (redirect, form)
        # Handle redirect type
        if selected_category_id == 0:
            redirect_embed = Embeds.info(
                title="Auto-Response [Ticket NOT Created]",
                description=type["redirectText"],
            )
            redirect_embed.timestamp = datetime.now(timezone.utc)
            if guild.icon:
                redirect_embed.set_footer(text=guild.name, icon_url=guild.icon.url)
            else:
                redirect_embed.set_footer(text=guild.name)

            await self.message_out(interaction, redirect_embed)
            return

        # Get the category
        category = await self.bot.cache.get_channel(selected_category_id, timeout=2)
        if not category:
            error_embed = Embeds.error(
                description="❌ Couldn't find ticket category in the destination "
                "server. Please contact a server admin if this error persists.",
            )
            await self.message_out(interaction, error_embed)
            return

        # Handle max channels in the category
        if len(category.channels) >= 50:
            # TODO check if queue is enabled --> queue here
            error_embed = Embeds.error(
                description="Thank you for reaching out to the moderation team!\n\n"
                f"Unfortunately, tickets of type **{emoji} {name}** have "
                "reached maximum capacity. Please try again later for an "
                "opening, we thank you in advance for your patience."
            )
            await self.message_out(interaction, error_embed)
            return

        source_view = self.view
        modal_template = type["form"]
        ping_roles = type["ping_roles"]
        if (not ping_roles) and (self.parent_category_id is not None):
            ping_roles = next(
                (
                    entry["ping_roles"]
                    for entry in self.types
                    if entry["category_id"] == self.parent_category_id
                ),
                None,
            )

        await send_dynamic_modal(
            self.bot,
            interaction,
            self.guild_id,
            category,
            selected_type_id,
            selected_nsfw_id,
            dm_channel_id,
            ping_roles,
            modal_template,
            source_view,
        )

    @classmethod
    async def create(cls, bot, guild_id, dm_channel_id, types, parent_category_id=None):
        try:
            if parent_category_id is None:
                filtered_types = [
                    entry for entry in types if int(entry.get("sub_type")) == -1
                ]
            else:
                filtered_types = [
                    entry
                    for entry in types
                    if int(entry.get("sub_type")) == parent_category_id
                ]

            options = [
                SelectOption(
                    label=str(entry["type_name"]),
                    value=f"{entry['type_id']} {entry['category_id']} {entry['nsfw_category_id']}",
                    emoji=str(entry.get("type_emoji")),
                    description=str(entry["type_descrip"]),
                )
                for entry in filtered_types
            ]

            return cls(bot, guild_id, dm_channel_id, types, options, parent_category_id)
        except Exception as e:
            logger.exception(e)


class CategorySelectView(TimeoutSafeView):
    def __init__(self, bot, guild_id, dm_channel_id, types, parent_category_id=None):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.dm_channel_id = dm_channel_id
        self.types = types
        self.parent_category_id = parent_category_id

    async def setup(self):
        select = await CategorySelect.create(
            self.bot,
            self.guild_id,
            self.dm_channel_id,
            self.types,
            self.parent_category_id,
        )
        self.add_item(select)

        # Only add back button if viewing subtypes
        if self.parent_category_id is not None:
            self.add_item(
                BackButton(self.bot, self.guild_id, self.dm_channel_id, self.types)
            )


class BackButton(discord.ui.Button):
    def __init__(self, bot, guild_id, dm_channel_id, types):
        super().__init__(style=discord.ButtonStyle.success, label="⬅ Go Back")
        self.bot = bot
        self.guild_id = guild_id
        self.dm_channel_id = dm_channel_id
        self.types = types

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=False)
        guild = self.bot.get_guild(self.guild_id)
        category_embed = Embeds.info(
            title="Select a Ticket Type",
            description="Please select a type for your ticket with the drop-down menu below.\n\n"
            "Your ticket will not be created until you select a type and complete the resulting "
            "form, so explore the available types as needed!",
        )
        if guild.icon:
            category_embed.set_author(name=guild.name, icon_url=guild.icon.url)
            category_embed.set_thumbnail(url=guild.icon.url)
        else:
            category_embed.set_author(name=guild.name)

        view = CategorySelectView(
            self.bot, self.guild_id, self.dm_channel_id, self.types
        )
        await view.setup()

        try:
            message = await interaction.message.edit(embed=category_embed, view=view)
            view.message = message
        except discord.HTTPException:
            message = await interaction.channel.send(embed=category_embed, view=view)
            view.message = message


async def send_dynamic_modal(
    bot,
    interaction,
    guild_id,
    category,
    type_id,
    nsfw_id,
    dm_channel_id,
    ping_roles,
    modal_template,
    source_view,
):
    if not category:
        error_embed = Embeds.error(
            description="❌ Couldn't find ticket category in the destination server. Please contact a server admin.",
        )
        await interaction.channel.send(embed=error_embed)
        return

    title = modal_template.get("title", "Form")
    fields = modal_template.get("fields", [])
    start_time = int(time.time())

    # Modal submission handler
    async def handle_submit(interaction: discord.Interaction, values: dict):
        try:
            await interaction.response.defer()

            user = interaction.user
            time_taken = int(time.time()) - start_time

            ticket = Ticket(
                user_id=user.id,
                guild_id=guild_id,
                category_id=category.id,
                type_id=type_id,
                type_name=title,
                data=values,
                time_taken=time_taken,
                ping_roles=ping_roles,
            )

            if nsfw_id != -1:
                nsfw_embed = Embeds.error(
                    title="Does Your Report Contain NSFW?",
                    description="Use the buttons below to select whether your ticket "
                    "contains **content that is considered Not Safe For Work (NSFW)**, "
                    "such as:\n"
                    "> - Gore or extreme violence\n"
                    "> - Suggestive, explicit, or sexual content\n"
                    "> - Anything violating **Rule 1.** of our server's rules list\n"
                    "We ask this to ensure your report is handed to the appropriate staff "
                    "members, thank you!",
                )

                # Build and send the NSFW button view
                view = NSFWButtonView(bot, nsfw_id, ticket)

                try:
                    message = await interaction.message.edit(
                        embed=nsfw_embed, view=view
                    )
                    view.message = message
                except discord.HTTPException:
                    message = await interaction.channel.send(
                        embed=nsfw_embed, view=view
                    )
                    view.message = message
            else:
                try:
                    # Delete the original DM message with the view
                    await source_view.message.delete()
                except Exception as e:
                    print(f"Failed to delete old message: {e}")
                info_message = await interaction.channel.send(
                    embed=await processing_embed()
                )
                await bot.cache.store_message(info_message)
                await roblox_data_fetch(ticket, guild_id, user.id)
                await bot.ticket_queue._add_ticket(ticket, info_message)

        except Exception as e:
            print(e)

    # Send the modal
    await interaction.response.send_modal(
        DynamicFormModal(title, fields, handle_submit, source_view)
    )


class DynamicFormModal(discord.ui.Modal):
    def __init__(self, title, fields, on_submit_callback, view):
        super().__init__(title=title)
        self.on_submit_callback = on_submit_callback
        self.values = {}
        self.source_view = view

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
                max_length=field.get("max_length", 100),
                required=field.get("required", True),
            )
            self.add_item(input)

    async def on_submit(self, interaction: discord.Interaction):
        for child in self.children:
            self.values[child.label] = child.value

        await self.on_submit_callback(interaction, self.values)
        message = None


class NSFWButtonView(TimeoutSafeView):
    def __init__(self, bot, nsfw_id, ticket):
        super().__init__(timeout=None)
        self.bot = bot
        self.nsfw_id = nsfw_id
        self.ticket = ticket
        self.message = None

    @discord.ui.button(
        label="Yes, it contains NSFW", style=discord.ButtonStyle.success, row=0
    )
    async def nsfw_yes_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        ticket = self.ticket

        try:
            # Delete the original DM message with the view
            await self.message.delete()
        except Exception as e:
            print(f"Failed to delete old message: {e}")

        category = await self.bot.cache.get_channel(self.nsfw_id)
        if not category:
            error_embed = Embeds.error(
                description="❌ Couldn't find NSFW ticket category in the destination server. "
                "Please contact a server admin.",
            )
            await interaction.channel.send(embed=error_embed)
            return

        ticket.category_id = category.id
        ticket.nsfw = True
        info_message = await interaction.channel.send(embed=await processing_embed())
        await self.bot.cache.store_message(info_message)
        await roblox_data_fetch(ticket, ticket.guild_id, ticket.user_id)
        await self.bot.ticket_queue._add_ticket(self.ticket, info_message)

    @discord.ui.button(label="No, it does not", style=discord.ButtonStyle.danger, row=0)
    async def nsfw_no_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        ticket = self.ticket

        try:
            # Delete the original DM message with the view
            await self.message.delete()
        except Exception as e:
            print(f"Failed to delete old message: {e}")

        info_message = await interaction.channel.send(embed=await processing_embed())
        await self.bot.cache.store_message(info_message)
        await roblox_data_fetch(ticket, ticket.guild_id, ticket.user_id)
        await self.bot.ticket_queue._add_ticket(ticket, info_message)


class TicketRatingView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.rating_given = False
        self.feedback_sent = False
        self.report_sent = False
        self.message = None

    def disable_rating_buttons(self):
        for child in self.children:
            if child.custom_id in ("resolved", "not_resolved"):
                child.disabled = True

    def disable_feedback_button(self):
        for child in self.children:
            if child.custom_id == "feedback":
                child.disabled = True

    def disable_report_button(self):
        for child in self.children:
            if child.custom_id == "report":
                child.disabled = True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

    @discord.ui.button(
        label="Satisfied",
        style=discord.ButtonStyle.success,
        row=0,
        emoji="👍",
        custom_id="resolved",
    )
    async def resolved_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        if not self.rating_given:
            self.rating_given = True
            self.disable_rating_buttons()
            response_embed = Embeds.success(
                description="We're glad to hear you're satisfied with your ticket! "
                "You can leave feedback or report an issue using the buttons "
                "provided above.",
            )
            await interaction.followup.send(embed=response_embed, ephemeral=True)
            await interaction.message.edit(view=self)

            message = interaction.message
            embed = message.embeds[1]
            footer = (embed.footer.text).split()
            channel_id = footer[-1]

            await self.bot.data_manager.update_rating(channel_id, "Satisfied")

    @discord.ui.button(
        label="Dissatisfied",
        style=discord.ButtonStyle.danger,
        row=0,
        emoji="👎",
        custom_id="not_resolved",
    )
    async def not_resolved_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        if not self.rating_given:
            self.rating_given = True
            self.disable_rating_buttons()
            response_embed = Embeds.success(
                description="We're sorry to hear you're dissatisfied with your ticket. "
                "You can leave feedback or report an issue using the buttons "
                "provided above.",
            )
            await interaction.followup.send(embed=response_embed, ephemeral=True)
            await interaction.message.edit(view=self)

            message = interaction.message
            embed = message.embeds[1]
            footer = (embed.footer.text).split()
            channel_id = footer[-1]

            await self.bot.data_manager.update_rating(channel_id, "Dissatisfied")

    @discord.ui.button(
        label="📝 Leave Feedback",
        style=discord.ButtonStyle.secondary,
        row=1,
        custom_id="feedback",
    )
    async def feedback_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not self.feedback_sent:
            await interaction.response.send_modal(FeedbackModal(view=self))

    @discord.ui.button(
        label="🚩 Report Issue",
        style=discord.ButtonStyle.secondary,
        row=1,
        custom_id="report",
    )
    async def report_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not self.report_sent:
            await interaction.response.send_modal(ReportModal(view=self))


class FeedbackModal(discord.ui.Modal, title="Feedback Form"):
    def __init__(self, view: TicketRatingView):
        super().__init__()
        self.view = view
        self.bot = view.bot
        self.feedback = discord.ui.TextInput(
            label="Leave your feedback",
            style=discord.TextStyle.paragraph,
            required=True,
        )
        self.add_item(self.feedback)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        message = interaction.message
        user = interaction.user
        embed = message.embeds[1]
        footer = (embed.footer.text).split()
        channel_id = footer[-1]
        guild_id = None
        thread_id = None

        data = await self.bot.data_manager.get_guild_and_log(channel_id)
        if len(data) != 0:
            guild_id = data[0][0]
            thread_id = data[0][1]

        config = await self.bot.data_manager.get_or_load_config(guild_id)
        if config is not None:
            feedback_id = config["feedback_id"]

        feedback_channel = await self.bot.cache.get_channel(feedback_id)
        if feedback_channel:
            embed = Embeds.info(
                title="New Feedback Submitted",
                description=self.feedback.value,
            )
            embed.set_author(
                name=f"{user.name} | {user.id}",
                icon_url=(user.avatar and user.avatar.url) or user.display_avatar.url,
            )
            embed.add_field(name="Ticket Log", value=f"<#{thread_id}>")
            await feedback_channel.send(embed=embed)
        feedback_embed = Embeds.success(
            description="Your feedback has been recorded. Thank you!",
        )
        await interaction.followup.send(embed=feedback_embed, ephemeral=True)
        self.view.feedback_sent = True
        self.view.disable_feedback_button()
        await interaction.message.edit(view=self.view)


class ReportModal(discord.ui.Modal, title="Report an Issue"):
    def __init__(self, view: TicketRatingView):
        super().__init__()
        self.view = view
        self.bot = view.bot
        self.issue = discord.ui.TextInput(
            label="Describe your issue",
            style=discord.TextStyle.paragraph,
            required=True,
        )
        self.add_item(self.issue)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        message = interaction.message
        user = interaction.user
        embed = message.embeds[1]
        footer = (embed.footer.text).split()
        channel_id = footer[-1]
        guild_id = None
        thread_id = None

        data = await self.bot.data_manager.get_guild_and_log(channel_id)
        if len(data) != 0:
            guild_id = data[0][0]
            thread_id = data[0][1]

        config = await self.bot.data_manager.get_or_load_config(guild_id)
        if config is not None:
            report_id = config["report_id"]

        report_channel = await self.bot.cache.get_channel(report_id)
        if report_channel:
            embed = Embeds.error(
                title="New Issue Reported",
                description=self.issue.value,
            )

            embed.set_author(
                name=f"{user.name} | {user.id}",
                icon_url=(user.avatar and user.avatar.url) or user.display_avatar.url,
            )
            embed.add_field(name="Ticket Log", value=f"<#{thread_id}>")
            await report_channel.send(embed=embed)

        report_embed = Embeds.success(
            description="Your issue has been reported. Thank you!",
        )
        await interaction.followup.send(embed=report_embed, ephemeral=True)
        self.view.report_sent = True
        self.view.disable_report_button()
        await interaction.message.edit(view=self.view)
