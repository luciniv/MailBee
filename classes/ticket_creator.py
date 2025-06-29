import discord
import time
import asyncio
from discord import PartialEmoji, SelectOption
from discord.ext import commands
from discord.ui import View, Button
from datetime import datetime, timezone
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
                    timeoutEmbed=discord.Embed(title="", 
                                               description="Embed has timed out. Please run the command again.", 
                                               color=discord.Color.red())
                    await self.message.edit(embed=timeoutEmbed)
                except discord.Forbidden:
                    pass
        except Exception:
            pass


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
        user = interaction.user

        existing = await self.bot.data_manager.get_or_load_blacklist_entry(guild.id, user.id)
        if existing is not None:
            errorEmbed = discord.Embed(
                description=f"❌ You are blacklisted from opening tickets with this server.",
                color=discord.Color.red())
            await interaction.channel.send(embed=errorEmbed)

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
                member = await asyncio.wait_for(guild.fetch_member(interaction.user.id), timeout=1)

            except discord.errors.NotFound:
                errorEmbed = discord.Embed(
                    description=f"❌ You are not in that server. If you would like to open a ticket there, "
                                "please join the server first.",
                    color=discord.Color.red())
                await interaction.channel.send(embed=errorEmbed)

                try:
                    await interaction.message.delete()
                except discord.errors.HTTPException:
                    pass

                if self.view:
                    self.view.stop()
                return
            
            except Exception:
                errorEmbed = discord.Embed(
                    description=f"❌ An error occurred with Discord's API. Please try again.",
                    color=discord.Color.red())
                await interaction.channel.send(embed=errorEmbed)

                try:
                    await interaction.message.delete()
                except discord.errors.HTTPException:
                    pass

                if self.view:
                    self.view.stop()
                return
        
        await self.bot.cache.store_guild_member(guildID, member)

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


    @discord.ui.button(label="Open a Ticket", style=discord.ButtonStyle.green, custom_id="persistent_dm_button", emoji="✉️")
    async def send_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        errorEmbed = discord.Embed(description=" ", color=discord.Color.red())

        user = interaction.user
        guild = interaction.guild
        limited, retry_after, was_notified = self.bot.queue.check_user_action_cooldown("open_ticket_button", user.id)

        if limited:
            if not was_notified:
                self.bot.queue.user_action_cooldowns["open_ticket_button"]["notified"][user.id] = True
                errorEmbed.description = (
                    f"❌ You're clicking a bit too quickly — please wait {retry_after:.1f} seconds."
                )
                await interaction.followup.send(embed=errorEmbed, ephemeral=True)
            # else: silently ignore
            return

        if not guild:
            errorEmbed.description="❌ This button must be used in a server."
            await interaction.followup.send(embed=errorEmbed, ephemeral=True)
            return

        guild_id = guild.id

        existing = await self.bot.data_manager.get_or_load_blacklist_entry(guild_id, user.id)
        if existing is not None:
            errorEmbed.description="❌ You are blacklisted from opening tickets with this server."
            await interaction.followup.send(embed=errorEmbed, ephemeral=True)
            return

        try:
            tickets = await self.bot.data_manager.get_or_load_user_tickets(user.id)
            if tickets and any(ticket["guildID"] == guild_id for ticket in tickets):
                errorEmbed.description=("❌ You already have a ticket open with this server. "
                                        "Direct message me to reply to that ticket instead.")
                await interaction.followup.send(embed=errorEmbed, ephemeral=True)
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

            startView = View()
            startView.add_item(Button(label="Jump to ticket", url=f"https://discord.com/channels/@me/{dm_channel.id}/{sent_msg.id}"))

            startEmbed = discord.Embed(title="Ticket Started", description="A ticket has been started in your direct messages!",
                                       color=discord.Color.green())

            await interaction.followup.send(embed=startEmbed, view=startView, ephemeral=True)

        except discord.Forbidden:
            errorEmbed.description="❌ I couldn’t message you! Please enable direct messages and try again."
            await interaction.followup.send(embed=errorEmbed, ephemeral=True)


class CategorySelect(discord.ui.Select):
    def __init__(self, bot, guild, dm_channelID, types, options, parent_category_id=None):
        self.bot = bot
        self.guild = guild
        self.dm_channelID = dm_channelID
        self.types = types
        self.parent_category_id = parent_category_id  # If selecting a subtype
        super().__init__(placeholder="Choose a ticket type..." if parent_category_id is None else "Choose a sub-type...", options=options)


    async def callback(self, interaction: discord.Interaction):
        value = self.values[0].split()
        selected_typeID = int(value[0])
        selected_categoryID = int(value[1])
        selected_NSFWID = int(value[2])
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
        category = await self.bot.cache.get_channel(selected_categoryID)

        # Only calls for parent types WITH subtypes
        if (len(subtypes) > 0):

            subtype_embed = discord.Embed(
                title="Select a Ticket Sub-Type",
                description=f"You selected ticket type **{category.name}**.\n\nPlease choose "
                            "the ticket sub-type that best fits your situation below.",
                color=discord.Color.green())
            
            if guild.icon:
                subtype_embed.set_author(name=guild.name, icon_url=guild.icon.url)
                subtype_embed.set_thumbnail(url=guild.icon.url)
            else:
                subtype_embed.set_author(name=guild.name)

            # Show subtypes select
            newView = CategorySelectView(self.bot, self.guild, self.dm_channelID, self.types, 
                                      parent_category_id=selected_categoryID)
            await newView.setup()

            await interaction.response.edit_message(embed=subtype_embed, view=newView)
            newView.message = interaction.message

        else:
            # No subtypes, proceed to modal OR reply with redirect
            if selected_categoryID == 0:
                redirect_text = next(
                (entry["redirectText"] for entry in self.types if int(entry["typeID"]) == selected_typeID), 
                None)

                redirectEmbed = discord.Embed(title="Auto-Response [Ticket NOT Created]",
                                              description=redirect_text,
                                              color=discord.Color.blue())
                redirectEmbed.timestamp = datetime.now(timezone.utc)
                if guild.icon:
                    redirectEmbed.set_footer(text=guild.name, icon_url=guild.icon.url)
                else:
                    redirectEmbed.set_footer(text=guild.name)
                
                try:
                    await interaction.message.delete()
                except discord.HTTPException:
                    pass

                if self.view:
                    self.view.stop()

                await interaction.channel.send(embed=redirectEmbed)
                return

            modal_template = next(
                (entry["form"] for entry in self.types if int(entry["typeID"]) == selected_typeID), 
                None)
            source_view = self.view

            if modal_template:
                await send_dynamic_modal(
                    self.bot, interaction, self.guild, category, selected_typeID, selected_NSFWID, dm_channelID,
                    modal_template, source_view)
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

        #{entry["NSFWCategoryID"]}

        options = [
            SelectOption(
                label=str(entry["typeName"]),
                value=f"{entry['typeID']} {entry['categoryID']} {entry['NSFWCategoryID']}",
                emoji=safe_partial_emoji(entry.get("typeEmoji")),
                description=str(entry["typeDescrip"])
            ) for entry in filtered_types]
        
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

        # Only add back button if viewing subtypes
        if self.parent_category_id is not None:
            self.add_item(BackButton(self.bot, self.guild, self.dm_channelID, self.types))


class BackButton(discord.ui.Button):
    def __init__(self, bot, guild, dm_channelID, types):
        super().__init__(style=discord.ButtonStyle.success, label="⬅ Go Back")
        self.bot = bot
        self.guild = guild
        self.dm_channelID = dm_channelID
        self.types = types


    async def callback(self, interaction: discord.Interaction):
        categoryEmbed = discord.Embed(
            title="Select a Ticket Type", 
            description="Please select a type for your ticket with the drop-down menu below.\n\n"
                        "If you are unsure what to choose, or your topic is not listed, select \"Other.\"",
            color=discord.Color.blue())
        if self.guild.icon:
            categoryEmbed.set_author(name=self.guild.name, icon_url=self.guild.icon.url)
            categoryEmbed.set_thumbnail(url=self.guild.icon.url)
        else:
            categoryEmbed.set_author(name=self.guild.name)

        view = CategorySelectView(self.bot, self.guild, self.dm_channelID, self.types)
        await view.setup()

        try:
            await interaction.response.defer(thinking=False)
            message = await interaction.message.edit(embed=categoryEmbed, view=view)
            view.message = message
        except discord.HTTPException:
            await interaction.response.defer(thinking=False)
            message = await interaction.channel.send(embed=categoryEmbed, view=view)
            view.message = message


async def send_dynamic_modal(bot, interaction, guild, category, typeID, NSFWID, dm_channelID, modal_template, view):
    if not category:
        errorEmbed = discord.Embed(
            description="❌ Couldn't find ticket category in the destination server. Please contact a server admin.",
            color=discord.Color.red()
        )
        await interaction.channel.send(embed=errorEmbed)
        return

    title = modal_template.get("title", "Form")
    fields = modal_template.get("fields", [])
    start_time = int(time.time())

    # Modal submission handler
    async def handle_submit(interaction: discord.Interaction, values: dict):
        try:
            time_taken = int(time.time()) - start_time
            await interaction.response.defer()

            if NSFWID != -1:
                NSFWembed = discord.Embed(title="Does Your Report Contain NSFW?", 
                                        description="Use the buttons below to select whether your ticket "
                                        "contains **content that is considered Not Safe For Work (NSFW)**, "
                                        "such as:\n"
                                        "> - Gore or extreme violence\n"
                                        "> - Suggestive, explicit, or sexual content\n"
                                        "> - Anything violating **Rule 1.** of our server's rules list\n"
                                        "We ask this to ensure your report is handed to the appropriate staff "
                                        "members, thank you!",
                                        color=discord.Color.red())

                # Build and send the NSFW button view
                view = NSFWButtonView(bot, guild, category, typeID, NSFWID, dm_channelID, values, title, time_taken)

                try:
                    message = await interaction.message.edit(embed=NSFWembed, view=view)
                    view.message = message
                except discord.HTTPException:
                    message = await interaction.channel.send(embed=NSFWembed, view=view)
                    view.message = message
            else:
                sendingEmbed = discord.Embed(description="Opening ticket...", color=discord.Color.blue())
                opening_message = await interaction.channel.send(embed=sendingEmbed)
                user = interaction.user

                opener = TicketOpener(bot)
                status = await opener.open_ticket(user, guild, category, typeID, values, title, time_taken, False)
                await opening_message.delete()

                if not status:
                    errorEmbed = discord.Embed(
                        description="❌ Couldn't open a ticket in the destination server. Please contact a server admin.",
                        color=discord.Color.red()
                    )
                    await interaction.channel.send(embed=errorEmbed)
        except Exception as e:
            print(e)
            
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
        # if self.source_view:
        #     message = self.source_view.message
        #     self.source_view.stop()

        # # Delete the original category select message
        # if (message):
        #     try:
        #         await message.delete()
        #     except discord.HTTPException:
        #         pass


class NSFWButtonView(TimeoutSafeView):
    def __init__(self, bot, guild, category, typeID, NSFWID, dm_channelID, values, title, time_taken):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild
        self.category = category
        self.typeID = typeID
        self.NSFWID = NSFWID
        self.dm_channelID = dm_channelID
        self.values = values
        self.title = title
        self.time_taken = time_taken
        self.message = None
   

    @discord.ui.button(label="Yes, it contains NSFW", style=discord.ButtonStyle.success, row=0)
    async def nsfw_yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        try:
            # Delete the original DM message with the view
            await self.message.delete()
        except Exception as e:
            print(f"Failed to delete old message: {e}")

        category = await self.bot.cache.get_channel(self.NSFWID)
        if not category:
            errorEmbed = discord.Embed(
                description="❌ Couldn't find NSFW ticket category in the destination server. "
                            "Please contact a server admin.",
                color=discord.Color.red())
            await interaction.channel.send(embed=errorEmbed)
            return
        self.category = category
            
        sendingEmbed = discord.Embed(description="Opening ticket...", color=discord.Color.blue())
        opening_message = await interaction.channel.send(embed=sendingEmbed)
        user = interaction.user

        opener = TicketOpener(self.bot)
        status = await opener.open_ticket(user, self.guild, self.category, self.typeID, 
                                          self.values, self.title, self.time_taken, True)
        await opening_message.delete()

        if not status:
            errorEmbed = discord.Embed(
                description="❌ Couldn't open a ticket in the destination server. Please contact a server admin.",
                color=discord.Color.red()
            )
            await interaction.channel.send(embed=errorEmbed)


    @discord.ui.button(label="No, it does not", style=discord.ButtonStyle.danger, row=0)
    async def nsfw_no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            # Delete the original DM message with the view
            await self.message.delete()
        except Exception as e:
            print(f"Failed to delete old message: {e}")
            
        sendingEmbed = discord.Embed(description="Opening ticket...", color=discord.Color.blue())
        opening_message = await interaction.channel.send(embed=sendingEmbed)
        user = interaction.user

        opener = TicketOpener(self.bot)
        status = await opener.open_ticket(user, self.guild, self.category, self.typeID, 
                                          self.values, self.title, self.time_taken, False)
        await opening_message.delete()

        if not status:
            errorEmbed = discord.Embed(
                description="❌ Couldn't open a ticket in the destination server. Please contact a server admin.",
                color=discord.Color.red()
            )
            await interaction.channel.send(embed=errorEmbed)


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


    @discord.ui.button(label="Satisfied", style=discord.ButtonStyle.success, row=0, emoji="👍", custom_id="resolved")
    async def resolved_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.rating_given:
            self.rating_given = True
            self.disable_rating_buttons()
            responseEmbed = discord.Embed(description="We're glad to hear you're satisfied with your ticket! "
                                                      "You can leave feedback or report an issue using the buttons "
                                                      "provided above.",
                                    color=discord.Color.green()) 
            await interaction.response.send_message(embed=responseEmbed, ephemeral=True)
            await interaction.message.edit(view=self)

            message = interaction.message
            embed = message.embeds[0]
            footer = (embed.footer.text).split()
            ticketID = footer[-1]

            await self.bot.data_manager.update_rating(ticketID, "Satisfied")


    @discord.ui.button(label="Dissatisfied", style=discord.ButtonStyle.danger, row=0, emoji="👎", custom_id="not_resolved")
    async def not_resolved_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.rating_given:
            self.rating_given = True
            self.disable_rating_buttons()
            responseEmbed = discord.Embed(description="We're sorry to hear you're dissatisfied with your ticket. "
                                                      "You can leave feedback or report an issue using the buttons "
                                                      "provided above.",
                                    color=discord.Color.green())
            await interaction.response.send_message(embed=responseEmbed, ephemeral=True)
            await interaction.message.edit(view=self)

            message = interaction.message
            embed = message.embeds[0]
            footer = (embed.footer.text).split()
            ticketID = footer[-1]

            await self.bot.data_manager.update_rating(ticketID, "Dissatisfied")


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
        self.feedback = discord.ui.TextInput(
            label="Leave your feedback",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.feedback)


    async def on_submit(self, interaction: discord.Interaction):
        message = interaction.message
        user = interaction.user
        embed = message.embeds[0]
        footer = (embed.footer.text).split()
        ticketID = footer[-1]
        guildID = None
        threadID = None

        data = await self.bot.data_manager.get_guild_and_log(ticketID)
        if len(data) != 0:
            guildID = data[0][0]
            threadID = data[0][1]

        config = await self.bot.data_manager.get_or_load_config(guildID)
        if config is not None:
            feedbackID = config["feedbackID"]

        feedback_channel = await self.bot.cache.get_channel(feedbackID)
        if feedback_channel:
            embed = discord.Embed(
                title="New Feedback Submitted",
                description=self.feedback.value,
                color=discord.Color.blue()
            )
            embed.set_author(name=f"{user.name} | {user.id}", icon_url=user.display_avatar.url)
            embed.add_field(name="Ticket Log", value=f"<#{threadID}>")
            await feedback_channel.send(embed=embed)
        feedbackEmbed = discord.Embed(description="Your feedback has been recorded. Thank you!",
                                    color=discord.Color.green())
        await interaction.response.send_message(embed=feedbackEmbed, ephemeral=True)
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
            required=True
        )
        self.add_item(self.issue)


    async def on_submit(self, interaction: discord.Interaction):
        message = interaction.message
        user = interaction.user
        embed = message.embeds[0]
        footer = (embed.footer.text).split()
        ticketID = footer[-1]
        guildID = None
        threadID = None

        data = await self.bot.data_manager.get_guild_and_log(ticketID)
        if len(data) != 0:
            guildID = data[0][0]
            threadID = data[0][1]

        config = await self.bot.data_manager.get_or_load_config(guildID)
        if config is not None:
            reportID = config["reportID"]

        report_channel = await self.bot.cache.get_channel(reportID)
        if report_channel:
            embed = discord.Embed(
                title="New Issue Reported",
                description=self.issue.value,
                color=discord.Color.red()
            )
        
            embed.set_author(name=f"{user.name} | {user.id}", icon_url=user.display_avatar.url)
            embed.add_field(name="Ticket Log", value=f"<#{threadID}>")
            await report_channel.send(embed=embed)

        reportEmbed = discord.Embed(description="Your issue has been reported. Thank you!",
                                    color=discord.Color.green())
        await interaction.response.send_message(embed=reportEmbed, ephemeral=True)
        self.view.report_sent = True
        self.view.disable_report_button()
        await interaction.message.edit(view=self.view)


# Example usage when closing a ticket:
# threadID = 123456789012345678
# embed = discord.Embed(title="Ticket Closed", description="Thanks for using support! Let us know how it went.", color=discord.Color.blurple())
# view = TicketRatingView(threadID=threadID)
# message = await channel.send(embed=embed, view=view)
# view.message = message