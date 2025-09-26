import asyncio
import time
from datetime import datetime, timezone

import discord
from discord import PartialEmoji, SelectOption
from discord.ext import commands
from discord.ui import Button, View

from classes.ticket_opener import TicketOpener


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
                    timeout_embed = discord.Embed(
                        title="",
                        description="Embed has timed out. Repeat your prior command or action if you need more time.",
                        color=discord.Color.red(),
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
            error_embed = discord.Embed(
                description="❌ Internal error, please try sending your message again.",
                color=discord.Color.red(),
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
        # FIXME custom emojis at some point
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

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild_id = int(self.values[0])
        guild = self.bot.get_guild(guild_id)
        dm_channel_id = self.dm_channel_id
        user = interaction.user

        blacklisted = await self.bot.data_manager.get_blacklist_entry(guild.id, user.id)
        if blacklisted is not None:
            error_embed = discord.Embed(
                description=f"❌ You are blacklisted from opening tickets with this server.",
                color=discord.Color.red(),
            )
            await interaction.channel.send(embed=error_embed)

            try:
                await interaction.message.delete()
            except discord.errors.HTTPException:
                pass

            if self.view:
                self.view.stop()
            return

        # Check if user is in this guild
        member = guild.get_member(interaction.user.id)
        if member is None:
            try:
                member = await asyncio.wait_for(
                    guild.fetch_member(interaction.user.id), timeout=1
                )

            except discord.errors.NotFound:
                error_embed = discord.Embed(
                    description=f"❌ You are not in that server. If you would like to open a ticket there, "
                    "please join the server first.",
                    color=discord.Color.red(),
                )
                await interaction.channel.send(embed=error_embed)

                try:
                    await interaction.message.delete()
                except discord.errors.HTTPException:
                    pass

                if self.view:
                    self.view.stop()
                return

            except Exception:
                error_embed = discord.Embed(
                    description=f"❌ An error occurred with Discord's API. Please try again.",
                    color=discord.Color.red(),
                )
                await interaction.channel.send(embed=error_embed)

                try:
                    await interaction.message.delete()
                except discord.errors.HTTPException:
                    pass

                if self.view:
                    self.view.stop()
                return

        await self.bot.cache.store_guild_member(guild_id, member)

        # Check if user already has a ticket open with this guild
        tickets = await self.bot.data_manager.get_or_load_user_tickets(
            interaction.user.id
        )
        if (tickets is not None) and (
            any(ticket["guild_id"] == guild_id for ticket in tickets)
        ):
            error_embed = discord.Embed(
                description=f"❌ You already have a ticket open with **{guild.name}**.\n\n"
                "Send a message in this channel to reply to your open ticket instead.",
                color=discord.Color.red(),
            )
            await interaction.channel.send(embed=error_embed)

            try:
                await interaction.message.delete()
            except discord.HTTPException:
                pass

            if self.view:
                self.view.stop()
            return

        # Check if guild is accepting tickets
        config = await self.bot.data_manager.get_or_load_config(guild_id)
        if config is None or config["accepting"] != "true":
            error_embed = discord.Embed(
                title="Ticket Creation is Disabled",
                description=(
                    config["accepting"]
                    if config
                    else "This server has not set up ticket creation yet."
                ),
                color=discord.Color.red(),
            )
            await interaction.channel.send(embed=error_embed)

            try:
                await interaction.message.delete()
            except discord.HTTPException:
                pass

            if self.view:
                self.view.stop()
            return

        # Load available ticket types
        types = await self.bot.data_manager.get_or_load_guild_types(guild_id)
        if not types:
            error_embed = discord.Embed(
                description=f"❌ **{guild.name}** has not set up any ticket types yet.\n\n"
                "Please contact a server admin if you believe this is a mistake.",
                color=discord.Color.red(),
            )
            await interaction.channel.send(embed=error_embed)

            try:
                await interaction.message.delete()
            except discord.HTTPException:
                pass

            if self.view:
                self.view.stop()
            return

        loading_embed = discord.Embed(
            description="Loading ticket types...", color=discord.Color.blue()
        )
        await interaction.message.edit(embed=loading_embed)

        # Build the category select embed
        category_embed = discord.Embed(
            title="Select a Ticket Type",
            description="Please select a type for your ticket with the drop-down menu below.\n\n"
            'If you are unsure what to choose, or your topic is not listed, select "Other."',
            color=discord.Color.blue(),
        )
        if guild.icon:
            category_embed.set_author(name=guild.name, icon_url=guild.icon.url)
            category_embed.set_thumbnail(url=guild.icon.url)
        else:
            category_embed.set_author(name=guild.name)

        # Build and send the category select view
        view = CategorySelectView(self.bot, guild, dm_channel_id, types)
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
            error_embed = discord.Embed(description=" ", color=discord.Color.red())

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
                    error_embed.description = f"❌ You're clicking a bit too quickly — please wait {retry_after:.1f} seconds."
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                # else: silently ignore
                return

            if not guild:
                error_embed.description = "❌ This button must be used in a server."
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            guild_id = guild.id

            blacklisted = await self.bot.data_manager.get_blacklist_entry(
                guild_id, user.id
            )
            if blacklisted is not None:
                error_embed.description = (
                    "❌ You are blacklisted from opening tickets with this server."
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            tickets = await self.bot.data_manager.get_or_load_user_tickets(user.id)
            if tickets and any(ticket["guild_id"] == guild_id for ticket in tickets):
                error_embed.description = (
                    "❌ You already have a ticket open with this server. "
                    "Direct message me to reply to that ticket instead."
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            config = await self.bot.data_manager.get_or_load_config(guild_id)
            if config["accepting"] != "true":
                error_embed.title = "Ticket Creation is Disabled"
                error_embed.description = config["accepting"]
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            try:
                dm_channel = user.dm_channel or await user.create_dm()
                types = await self.bot.data_manager.get_or_load_guild_types(guild_id)

                embed = discord.Embed(
                    title="Select Ticket Type",
                    description="Please select a type for your ticket with the drop-down menu below.\n\n"
                    "If you're unsure what to choose, or your topic isn't listed, select \"Other.\"",
                    color=discord.Color.blue(),
                )
                if guild.icon:
                    embed.set_author(name=guild.name, icon_url=guild.icon.url)
                    embed.set_thumbnail(url=guild.icon.url)
                else:
                    embed.set_author(name=guild.name)

                view = CategorySelectView(self.bot, guild, dm_channel.id, types)
                await view.setup()

                sent_msg = await dm_channel.send(embed=embed, view=view)
                if sent_msg is None:
                    error_embed.description = "❌ I couldn’t message you! Please enable direct messages and try again."
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return

                view.message = sent_msg

                start_view = View()
                start_view.add_item(
                    Button(
                        label="Jump to ticket",
                        url=f"https://discord.com/channels/@me/{dm_channel.id}/{sent_msg.id}",
                    )
                )

                start_embed = discord.Embed(
                    title="Ticket Started",
                    description="A ticket has been started in your direct messages!",
                    color=discord.Color.green(),
                )

                await interaction.followup.send(
                    embed=start_embed, view=start_view, ephemeral=True
                )

            except discord.Forbidden:
                error_embed.description = "❌ I couldn’t message you! Please enable direct messages and try again."
                await interaction.followup.send(embed=error_embed, ephemeral=True)
        except Exception as e:
            error_embed.description = (
                "❌ An error occurred. Please wait a bit and try again."
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)


class CategorySelect(discord.ui.Select):
    def __init__(
        self, bot, guild, dm_channel_id, types, options, parent_category_id=None
    ):
        self.bot = bot
        self.guild = guild
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

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0].split()
        selected_type_id = int(value[0])
        selected_category_id = int(value[1])
        selected_nsfw_id = int(value[2])
        dm_channel_id = self.dm_channel_id
        guild = self.guild
        subtypes = []

        if self.parent_category_id is None:
            # Check for subtypes
            subtypes = [
                entry
                for entry in self.types
                if int(entry.get("sub_type")) == selected_category_id
            ]
        else:
            selected_category_id = self.parent_category_id

        # Safely fetch the selected category
        category = await self.bot.cache.get_channel(selected_category_id)

        # Only calls for parent types WITH subtypes
        if len(subtypes) > 0:
            subtype_embed = discord.Embed(
                title="Select a Ticket Sub-Type",
                description=f"You selected ticket type **{category.name}**.\n\nPlease choose "
                "the ticket sub-type that best fits your situation below.",
                color=discord.Color.green(),
            )

            if guild.icon:
                subtype_embed.set_author(name=guild.name, icon_url=guild.icon.url)
                subtype_embed.set_thumbnail(url=guild.icon.url)
            else:
                subtype_embed.set_author(name=guild.name)

            # Show subtypes select
            newView = CategorySelectView(
                self.bot,
                self.guild,
                self.dm_channel_id,
                self.types,
                parent_category_id=selected_category_id,
            )
            await newView.setup()
            await interaction.response.edit_message(embed=subtype_embed, view=newView)
            newView.message = interaction.message

        # No subtypes selected, proceed past selection
        else:
            error_embed = None
            # Handle redirect type
            if selected_category_id == 0:
                redirect_text = next(
                    (
                        entry["redirectText"]
                        for entry in self.types
                        if int(entry["type_id"]) == selected_type_id
                    ),
                    None,
                )

                redirect_embed = discord.Embed(
                    title="Auto-Response [Ticket NOT Created]",
                    description=redirect_text,
                    color=discord.Color.blue(),
                )
                redirect_embed.timestamp = datetime.now(timezone.utc)
                if guild.icon:
                    redirect_embed.set_footer(text=guild.name, icon_url=guild.icon.url)
                else:
                    redirect_embed.set_footer(text=guild.name)

                try:
                    await interaction.message.delete()
                except discord.HTTPException:
                    pass
                if self.view:
                    self.view.stop()
                await interaction.channel.send(embed=redirect_embed)
                return

            # Handle max channels in target category
            elif len(category.channels) >= 50:
                # FIXME use the type name from the DB instead of category name
                error_embed = discord.Embed(
                    description="Thank you for reaching out to the moderation team!\n\n"
                    f"Unfortunately, tickets of type **{category.name}** have "
                    "reached maximum capacity. Please try again later for an "
                    "opening, we thank you in advance for your patience.",
                    color=discord.Color.red(),
                )
            else:
                # Determine if modal is valid or not
                modal_template = next(
                    (
                        entry["form"]
                        for entry in self.types
                        if int(entry["type_id"]) == selected_type_id
                    ),
                    None,
                )
                if modal_template:
                    source_view = self.view

                    ping_roles = next(
                        (
                            entry["ping_roles"]
                            for entry in self.types
                            if int(entry["type_id"]) == selected_type_id
                        ),
                        None,
                    )
                    if (not ping_roles) and (self.parent_category_id is not None):
                        ping_roles = next(
                            (
                                entry["ping_roles"]
                                for entry in self.types
                                if int(entry["category_id"]) == self.parent_category_id
                            ),
                            None,
                        )

                    await send_dynamic_modal(
                        self.bot,
                        interaction,
                        self.guild,
                        category,
                        selected_type_id,
                        selected_nsfw_id,
                        dm_channel_id,
                        ping_roles,
                        modal_template,
                        source_view,
                    )
                    return
                # Handle invalid modal template
                else:
                    error_embed = discord.Embed(
                        description="❌ The server you are trying to contact has improperly set "
                        "up this ticket type option. Please contact a server admin.",
                        color=discord.Color.red(),
                    )

            # Finally, send error message if needed
            try:
                await interaction.message.delete()
            except discord.HTTPException:
                pass
            if self.view:
                self.view.stop()
            await interaction.channel.send(embed=error_embed)
            return

    @classmethod
    async def create(cls, bot, guild, dm_channel_id, types, parent_category_id=None):
        def safe_partial_emoji(e):
            try:
                return PartialEmoji.from_str(e) if e else None
            except Exception:
                return None

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

        # {entry["nsfw_category_id"]}

        options = [
            SelectOption(
                label=str(entry["type_name"]),
                value=f"{entry['type_id']} {entry['category_id']} {entry['nsfw_category_id']}",
                emoji=safe_partial_emoji(entry.get("type_emoji")),
                description=str(entry["type_descrip"]),
            )
            for entry in filtered_types
        ]

        return cls(bot, guild, dm_channel_id, types, options, parent_category_id)


class CategorySelectView(TimeoutSafeView):
    def __init__(self, bot, guild, dm_channel_id, types, parent_category_id=None):
        super().__init__()
        self.bot = bot
        self.guild = guild
        self.dm_channel_id = dm_channel_id
        self.types = types
        self.parent_category_id = parent_category_id

    async def setup(self):
        select = await CategorySelect.create(
            self.bot,
            self.guild,
            self.dm_channel_id,
            self.types,
            self.parent_category_id,
        )
        self.add_item(select)

        # Only add back button if viewing subtypes
        if self.parent_category_id is not None:
            self.add_item(
                BackButton(self.bot, self.guild, self.dm_channel_id, self.types)
            )


class BackButton(discord.ui.Button):
    def __init__(self, bot, guild, dm_channel_id, types):
        super().__init__(style=discord.ButtonStyle.success, label="⬅ Go Back")
        self.bot = bot
        self.guild = guild
        self.dm_channel_id = dm_channel_id
        self.types = types

    async def callback(self, interaction: discord.Interaction):
        category_embed = discord.Embed(
            title="Select a Ticket Type",
            description="Please select a type for your ticket with the drop-down menu below.\n\n"
            'If you are unsure what to choose, or your topic is not listed, select "Other."',
            color=discord.Color.blue(),
        )
        if self.guild.icon:
            category_embed.set_author(
                name=self.guild.name, icon_url=self.guild.icon.url
            )
            category_embed.set_thumbnail(url=self.guild.icon.url)
        else:
            category_embed.set_author(name=self.guild.name)

        view = CategorySelectView(self.bot, self.guild, self.dm_channel_id, self.types)
        await view.setup()

        try:
            await interaction.response.defer(thinking=False)
            message = await interaction.message.edit(embed=category_embed, view=view)
            view.message = message
        except discord.HTTPException:
            await interaction.response.defer(thinking=False)
            message = await interaction.channel.send(embed=category_embed, view=view)
            view.message = message


async def send_dynamic_modal(
    bot,
    interaction,
    guild,
    category,
    type_id,
    nsfw_id,
    dm_channel_id,
    ping_roles,
    modal_template,
    source_view,
):
    if not category:
        error_embed = discord.Embed(
            description="❌ Couldn't find ticket category in the destination server. Please contact a server admin.",
            color=discord.Color.red(),
        )
        await interaction.channel.send(embed=error_embed)
        return

    title = modal_template.get("title", "Form")
    fields = modal_template.get("fields", [])
    start_time = int(time.time())

    # Modal submission handler
    async def handle_submit(interaction: discord.Interaction, values: dict):
        try:
            time_taken = int(time.time()) - start_time
            await interaction.response.defer()

            if nsfw_id != -1:
                nsfw_embed = discord.Embed(
                    title="Does Your Report Contain NSFW?",
                    description="Use the buttons below to select whether your ticket "
                    "contains **content that is considered Not Safe For Work (NSFW)**, "
                    "such as:\n"
                    "> - Gore or extreme violence\n"
                    "> - Suggestive, explicit, or sexual content\n"
                    "> - Anything violating **Rule 1.** of our server's rules list\n"
                    "We ask this to ensure your report is handed to the appropriate staff "
                    "members, thank you!",
                    color=discord.Color.red(),
                )

                # Build and send the NSFW button view
                view = NSFWButtonView(
                    bot,
                    guild,
                    category,
                    type_id,
                    nsfw_id,
                    dm_channel_id,
                    ping_roles,
                    values,
                    title,
                    time_taken,
                )

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

                sending_embed = discord.Embed(
                    description="Creating your ticket...\n\n"
                    "**This may take a moment!** This message will be deleted once "
                    "your ticket is ready.",
                    color=discord.Color.blue(),
                )
                opening_message = await interaction.channel.send(embed=sending_embed)
                user = interaction.user

                opener = TicketOpener(bot)
                status = await opener.open_ticket(
                    user,
                    guild,
                    category,
                    type_id,
                    ping_roles,
                    values,
                    title,
                    time_taken,
                    False,
                )
                await opening_message.delete()

                if not status:
                    error_embed = discord.Embed(
                        description="❌ Couldn't open a ticket in the destination server. Please contact a server admin.",
                        color=discord.Color.red(),
                    )
                    await interaction.channel.send(embed=error_embed)
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
    def __init__(
        self,
        bot,
        guild,
        category,
        type_id,
        nsfw_id,
        dm_channel_id,
        ping_roles,
        values,
        title,
        time_taken,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild
        self.category = category
        self.type_id = type_id
        self.nsfw_id = nsfw_id
        self.dm_channel_id = dm_channel_id
        self.ping_roles = ping_roles
        self.values = values
        self.title = title
        self.time_taken = time_taken
        self.message = None

    @discord.ui.button(
        label="Yes, it contains NSFW", style=discord.ButtonStyle.success, row=0
    )
    async def nsfw_yes_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()

        try:
            # Delete the original DM message with the view
            await self.message.delete()
        except Exception as e:
            print(f"Failed to delete old message: {e}")

        category = await self.bot.cache.get_channel(self.nsfw_id)
        if not category:
            error_embed = discord.Embed(
                description="❌ Couldn't find NSFW ticket category in the destination server. "
                "Please contact a server admin.",
                color=discord.Color.red(),
            )
            await interaction.channel.send(embed=error_embed)
            return
        self.category = category

        sending_embed = discord.Embed(
            description="Creating your ticket...\n\n"
            "**This may take a moment!** This message will be deleted once "
            "your ticket is ready.",
            color=discord.Color.blue(),
        )
        opening_message = await interaction.channel.send(embed=sending_embed)
        user = interaction.user

        opener = TicketOpener(self.bot)
        status = await opener.open_ticket(
            user,
            self.guild,
            self.category,
            self.type_id,
            self.ping_roles,
            self.values,
            self.title,
            self.time_taken,
            True,
        )
        await opening_message.delete()

        if not status:
            error_embed = discord.Embed(
                description="❌ Couldn't open a ticket in the destination server. Please contact a server admin.",
                color=discord.Color.red(),
            )
            await interaction.channel.send(embed=error_embed)

    @discord.ui.button(label="No, it does not", style=discord.ButtonStyle.danger, row=0)
    async def nsfw_no_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        try:
            # Delete the original DM message with the view
            await self.message.delete()
        except Exception as e:
            print(f"Failed to delete old message: {e}")

        sending_embed = discord.Embed(
            description="Creating your ticket...\n\n"
            "**This may take a moment!** This message will be deleted once "
            "your ticket is ready.",
            color=discord.Color.blue(),
        )
        opening_message = await interaction.channel.send(embed=sending_embed)
        user = interaction.user

        opener = TicketOpener(self.bot)
        status = await opener.open_ticket(
            user,
            self.guild,
            self.category,
            self.type_id,
            self.ping_roles,
            self.values,
            self.title,
            self.time_taken,
            False,
        )
        await opening_message.delete()

        if not status:
            error_embed = discord.Embed(
                description="❌ Couldn't open a ticket in the destination server. Please contact a server admin.",
                color=discord.Color.red(),
            )
            await interaction.channel.send(embed=error_embed)


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
        if not self.rating_given:
            self.rating_given = True
            self.disable_rating_buttons()
            response_embed = discord.Embed(
                description="We're glad to hear you're satisfied with your ticket! "
                "You can leave feedback or report an issue using the buttons "
                "provided above.",
                color=discord.Color.green(),
            )
            await interaction.response.send_message(
                embed=response_embed, ephemeral=True
            )
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
        if not self.rating_given:
            self.rating_given = True
            self.disable_rating_buttons()
            response_embed = discord.Embed(
                description="We're sorry to hear you're dissatisfied with your ticket. "
                "You can leave feedback or report an issue using the buttons "
                "provided above.",
                color=discord.Color.green(),
            )
            await interaction.response.send_message(
                embed=response_embed, ephemeral=True
            )
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
            embed = discord.Embed(
                title="New Feedback Submitted",
                description=self.feedback.value,
                color=discord.Color.blue(),
            )
            embed.set_author(
                name=f"{user.name} | {user.id}",
                icon_url=(user.avatar and user.avatar.url) or user.display_avatar.url,
            )
            embed.add_field(name="Ticket Log", value=f"<#{thread_id}>")
            await feedback_channel.send(embed=embed)
        feedback_embed = discord.Embed(
            description="Your feedback has been recorded. Thank you!",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=feedback_embed, ephemeral=True)
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
            embed = discord.Embed(
                title="New Issue Reported",
                description=self.issue.value,
                color=discord.Color.red(),
            )

            embed.set_author(
                name=f"{user.name} | {user.id}",
                icon_url=(user.avatar and user.avatar.url) or user.display_avatar.url,
            )
            embed.add_field(name="Ticket Log", value=f"<#{thread_id}>")
            await report_channel.send(embed=embed)

        report_embed = discord.Embed(
            description="Your issue has been reported. Thank you!",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=report_embed, ephemeral=True)
        self.view.report_sent = True
        self.view.disable_report_button()
        await interaction.message.edit(view=self.view)


# Example usage when closing a ticket:
# thread_id = 123456789012345678
# embed = discord.Embed(title="Ticket Closed", description="Thanks for using support! Let us know how it went.", color=discord.Color.blurple())
# view = TicketRatingView(thread_id=thread_id)
# message = await channel.send(embed=embed, view=view)
# view.message = message
