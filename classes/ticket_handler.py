import discord
import asyncio
from discord import PartialEmoji, SelectOption
from discord.ext import commands
from discord.ui import View, Select
from datetime import datetime, timezone
from classes.ticket_opener import TicketOpener
import json


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
                    timeoutEmbed=discord.Embed(title="", 
                                               description="Embed has timed out. Please run the command again.", 
                                               color=discord.Color.red())
                    await self.message.edit(embed=timeoutEmbed)
                except discord.Forbidden:
                    pass
        except Exception:
            print("embed timeout exception")


class TicketSelect(discord.ui.Select):
    def __init__(self, bot, tickets: list[dict]):
        self.bot = bot
        self.selected_ticket = None

        options = []

        for ticket in tickets:
            guild = self.bot.get_guild(ticket['guildID'])

            if guild:
                options.append(SelectOption(
                        label=f"{guild.name}",
                        value=str(ticket['ticketID']),
                        description=f"Channel ID: {ticket['channelID']}"))

        super().__init__(
            placeholder="Select a ticket by server",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        self.selected_ticket = self.values[0]
        await interaction.response.send_message(
            f"Ticket {self.selected_ticket} selected.",
            ephemeral=True
        )
        self.view.selected_ticket = self.selected_ticket
        self.view.stop()


class TicketSelectView(TimeoutSafeView):
    def __init__(self, bot, tickets: list[dict]):
        super().__init__()
        self.bot = bot
        self.selected_ticket = None
        self.add_item(TicketSelect(bot, tickets))


class ServerSelect(discord.ui.Select):
    def __init__(self, bot, shared_guilds, dm_channelID):
        # List of guild names
        # FIXME custom emojis at some point
        options = [SelectOption(label=guild.name, 
                                value=str(guild.id)) 
                                for guild in shared_guilds]
        
        super().__init__(placeholder="Choose a server...", min_values=1, max_values=1, options=options)
        self.bot = bot
        self.dm_channelID = dm_channelID

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guildID = int(self.values[0])
        guild = self.bot.get_guild(guildID)
        dm_channelID = self.dm_channelID

        # Check if user is in this guild
        try:
            member = await guild.fetch_member(interaction.user.id)
        except discord.NotFound:
            errorEmbed = discord.Embed(
                description=f"❌ You are not in that server [this server is only visible during testing]",
                color=discord.Color.red())
            
            await interaction.channel.send(embed=errorEmbed)

            try:
                await interaction.message.delete()
            except discord.HTTPException:
                pass

            if self.view:
                self.view.stop()
            return

        # Check if user already has a ticket open with this guild
        tickets = await self.bot.data_manager.get_or_load_user_tickets(interaction.user.id)
        if (tickets is not None) and (any(ticket["guildID"] == guildID for ticket in tickets)):
            errorEmbed = discord.Embed(
                description=f"❌ You already have a ticket open with **{guild.name}**.\n\n"
                            "Send a message in this channel to reply to your open ticket instead.",
                color=discord.Color.red())
            
            await interaction.channel.send(embed=errorEmbed)

            try:
                await interaction.message.delete()
            except discord.HTTPException:
                pass

            if self.view:
                self.view.stop()
            return
        
        # Check if guild has a ticket category --> dont think i need to do this
        # config = await self.bot.data_manager.get_or_load_config(guildID)
        # if config is not None:
        #     inboxID = config["inboxID"]
        #     if inboxID:
        #         category = self.bot.get_channel(inboxID)
        #         if not category:
        #             try:
        #                 category = await asyncio.wait_for(self.bot.fetch_channel(inboxID), timeout=1)
        #             except Exception:
        #                 category = None
        # if not types:
        #     errorEmbed = discord.Embed(
        #         description=f"❌ **{guild.name}** has not set up any ticket types yet.\n\n"
        #                     "Please contact a server admin if you believe this is a mistake.",
        #         color=discord.Color.red())
            
        #     await interaction.channel.send(embed=errorEmbed)

        #     try:
        #         await interaction.message.delete()
        #     except discord.HTTPException:
        #         pass

        #     if self.view:
        #         self.view.stop()
        #     return

        # Load available ticket types
        types = await self.bot.data_manager.get_or_load_guild_types(guildID)
        if not types:
            errorEmbed = discord.Embed(
                description=f"❌ **{guild.name}** has not set up any ticket types yet.\n\n"
                            "Please contact a server admin if you believe this is a mistake.",
                color=discord.Color.red())
            
            await interaction.channel.send(embed=errorEmbed)

            try:
                await interaction.message.delete()
            except discord.HTTPException:
                pass

            if self.view:
                self.view.stop()
            return
        
        
        
        loadingEmbed = discord.Embed(description="Loading ticket types...", color=discord.Color.blue())
        await interaction.message.edit(embed=loadingEmbed)

        # Build the category select embed
        categoryEmbed = discord.Embed(
            title="Select a Ticket Type", 
            description="Please select a type for your ticket with the drop-down menu below.\n\n"
                        "If you are unsure what to choose, or your topic is not listed, select \"Other.\"",
            color=discord.Color.blue())
        if guild.icon:
            categoryEmbed.set_author(name=guild.name, icon_url=guild.icon.url)
            categoryEmbed.set_thumbnail(url=guild.icon.url)
        else:
            categoryEmbed.set_author(name=guild.name)

        # Build and send the category select view
        view = CategorySelectView(self.bot, guild, dm_channelID, types)
        await view.setup()

        try:
            message = await interaction.message.edit(embed=categoryEmbed, view=view)
            view.message = message
        except discord.HTTPException:
            message = await interaction.channel.send(embed=categoryEmbed, view=view)
            view.message = message


class ServerSelectView(TimeoutSafeView):
    def __init__(self, bot, shared_guilds, dm_channelID):
        super().__init__()
        self.bot = bot
        self.add_item(ServerSelect(bot, shared_guilds, dm_channelID))


class DMCategoryButtonView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Open a Ticket", style=discord.ButtonStyle.blurple, custom_id="persistent_dm_button")
    async def send_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        guild = interaction.guild

        if not guild:
            await interaction.followup.send("❌ This button must be used in a server.", ephemeral=True)
            return

        guild_id = guild.id

        try:
            tickets = await self.bot.data_manager.get_or_load_user_tickets(user.id)
            if tickets and any(ticket["guildID"] == guild_id for ticket in tickets):
                await interaction.followup.send("❌ You already have a ticket open with this server. DM me to reply to that ticket instead.", ephemeral=True)
                return

            dm_channel = user.dm_channel or await user.create_dm()
            types = await self.bot.data_manager.get_or_load_guild_types(guild_id)

            embed = discord.Embed(
                title="Select Ticket Type",
                description="Please select a type for your ticket with the drop-down menu below.\n\n"
                            "If you're unsure what to choose, or your topic isn't listed, select \"Other.\"",
                color=discord.Color.blue()
            )
            if guild.icon:
                embed.set_author(name=guild.name, icon_url=guild.icon.url)
                embed.set_thumbnail(url=guild.icon.url)
            else:
                embed.set_author(name=guild.name)

            view = CategorySelectView(self.bot, guild, dm_channel.id, types)
            await view.setup()

            sent_msg = await dm_channel.send(embed=embed, view=view)
            view.message = sent_msg

            await interaction.followup.send(
                f"✅ Ticket creation process started. Please navigate to your DMs: <#{dm_channel.id}>",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send("❌ I couldn’t DM you! Please enable DMs and try again.", ephemeral=True)


class CategorySelect(discord.ui.Select):
    def __init__(self, bot, guild, dm_channelID, types, options, parent_category_id=None):
        self.bot = bot
        self.guild = guild
        self.dm_channelID = dm_channelID
        self.types = types
        self.parent_category_id = parent_category_id  # If selecting a subtype
        super().__init__(placeholder="Choose a ticket type..." if parent_category_id is None else "Choose a sub-type...", options=options)


    async def callback(self, interaction: discord.Interaction):
        values = self.values[0].split()
        selected_typeID = int(values[0])
        selected_categoryID = int(values[1])
        dm_channelID = self.dm_channelID
        guild = self.guild
        subtypes = []

        if self.parent_category_id is None:
            # Check for subtypes
            subtypes = [
                entry for entry in self.types 
                if int(entry.get("subType")) == selected_categoryID
            ]
        else:
            selected_categoryID = self.parent_category_id

        # Safely fetch the selected category
        print("selected category id is", selected_categoryID)
        print("parent category id is", self.parent_category_id)
        category = self.bot.get_channel(selected_categoryID)
        if not category:
            try:
                category = await asyncio.wait_for(self.bot.fetch_channel(selected_categoryID), timeout=1)
            except Exception:
                category = None

        # Only calls for parent types WITH subtypes
        if subtypes:
            subtype_embed = discord.Embed(
                title="Select a Ticket Sub-Type",
                description=f"You selected ticket type **{category.name}**.\n\nPlease choose "
                            "the ticket sub-type that best fits your situation below.",
                color=discord.Color.yellow())
            
            if guild.icon:
                subtype_embed.set_author(name=guild.name, icon_url=guild.icon.url)
                subtype_embed.set_thumbnail(url=guild.icon.url)
            else:
                subtype_embed.set_author(name=guild.name)

            # Show subtypes select
            view = CategorySelectView(self.bot, self.guild, self.dm_channelID, self.types, 
                                      parent_category_id=selected_categoryID)
            await view.setup()
            message = await interaction.response.edit_message(embed=subtype_embed, view=view)
            view.message = message

        else:
            # No subtypes, proceed to modal
            modal_template = next(
                (entry["form"] for entry in self.types if int(entry["categoryID"]) == selected_categoryID), 
                None)
            source_view = self.view

            if modal_template:
                await send_dynamic_modal(
                    self.bot, interaction, self.guild, selected_categoryID, selected_typeID, dm_channelID,
                    modal_template, source_view, parent_category_id=self.parent_category_id)
            else:
                errorEmbed = discord.Embed(
                    description="❌ The server you are trying to contact has improperly set up this ticket type option. Please contact a server admin.",
                    color=discord.Color.red())
                
                await interaction.response.send_message(embed=errorEmbed, ephemeral=True)


    @classmethod
    async def create(cls, bot, guild, dm_channelID, types, parent_category_id=None):
        def safe_partial_emoji(e):
            try:
                return PartialEmoji.from_str(e) if e else None
            except Exception:
                return None

        if parent_category_id is None:
            filtered_types = [entry for entry in types if int(entry.get("subType")) == -1]
        else:
            filtered_types = [entry for entry in types if int(entry.get("subType")) == parent_category_id]

        options = [
            SelectOption(
                label=str(entry["typeName"]),
                value=f"{entry['typeID']} {entry['categoryID']}",
                emoji=safe_partial_emoji(entry.get("typeEmoji")),
                description=str(entry["typeDescrip"])
            ) for entry in filtered_types
        ]

        return cls(bot, guild, dm_channelID, types, options, parent_category_id)


class CategorySelectView(TimeoutSafeView):
    def __init__(self, bot, guild, dm_channelID, types, parent_category_id=None):
        super().__init__()
        self.bot = bot
        self.guild = guild
        self.dm_channelID = dm_channelID
        self.types = types
        self.parent_category_id = parent_category_id

    async def setup(self):
        select = await CategorySelect.create(self.bot, self.guild, self.dm_channelID, self.types, self.parent_category_id)
        self.add_item(select)


async def send_dynamic_modal(bot, interaction, guild, categoryID, typeID, dm_channelID, modal_template, view, parent_category_id=None):
    category = bot.get_channel(categoryID)
    if not category:
        try:
            category = await asyncio.wait_for(bot.fetch_channel(categoryID), timeout=1)
        except Exception:
            category = None

    # Fallback to parent category if needed
    if not category and parent_category_id:
        category = bot.get_channel(parent_category_id)
        if not category:
            try:
                category = await asyncio.wait_for(bot.fetch_channel(parent_category_id), timeout=1)
            except Exception:
                category = None

    if not category:
        errorEmbed = discord.Embed(
            description="❌ Couldn't find ticket category in the destination server. Please contact a server admin.",
            color=discord.Color.red()
        )
        await interaction.channel.send(embed=errorEmbed)
        return

    title = modal_template.get("title", "Form")
    fields = modal_template.get("fields", [])

    # Modal submission handler
    async def handle_submit(interaction: discord.Interaction, values: dict):
        try:
            # Delete the original DM message with the view
            await view.message.delete()
        except Exception as e:
            print(f"Failed to delete old message: {e}")

        await interaction.response.defer()
            
        sendingEmbed = discord.Embed(description="Opening ticket...", color=discord.Color.blue())
        opening_message = await interaction.channel.send(embed=sendingEmbed)

        opener = TicketOpener(bot)
        status = await opener.open_ticket(interaction, guild, category, typeID, dm_channelID, values, title)
        await opening_message.delete()

        if not status:
            errorEmbed = discord.Embed(
                description="❌ Couldn't open a ticket in the destination server. Please contact a server admin.",
                color=discord.Color.red()
            )
            await interaction.channel.send(embed=errorEmbed)
            
    # Send the modal
    await interaction.response.send_modal(DynamicFormModal(title, fields, handle_submit, view))

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
                style=discord.TextStyle.paragraph if field["style"] == "paragraph" else discord.TextStyle.short,
                min_length=field.get("min_length", 1),
                max_length=field.get("max_length", 100),
                required = field.get("required", True)
            )
            self.add_item(input)

    async def on_submit(self, interaction: discord.Interaction):
        for child in self.children:
            self.values[child.label] = child.value

        await self.on_submit_callback(interaction, self.values)
        message = None

        # Stop the original view to disable its components
        if self.source_view:
            message = self.source_view.message
            self.source_view.stop()

        # Delete the original category select message
        if (message):
            try:
                await message.delete()
            except discord.HTTPException:
                pass


class TicketRatingView(discord.ui.View):
    def __init__(self, bot, guildID: int, threadID: int, timeout=300):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guildID = guildID
        self.threadID = threadID
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

    @discord.ui.button(label="Resolved", style=discord.ButtonStyle.success, row=0, custom_id="resolved")
    async def resolved_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.rating_given:
            self.rating_given = True
            self.disable_rating_buttons()
            await interaction.response.send_message("Glad to hear it was resolved!", ephemeral=True)
            await interaction.message.edit(view=self)

    @discord.ui.button(label="Not Resolved", style=discord.ButtonStyle.danger, row=0, custom_id="not_resolved")
    async def not_resolved_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.rating_given:
            self.rating_given = True
            self.disable_rating_buttons()
            await interaction.response.send_message("Sorry to hear that. You can leave feedback or report the issue below.", ephemeral=True)
            await interaction.message.edit(view=self)

    @discord.ui.button(label="📝 Leave Feedback", style=discord.ButtonStyle.secondary, row=1, custom_id="feedback")
    async def feedback_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.feedback_sent:
            await interaction.response.send_modal(FeedbackModal(view=self))

    @discord.ui.button(label="🚩 Report Issue", style=discord.ButtonStyle.secondary, row=1, custom_id="report")
    async def report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.report_sent:
            await interaction.response.send_modal(ReportModal(view=self))


class FeedbackModal(discord.ui.Modal, title="Feedback Form"):
    def __init__(self, view: TicketRatingView):
        super().__init__()
        self.view = view
        self.bot = view.bot
        self.guildID = view.guildID
        self.threadID = view.threadID
        self.feedback = discord.ui.TextInput(
            label="Leave your feedback",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.feedback)

    async def on_submit(self, interaction: discord.Interaction):
        config = await self.bot.data_manager.get_or_load_config(self.guildID)
        if config is not None:
            feedbackID = config["feedbackID"]
        #FIXME, error case

        feedback_channel = interaction.client.get_channel(feedbackID)
        if feedback_channel:
            embed = discord.Embed(
                title="New Feedback Submitted",
                description=self.feedback.value,
                color=discord.Color.blue()
            )
            embed.set_author(name=f"{interaction.user.name} | {interaction.user.id}", icon_url=interaction.user.display_avatar.url)
            embed.add_field(name="Ticket Log", value=f"<#{self.view.threadID}>")
            await feedback_channel.send(embed=embed)
        await interaction.response.send_message("Thanks for your feedback!", ephemeral=True)
        self.view.feedback_sent = True
        self.view.disable_feedback_button()
        await interaction.message.edit(view=self.view)


class ReportModal(discord.ui.Modal, title="Report an Issue"):
    def __init__(self, view: TicketRatingView):
        super().__init__()
        self.view = view
        self.bot = view.bot
        self.guildID = view.guildID
        self.threadID = view.threadID
        self.issue = discord.ui.TextInput(
            label="Describe the issue",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.issue)

    async def on_submit(self, interaction: discord.Interaction):
        config = await self.bot.data_manager.get_or_load_config(self.guildID)
        if config is not None:
            reportID = config["reportID"]
        #FIXME, error case
        report_channel = interaction.client.get_channel(reportID)
        if report_channel:
            embed = discord.Embed(
                title="New Issue Reported",
                description=self.issue.value,
                color=discord.Color.red()
            )
            embed.set_author(name=f"{interaction.user.name} | {interaction.user.id}", icon_url=interaction.user.display_avatar.url)
            embed.add_field(name="Ticket Log", value=f"<#{self.view.threadID}>")
            await report_channel.send(embed=embed)
        await interaction.response.send_message("Your issue has been reported. Thank you!", ephemeral=True)
        self.view.report_sent = True
        self.view.disable_report_button()
        await interaction.message.edit(view=self.view)


# Example usage when closing a ticket:
# threadID = 123456789012345678
# embed = discord.Embed(title="Ticket Closed", description="Thanks for using support! Let us know how it went.", color=discord.Color.blurple())
# view = TicketRatingView(threadID=threadID)
# message = await channel.send(embed=embed, view=view)
# view.message = message


