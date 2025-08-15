import discord
import asyncio
import json
import re
from discord.ext import commands
from discord import app_commands
from discord.app_commands import Range
from classes.ticket_opener import get_overwrites
from classes.ticket_creator import DMCategoryButtonView
from classes.error_handler import *
from classes.paginator import *
from classes.embeds import *
from utils import emojis, checks
from utils.logger import *

def compress_text(text: str) -> str:
    if text == " ":
        return
    # Remove excess whitespace and newlines from user input
    return re.sub(r"\s+", " ", text.strip())


def validate_and_clean_form_template(template: dict) -> dict:
    """Validate and clean the form template."""
    if not isinstance(template, dict):
        raise BotError("Form template must be a JSON object.")

    title = template.get("title")
    if not isinstance(title, str):
        raise BotError("`title` must be a string.")
    
    fields = template.get("fields")
    if not isinstance(fields, list) or not fields:
        raise BotError("`fields` must be a non-empty list.")

    cleaned_fields = []
    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            raise BotError(f"Field #{i + 1} must be a JSON object.")

        label = field.get("label")
        placeholder = field.get("placeholder", " ")
        style = field.get("style", "short")
        max_length = field.get("max_length", 256)
        required = field.get("required", True)

        if not isinstance(label, str):
            raise BotError(f"Field #{i + 1} must have a `label` of type string.")

        if style not in ("short", "paragraph"):
            raise BotError(f"Field #{i + 1} has invalid style `{style}`. Use `short` or `paragraph`.")

        if not isinstance(max_length, int) or not (1 <= max_length <= 4000):
            raise BotError(f"Field #{i + 1} must have a `max_length` between 1 and 4000.")

        if not isinstance(required, bool):
            raise BotError(f"Field #{i + 1} has an invalid `required` value. Must be `true` or `false`.")

        cleaned_fields.append({
            "label": compress_text(label),
            "placeholder": compress_text(placeholder),
            "style": style,
            "max_length": max_length,
            "required": required,
        })

    return {
        "title": compress_text(title),
        "fields": cleaned_fields
    }


# Parses a JSON form template and sends a preview embed showing what the modal will look like
async def preview_form_template(ctx, form_template_str: str):
    try:
        form_template = json.loads(form_template_str)
    except json.JSONDecodeError as e:
        raise BotError(f"❌ Invalid JSON. Error: `{e}`")

    try:
        cleaned = validate_and_clean_form_template(form_template)
    except BotError as e:
        raise BotError(f"❌ Invalid form structure.\n{e}")

    embed = discord.Embed(
        title=f"📝 Form Preview: {cleaned['title']}",
        color=discord.Color.green()
    )

    for idx, field in enumerate(cleaned["fields"], start=1):
        label = field["label"]
        placeholder = field["placeholder"]
        style = field["style"]
        max_len = field["max_length"]
        required = field["required"]

        field_text = (
            f"**Label:** {label}\n"
            f"**Placeholder:** {placeholder}\n"
            f"**Style:** {'Paragraph' if style == 'paragraph' else 'Short'}\n"
            f"**Max Length:** {max_len}\n"
            f"**Required:** {'✅ Yes' if required else '❌ No'}"
        )

        embed.add_field(name=f"Field #{idx}", value=field_text, inline=False)

    await ctx.send(embed=embed)



class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    # @commands.hybrid_command(name="help2", description="View information on the bot and its command list")
    # @checks.is_guild()
    # @checks.is_user()
    # async def help2(self, ctx):
    #     try:
    #         await ctx.send("help command here")

    #     except Exception as e:
    #         raise BotError(f"/help2 sent an error: {e}")
        

    @commands.command(name="setup_mailbee")
    @checks.is_admin()
    @checks.is_guild()
    async def setup_mailbee(self, ctx):
        try:
            guild = ctx.guild
            guildID = guild.id
            bot_member = ctx.guild.me  
            inbox_category = None
            log_channel = None
            responses_channel = None
            feedback_thread = None
            reports_thread = None

            # Check for any permitted roles (user or admin)
            roles = []
            permissions = await self.bot.data_manager.get_or_load_permissions(guildID)
            for roleID in permissions.keys():
                role = guild.get_role(roleID)
                roles.append(role)

            overwrites = await get_overwrites(guild, roles)
            
            setupEmbed = discord.Embed(title="Bot Setup", 
                                       description="Run this command to setup the bot. Setup includes creating "
                                       "the ticketing category, tickets log channel, and responses channel. If "
                                       "any of these categories or channels do not exist, the bot will create new "
                                       "ones. To re-create setup items, first delete the channel or category, then "
                                       "run this command.",
                                       color=discord.Color.green())
            setupEmbed.add_field(name="Setup Results", value="", inline=False)
            
            
            if not bot_member.guild_permissions.administrator:
                setupEmbed.add_field(name="", value="❌ Could not run setup. I need the administrator permission to configure "
                                    "myself properly.", inline=False)
                await ctx.send(embed=setupEmbed)
                return

            config = await self.bot.data_manager.get_or_load_config(guildID)
            if config is not None:
                pass
                # inboxID = config["inboxID"]
                # if inboxID:
                #     inbox_category = self.bot.get_channel(inboxID)
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
                #             category = await asyncio.wait_for(self.bot.fetch_channel(inboxID), timeout=1)
                #         except Exception:
                #             category = None
                # else:
                #     # NO INBOX --> create this
                # logID = config["logID"]
            
            # No config, create all items
            else:
                if (len(guild.categories) == 50):
                    setupEmbed.add_field(name="", value="❌ This server is not set up. I was unable to create the ticketing "
                                         "category as this server is at 50 total categories already.", inline=False)
                    await ctx.send(embed=setupEmbed)
                    return
                else:
                    # Create the inbox category
                    inbox_category = await guild.create_category(name="Tickets", 
                                                                overwrites=overwrites)
                    if inbox_category:
                        setupEmbed.add_field(name="", value="Created the ticketing category: **Tickets**", inline=False)
                    else:
                        setupEmbed.add_field(name="", value="❌ An error occurred on Discord's end. Please retry this command. No "
                                             "setup was completed.", inline=False)
                        await ctx.send(embed=setupEmbed)
                        return
                
                if (len(guild.text_channels) > 498):
                    setupEmbed.add_field(name="", value="❌ This server is not set up. I was unable to create the log or close "
                                         "responses channels as this server is at 499 or above total channels already.")
                    await ctx.send(embed=setupEmbed)
                    return
                else:
                    log_channel = await guild.create_text_channel(name="ticket-log", 
                                                               overwrites=overwrites,
                                                               category=inbox_category)
                    if log_channel:
                        setupEmbed.add_field(name="", value=f"Created the log channel: <#{log_channel.id}>", inline=False)
                    
                    responses_channel = await guild.create_text_channel(name="close-responses", 
                                                               overwrites=overwrites,
                                                               category=inbox_category)
                    if responses_channel:
                        setupEmbed.add_field(name="", value=f"Created the close responses channel: <#{responses_channel.id}>", inline=False)
                        feedback = await responses_channel.send("**Ticket Feedback**")
                        reports = await responses_channel.send("**Ticket Reports**")

                        # Create threads from each message
                        feedback_thread = await feedback.create_thread(
                            name="Ticket Feedback",
                            auto_archive_duration=10080)
                        setupEmbed.add_field(name="", value=f"Created the ticket feedback thread: <#{feedback_thread.id}>", inline=False)
                        
                        reports_thread = await reports.create_thread(
                            name="Ticket Reports",
                            auto_archive_duration=10080)
                        setupEmbed.add_field(name="", value=f"Created the ticket reports thread: <#{reports_thread.id}>", inline=False)
            
            await self.bot.data_manager.add_config_to_db(guildID, log_channel.id, inbox_category.id, 
                                                         responses_channel.id, feedback_thread.id, reports_thread.id)
            await ctx.send(embed=setupEmbed)
            
        except Exception as e:
            raise BotError(f"/setup2 sent an error: {e}")
        

    @app_commands.command(name="type_add", description="Add a new ticket type and create a corresponding tickets category")
    @checks.is_user_app()   
    @checks.is_setup()
    @checks.is_guild_app()
    @app_commands.describe(name="Type name")
    @app_commands.describe(description="Type description")
    @app_commands.describe(emoji="Emoji to show for select option")
    async def type_add(self, interaction: discord.Interaction, name: Range[str, 1, 45], description: Range[str, 1, 100], emoji: str = None):
        try:
            await interaction.response.defer()

            guild = interaction.guild
            response = discord.Embed(description=f"Added ticket type **{name}** and created a "
                                                  "corresponding category. \n\nRun `/set_form` to modify "
                                                  "the questions users are presented with when opening a "
                                                  "ticket for this type. The current form is viewable by "
                                                  "running `/preview_form`.",
                                                  color=discord.Color.green())

            # Config must exist due to checks passing
            config = await self.bot.data_manager.get_or_load_config(guild.id)

            inbox_category = guild.get_channel(config["inboxID"])

            if inbox_category:
                if (isinstance(inbox_category, discord.CategoryChannel)):
                    # Define permission overwrites
                    # Check for any permitted roles (user or admin)
                    roles = []
                    permissions = await self.bot.data_manager.get_or_load_permissions(guild.id)
                    for roleID in permissions.keys():
                        role = guild.get_role(roleID)
                        roles.append(role)

                    overwrites = await get_overwrites(guild, roles)

                    # Create the new category
                    new_category = await guild.create_category(name=name, 
                                                               overwrites=overwrites,
                                                               position=(inbox_category.position + 1))

                    if new_category:
                        await self.bot.data_manager.add_type_to_db(guild.id, new_category.id, name, description, emoji)
                        await self.bot.data_manager.get_or_load_guild_types(guild.id, False)

                    else:
                        response.description=("❌ Failed to create new category. Please ensure "
                                            "bot has **administrator permissions** and this server "
                                            "is not at the maximum channel limit.")
                        response.color=discord.Color.red()
                        
                else:
                    pass
            else:
                response.description=("❌ Could not find valid inbox category. Please "
                                      "run `/setup` to create a new inbox category.")
                response.color=discord.Color.red()
            
            await interaction.followup.send(embed=response)

        except Exception as e:
            logger.exception(f"add_type error: {e}")
            raise BotError(f"/add_type sent an error: {e}")
        

    @commands.command(name="type_remove", description="Remove a tickets category type, deleting the category")
    @checks.is_user()
    @checks.is_guild()
    async def type_remove(self, ctx, category: discord.CategoryChannel):
        try:
            name = category.name
            await self.bot.data_manager.delete_guild_type(ctx.guild.id, category.id)
            await category.delete(reason="Deleted ticket type")

            responseEmbed = discord.Embed(title="", description=f"✅ Removed tickets type for {name}")

            await ctx.send(embed=responseEmbed)
            
        except Exception as e:
            raise BotError(f"/remove_type sent an error: {e}")


    @commands.hybrid_command(name="form_set", description="Change the form used by a ticket type")
    @checks.is_user()
    @checks.is_guild()
    @app_commands.describe(category="Tickets category to edit the form for")
    @app_commands.describe(form_template="Template for the form, use /form_template to view a pre-made template")
    async def form_set(self, ctx, category: discord.CategoryChannel, form_template: str):
        try:
            try:
                parsed_form = json.loads(form_template)
            except json.JSONDecodeError as decode_err:
                raise BotError(f"❌ Invalid form template. Please ensure it is valid JSON.\n\nError: `{decode_err}`")

            cleaned_form = validate_and_clean_form_template(parsed_form)
            await self.bot.data_manager.set_form(ctx.guild.id, category.id, cleaned_form)
            await self.bot.data_manager.get_or_load_guild_types(ctx.guild.id, False)

            responseEmbed = discord.Embed(
                description=f"✅ Updated form for ticket type `{category.name}`"
            )
            await ctx.send(embed=responseEmbed)

        except Exception as e:
            logger.exception(f"set_form error: {e}")
            raise BotError(f"/set_form sent an error: {e}")
        

    @commands.hybrid_command(name="form_preview", description="Preview how a form template will look")
    @checks.is_user()
    @checks.is_guild()
    @app_commands.describe(form_template="Form template JSON string")
    async def form_preview(self, ctx, form_template: str):
        await preview_form_template(ctx, form_template)
 

    @commands.command(name="greeting")
    @checks.is_user()
    @checks.is_guild()
    async def greeting(self, ctx, *, greeting: str):
        try:
            guild = ctx.guild

            moderation = self.bot.get_cog("Moderation")
            if moderation is not None:
                greeting = await self.bot.helper.convert_mentions(greeting, guild)

            if len(greeting) > 4000:
                errorEmbed = discord.Embed(description="❌ Greeting text is too long, must be at most 4000 characters", 
                                           color=discord.Color.red())
                await ctx.send(embed=errorEmbed)
                return
            
            await self.bot.data_manager.set_greeting(guild.id, greeting)
            await self.bot.data_manager.get_or_load_config(guild.id, False)

            successEmbed = discord.Embed(description=f"✅ **Greeting set:**\n{greeting}",
                                         color=discord.Color.green())
            await ctx.send(embed=successEmbed)

        except Exception as e:
            logger.exception(f"/greeting error: {e}")
            raise BotError(f"/greeting sent an error: {e}")
        

    @commands.command(name="closing")
    @checks.is_user()
    @checks.is_guild()
    async def closing(self, ctx, *, closing: str):
        try:
            guild = ctx.guild

            moderation = self.bot.get_cog("Moderation")
            if moderation is not None:
                closing = await self.bot.helper.convert_mentions(closing, guild)

            if len(closing) > 4000:
                errorEmbed = discord.Embed(description="❌ Closing text is too long, must be at most 4000 characters", 
                                           color=discord.Color.red())
                await ctx.send(embed=errorEmbed)
                return
            
            await self.bot.data_manager.set_closing(guild.id, closing)
            await self.bot.data_manager.get_or_load_config(guild.id, False)

            successEmbed = discord.Embed(description=f"✅ **Closing set:**\n{closing}",
                                         color=discord.Color.green())
            await ctx.send(embed=successEmbed)

        except Exception as e:
            logger.exception(f"/closing error: {e}")
            raise BotError(f"/closing sent an error: {e}")
        

    @commands.command(name="accepting")
    @checks.is_user()
    @checks.is_guild()
    async def accepting(self, ctx, *, accepting: str = ("The server you are attempting to contact is not "
                                                       "currently accepting new tickets. Please try again "
                                                       "later.")):
        try:
            guild = ctx.guild

            moderation = self.bot.get_cog("Moderation")
            if moderation is not None:
                accepting = await self.bot.helper.convert_mentions(accepting, guild)

            if len(accepting) > 2000:
                errorEmbed = discord.Embed(description="❌ Accepting text is too long, must be at most 2000 characters", 
                                           color=discord.Color.red())
                await ctx.send(embed=errorEmbed)
                return
            
            successEmbed = discord.Embed(description="", color=discord.Color.green())
        
            config = await self.bot.data_manager.get_or_load_config(guild.id)
            if config["accepting"] == "true":
                successEmbed.description=f"✅ Ticket creation disabled with message:\n{accepting}"
                await self.bot.data_manager.set_ticket_accepting(guild.id, accepting)
                await ctx.send(embed=successEmbed)
            else:
                successEmbed.description="✅ Ticket creation enabled"
                await self.bot.data_manager.set_ticket_accepting(guild.id, "true")
                await ctx.send(embed=successEmbed)

            await self.bot.data_manager.get_or_load_config(guild.id, False)

        except Exception as e:
            logger.exception(f"/accepting error: {e}")
            raise BotError(f"/accepting sent an error: {e}")


    @app_commands.command(name="set_type", description="Set the type of a tickets category")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(category="Tickets category to set a type for")
    @app_commands.describe(type="Select a type, or search by keyword")
    async def set_type(self, interaction: discord.Interaction, category: discord.CategoryChannel, type: str):
        try:
            guild = interaction.guild
            types = [
                f"{typeID}: {name}" for typeID, name
                in self.bot.data_manager.types]
            
            typeEmbed = discord.Embed(title="", 
                                      description=f"Set **{category.name}** as type **{type}**", 
                                      color=0x3ad407)

            if type not in types:
                typeEmbed.description=f"❌ Type **{type}** not found"
                typeEmbed.color=0xFF0000
                await interaction.response.send_message(embed=typeEmbed)
                return
            
            typeID = int(type[:(type.index(":"))])

            search_monitor = [
                (channelID) for guildID, channelID, monitorType 
                in self.bot.data_manager.monitored_channels
                if (channelID == category.id)]
            
            if (len(search_monitor) == 0):
                typeEmbed.description=f"❌ Category is not a tickets category"
                typeEmbed.color=0xFF0000
                await interaction.response.send_message(embed=typeEmbed)
                return
            
            await self.bot.data_manager.set_type(guild.id, category.id, typeID)
            await interaction.response.send_message(embed=typeEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/set_type sent an error: {e}")


    @set_type.autocomplete('type')
    async def type_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        if not guild:
            return []
        
        types = [
            f"{typeID}: {name}" for typeID, name
            in self.bot.data_manager.types
            ]

        matches = [
            app_commands.Choice(name=type, value=type)
            for type in types
            if current.lower() in type.lower()]
        
        return matches[:25]


    # @commands.hybrid_command(name="reset_form", description="View information on the bot and its command list")
    # @checks.is_guild()
    # @checks.is_user()
    # async def reset_form(self, ctx):
    #     try:
    #         await ctx.send("help command here")
            
    #     except Exception as e:
    #         raise BotError(f"/help2 sent an error: {e}")
        

    # @commands.hybrid_command(name="preview_form", description="View information on the bot and its command list")
    # @checks.is_guild()
    # @checks.is_user()
    # async def preview_form(self, ctx):
    #     try:
    #         await ctx.send("help command here")
            
    #     except Exception as e:
    #         raise BotError(f"/help2 sent an error: {e}")
        

    # @commands.hybrid_command(name="form_template", description="View information on the bot and its command list")
    # @checks.is_guild()
    # @checks.is_user()
    # async def form_template(self, ctx):
    #     try:
    #         await ctx.send("help command here")
            
    #     except Exception as e:
    #         raise BotError(f"/help2 sent an error: {e}")


    # Send embed of help guide + server commands
    @commands.command(name="help")
    @checks.is_user()
    @checks.is_guild()
    async def help(self, ctx):
        try:
            pages = []
            bot_user = self.bot.user
            helpEmbed = discord.Embed(title=f"Mantid Help Menu", 
                                            description=f"Mantid is a complimentary analytics bot to Modmail with the long-term"
                                            " goal of replicating and enhancing Modmail's functionality. Use the buttons below"
                                            " to navigate through Mantid's help pages.\n\nTo setup Mantid, run `/setup`"
                                            " \n\n**Flip to the next page to begin viewing Mantid's command list**"
                                            " \n\n**TIP:** Use `/edit_monitor`to add additional Modmail ticket categories" 
                                            " for the bot to monitor. Ticket categories generated by Mantid are automatically" 
                                            " added (and removed) from the monitor."
                                            " \n\n**Contact <@429711831695753237> for support & suggestions**", 
                                            color=0x3ad407)
            helpEmbed.set_thumbnail(url=bot_user.avatar.url)
            pages.append(helpEmbed)

            # Populate embed pages
            for cog_name in self.bot.cogs:
                if cog_name in ["Admin", "Util", "Analytics"]:
                    continue

                cog = self.bot.get_cog(cog_name)
                cog_commands = cog.get_commands()
                if len(cog_commands) == 0:
                    continue

                page = discord.Embed(title=f"{cog_name} Commands",
                                    description="",
                                    color=0x3ad407)
                page.set_author(name=f"Mantid Help Menu")
                page.set_thumbnail(url=bot_user.avatar.url)

                for command in cog_commands:
                    page.add_field(name=f"**`/{command.name}`**", 
                                    value=f"{emojis.mantis} {command.description}", 
                                    inline=False)
                pages.append(page)

            for page in range(len(pages)):
                pages[page].set_footer(text=f"Use the buttons below to navigate (Page {page + 1}/{len(pages)})")

            # Create an instance of the pagination view
            view = Paginator(pages)
            view.message = await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            raise BotError(f"/help sent an error: {e}")


    # Send setup steps and attempt to automatically configure channel monitor
    @commands.command(name="setup")
    @checks.is_admin()
    @checks.is_guild()
    async def setup(self, ctx):
        try:
            guild = ctx.guild
            
            setupEmbed = Embeds(self.bot, title=f"Bot Setup", 
                                description="Run this command to setup or refresh Mantid's monitored channels\n\n"
                                            "To properly record data on Modmail, Mantid requires channel monitors"
                                            " for the **modmail-log** channel and any categories used to store Modmail" 
                                            " tickets. Channel monitors are set automatically upon running the"
                                            " command `/setup` or when Mantid generates a category to handle ticket"
                                            " overflow.\n\n- Use the `/edit_monitor` command and select **add** to"
                                            " assign Mantid additional ticket categories to monitor after setup\n"
                                            "- View current monitored channels and categories with `/show`, then select"
                                            " **monitored channels**\n- If Mantid incorrectly adds or is missing a"
                                            " channel in the monitor, use `/edit_monitor` with **add** or **remove**"
                                            f" as needed\n\n**Confirm correct setup by identifying a {emojis.mantis}"
                                            " reaction underneath all new entries in your server's modmail-log."
                                            " If this reaction fails to appear, run `/setup` again or contact"
                                            " <@429711831695753237>.\n\n**")
            setupEmbed.add_field(name="Setup Output:", value=f"", inline=False)

            for channel in guild.channels:
                if (isinstance(channel, discord.DMChannel)):
                    pass
                 
                if (isinstance(channel, discord.TextChannel)):
                    if (channel.name == "modmail-log"):
                        search_monitor = [
                            (channelID) for guildID, channelID, monitorType 
                            in self.bot.data_manager.monitored_channels if channelID == channel.id]
                        if (len(search_monitor) != 0):
                            pass
                            # setupEmbed.add_field(name="", 
                            #                     value=f"{emojis.mantis} <#{channel.id}> is already set as this server's **Modmail log**", 
                            #                     inline=False)
                        else:
                            await self.bot.data_manager.add_monitor(guild.id, channel.id, "Modmail log")
                            setupEmbed.add_field(name="", 
                                                value=f"{emojis.mantis} Set <#{channel.id}> as this server's **Modmail log**", 
                                                inline=False)
                            
                    elif ((channel.name)[-2:] == "-0"):
                        this_category = channel.category
                        if ((this_category.name).casefold() == "modmail"):
                            pass
                        else:
                            search_monitor = [
                                (channelID) for guildID, channelID, monitorType 
                                in self.bot.data_manager.monitored_channels if channelID == this_category.id]
                            if (len(search_monitor) != 0):
                                pass
                                # setupEmbed.add_field(name="", 
                                #                     value=f"{emojis.mantis} **<#{this_category.id}>** is already set as a **Tickets Category**", 
                                #                     inline=False)
                            else:
                                await self.bot.data_manager.add_monitor(guild.id, this_category.id, "Tickets category")
                                setupEmbed.add_field(name="", 
                                                    value=f"{emojis.mantis} Set **<#{this_category.id}>** as a **Tickets Category**", 
                                                    inline=False)

                if (isinstance(channel, discord.CategoryChannel)):
                    if ("modmail" in (channel.name).casefold()):
                        search_monitor = [
                            (channelID) for guildID, channelID, monitorType 
                            in self.bot.data_manager.monitored_channels if channelID == channel.id]
                        if (len(search_monitor) != 0):
                            pass
                            # setupEmbed.add_field(name="", 
                            #                     value=f"{emojis.mantis} **<#{channel.id}>** is already set as a **Tickets Category**", 
                            #                     inline=False)
                        else:
                            await self.bot.data_manager.add_monitor(guild.id, channel.id, "Tickets category")
                            setupEmbed.add_field(name="", 
                                                value=f"{emojis.mantis} Set **<#{channel.id}>** as a **Tickets Category**", 
                                                inline=False)
            await ctx.send(embed=setupEmbed)

        except Exception as e:
            raise BotError(f"/setup sent an error: {e}")


    # Show roles with the 'Bot Admin' permission or all monitored channels / categories
    @commands.hybrid_command(name="show", description="List this server's role permissions or monitored channels and categories")
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(selection="Select to show either server role permissions or monitored channels")
    @app_commands.choices(selection=[
        app_commands.Choice(name="role permissions", value="role permissions"),
        app_commands.Choice(name="monitored channels", value="monitored channels")])
    async def show(self, ctx, selection: discord.app_commands.Choice[str]):
        try:
            choice = selection.value
            this_guildID = ctx.guild.id
            guildName = (self.bot.get_guild(this_guildID)).name

            if (choice == "role permissions"):
                search_access = [
                    (roleID, permLevel) for guildID, roleID, permLevel 
                    in self.bot.data_manager.access_roles if guildID == this_guildID]
                permsEmbed = Embeds(self.bot, title=f"Server Role Permissions", 
                                    description=f"Roles with access to Mantid in: **{guildName}** ({this_guildID})")
    
                if (len(search_access) == 0):
                    permsEmbed.description=""
                    permsEmbed.color=0xFF0000
                    permsEmbed.add_field(name="", 
                                        value="No permissions set, run **/edit permissions** to add one", 
                                        inline=False)
                else:
                    for row in search_access:
                        permsEmbed.add_field(name="", 
                                            value=f"{emojis.mantis} <@&{row[0]}> - **{row[1]}**", 
                                            inline=False)
                
                await ctx.send(embed=permsEmbed)
            
            if (choice == "monitored channels"):
                search_monitor = [
                    (channelID, monitorType) for guildID, channelID, monitorType 
                    in self.bot.data_manager.monitored_channels if guildID == this_guildID]
                monitorEmbed = Embeds(self.bot, title=f"Server Monitored Channels", 
                                        description=f"Channels monitored in: **{guildName}** ({this_guildID})")
                
                if (len(search_monitor) == 0):
                    monitorEmbed.description=""
                    monitorEmbed.color=0xFF0000
                    monitorEmbed.add_field(name="", 
                                        value="No channels set, run **/edit monitor** to add one", 
                                        inline=False)
                else:
                    for row in search_monitor:
                        monitorEmbed.add_field(name="", 
                                            value=f"{emojis.mantis} <#{row[0]}> - **{row[1]}**", 
                                            inline=False)
                
                await ctx.send(embed=monitorEmbed)

        except Exception as e:
            raise BotError(f"/show sent an error: {e}")


    # Edit roles with the 'Bot Admin' permission
    @commands.hybrid_command(name="edit_permissions", description="Add or remove roles that can use Mantid in this server")
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(action="Desired edit action. Use 'add' to grant permissions and 'remove' to delete them")
    @app_commands.choices(action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove")])
    @app_commands.describe(role="Selected role")
    @app_commands.describe(level="Permission level. Bot users can only use moderation-specific commands")
    @app_commands.choices(level=[
        app_commands.Choice(name="Bot User", value="user"),
        app_commands.Choice(name="Bot Admin", value="admin")])
    async def edit_permissions(self, ctx, 
                               action: discord.app_commands.Choice[str], 
                               role: discord.Role, 
                               level: discord.app_commands.Choice[str]):
        try:
            this_guildID = ctx.guild.id
            choice = action.value
            level_name = level.name
            level_value = level.value
            this_roleID = role.id

            editEmbed = Embeds(self.bot, title=f"Edit Results", description="")

            # Check if access is already given, if not add it
            if (choice == "add"):
                search_access = [
                    (roleID, permLevel) for guildID, roleID, permLevel 
                    in self.bot.data_manager.access_roles if (roleID == this_roleID)]
                if (len(search_access) != 0):
                    perm = search_access[0][1]
                    if (perm == level_name):
                        editEmbed.description=f"Unable to add permissions, <@&{this_roleID}> already has **{perm}**"
                        editEmbed.color=0xFF0000
                    else:
                        query = f"""
                        UPDATE permissions 
                        SET permissions.permLevel = '{level_name}'
                        WHERE (permissions.roleID = {this_roleID});
                        """
                        await self.bot.data_manager.execute_query(query, False)
                        await self.bot.data_manager.update_cache(0)
                        await self.bot.data_manager.get_or_load_permissions(this_guildID, False)
                        editEmbed.description=f"Updated permissions to **{level_name}** for <@&{this_roleID}>"
                else:
                    query = f"""
                        INSERT INTO permissions VALUES 
                        ({this_guildID}, 
                        {this_roleID}, 
                        '{level_name}');
                        """
                    await self.bot.data_manager.execute_query(query, False)
                    await self.bot.data_manager.update_cache(0)
                    await self.bot.data_manager.get_or_load_permissions(this_guildID, False)
                    editEmbed.description=f"Added **{level_name}** permissions to <@&{this_roleID}>"

            # Check if user has access, if not do nothing
            if (choice == "remove"):
                search_access = [
                    (roleID, permLevel) for guildID, roleID, permLevel 
                    in self.bot.data_manager.access_roles if (roleID == this_roleID)]
                if (len(search_access) != 0):
                    perm = search_access[0][1]
                    if (perm == level_name):
                        query = f"""
                            DELETE FROM permissions WHERE 
                            (permissions.roleID = {this_roleID});
                            """
                        await self.bot.data_manager.execute_query(query, False)
                        await self.bot.data_manager.update_cache(0)
                        await self.bot.data_manager.get_or_load_permissions(this_guildID, False)
                        editEmbed.description=f"Removed **{level_name}** permissions from <@&{this_roleID}>"
                else:
                    editEmbed.description=f"Unable to remove permissions, <@&{this_roleID}> does not have this permission"
                    editEmbed.color=0xFF0000

            await ctx.send(embed=editEmbed)

        except Exception as e:
            raise BotError(f"/edit_permissions sent an error: {e}")


    # Edit monitored channels / categories
    @commands.hybrid_command(name="edit_monitor", description="Add or remove monitored modmail-log"
                                                              " channels and tickets categories in this server")
    @checks.is_admin()
    @checks.is_guild()
    @app_commands.describe(action="Desired edit action. Use 'add' to add channels / categories and 'remove' to remove them")
    @app_commands.choices(action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove")])
    @app_commands.describe(channel="Modmail channel")
    @app_commands.describe(category="Tickets category")
    async def edit_monitor(self, ctx, action: discord.app_commands.Choice[str], 
                           channel: discord.TextChannel = None, 
                           category: discord.CategoryChannel = None):
        try:
            this_guildID = ctx.guild.id
            choice = action.value
            this_channelID = None
            this_categoryID = None

            if channel is None and category is None:
                errorEmbed = discord.Embed(self.bot, title=f"", 
                                    description="❌ You must provide at least a channel or category", 
                                    color=0xFF0000)

                await ctx.send(embed=errorEmbed, ephemeral=True)
                return

            if channel is not None:
                this_channelID = channel.id
            if category is not None:
                this_categoryID = category.id

            editEmbed = Embeds(self.bot, title=f"Edit Results", description="")

            # check if channel / category is already added or not
            if (choice == "add"):
                if (this_channelID is not None):
                    search_monitor = [
                        (channelID) for guildID, channelID, monitorType 
                        in self.bot.data_manager.monitored_channels 
                        if (guildID == this_guildID and monitorType == "Modmail log")]
                    
                    if (len(search_monitor) != 0):
                        if (search_monitor[0] == this_channelID):
                            editEmbed.description=f"Unable to add channel, <#{this_channelID}> is already set as **Modmail log**"
                            editEmbed.color=0xFF0000
                        elif (search_monitor[0] != this_channelID):
                            editEmbed.description=(f"Unable to add channel, <#{search_monitor[0]}> is already set as this server's"
                                                " **Modmail log** \n\n(run `/edit_monitor remove channel` to remove this set"
                                                " channel before attempting to add a new one)")
                            editEmbed.color=0xFF0000
                    else:
                        await self.bot.data_manager.add_monitor(this_guildID, this_channelID, "Modmail log")
                        editEmbed.description=f"Set <#{this_channelID}> as **Modmail log** channel"
                    await ctx.send(embed=editEmbed)

                if (this_categoryID is not None):
                    search_monitor = [
                        (channelID, monitorType) for guildID, channelID, monitorType 
                        in self.bot.data_manager.monitored_channels 
                        if (channelID == this_categoryID)]
                    
                    if (len(search_monitor) != 0):
                        editEmbed.description=f"Unable to add category, **<#{this_categoryID}>** is already set as a **{search_monitor[0][1]}**"
                        editEmbed.color=0xFF0000
                    else:
                        await self.bot.data_manager.add_monitor(this_guildID, this_categoryID, "Tickets category")
                        editEmbed.description=f"Set **<#{this_categoryID}>** as a **Tickets category**"
                    await ctx.send(embed=editEmbed)

            # Check if channel / category is already removed or not
            if (choice == "remove"):
                if (this_channelID is not None):
                    search_monitor = [
                        (channelID) for guildID, channelID, monitorType 
                        in self.bot.data_manager.monitored_channels 
                        if (channelID == this_channelID and monitorType == "Modmail log")]
                    
                    if (len(search_monitor) != 0):
                        await self.bot.data_manager.remove_monitor(this_channelID)
                        editEmbed.description=f"Removed **Modmail log** status from <#{this_channelID}>"
                    else:
                        editEmbed.description=f"Unable to remove channel, <#{this_channelID}> is not a **Modmail log** channel"
                        editEmbed.color=0xFF0000
                    await ctx.send(embed=editEmbed)

                if (this_categoryID is not None):
                    search_monitor = [
                        (channelID, monitorType) for guildID, channelID, monitorType 
                        in self.bot.data_manager.monitored_channels 
                        if (channelID == this_categoryID)]
                    
                    if (len(search_monitor) != 0):
                        if (search_monitor[0][1] == "Tickets category"):
                            await self.bot.data_manager.remove_monitor(this_categoryID)
                            editEmbed.description=f"Removed **Tickets category** status from **<#{this_categoryID}>**"
                        else:
                            editEmbed.description=(f"Removed **Overflow category** status from **<#{this_categoryID}>**\n\n"
                                                   "**Remove the word 'Overflow' from this category's name if it is not being deleted**")
                    else:
                        editEmbed.description=f"Unable to remove category, **<#{this_categoryID}>** is not a **Tickets category**"
                        editEmbed.color=0xFF0000
                    await ctx.send(embed=editEmbed)

        except Exception as e:
            raise BotError(f"/edit_monitor sent an error: {e}")


async def setup(bot):
    await bot.add_cog(Config(bot))