import discord
from discord.ext import commands
from discord import app_commands
from classes.error_handler import *
from utils import emojis, checks
from utils.logger import *


class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.hybrid_command(name="show", description="List server role permissions or monitored channels")
    @checks.has_access()
    @app_commands.describe(selection="Select list to show (server role permissions or monitored channels)")
    @app_commands.choices(selection=[
        app_commands.Choice(name="role permissions", value="role permissions"),
        app_commands.Choice(name="monitored channels", value="monitored channels")])
    async def show(self, ctx, selection: discord.app_commands.Choice[str]):
        try:
            choice = selection.value
            this_guildID = ctx.guild.id
            guildName = (self.bot.get_guild(this_guildID)).name
            if (choice == "role permissions"):
                # ERROR TRIGGER
                val = search_access[20]
                search_access = [
                    (roleID, permLevel) for guildID, roleID, permLevel 
                    in self.bot.data_manager.access_roles if guildID == this_guildID]
                permsEmbed = discord.Embed(title=f"Server Role Permissions {emojis.mantis} ", 
                                        description=f"Roles with access to Mantid in: **{guildName}** ({this_guildID})", 
                                        color=0x3ad407)
                
                if not search_access:
                    permsEmbed.description=""
                    permsEmbed.color=0xFF0000
                    permsEmbed.add_field(name="", 
                                        value="No permissions set, run **/edit permissions** to add one", 
                                        inline=False)
                else:
                    for row in search_access:
                        permsEmbed.add_field(name="", 
                                            value=f"<@&{row[0]}> - **{row[1]}**", 
                                            inline=False)
                await ctx.send(embed=permsEmbed)
            
            if (choice == "monitored channels"):
                search_monitor = [
                    (channelID, monitorType) for guildID, channelID, monitorType 
                    in self.bot.data_manager.monitored_channels if guildID == this_guildID]
                monitorEmbed = discord.Embed(title=f"Server Monitored Channels {emojis.mantis} ", 
                                            description=f"Channels monitored in: **{guildName}** ({this_guildID})", 
                                            color=0x3ad407)
                
                if not search_monitor:
                    monitorEmbed.description=""
                    monitorEmbed.color=0xFF0000
                    monitorEmbed.add_field(name="", 
                                        value="No channels set, run **/edit monitor** to add one", 
                                        inline=False)
                else:
                    for row in search_monitor:
                        monitorEmbed.add_field(name="", 
                                            value=f"<#{row[0]}> - **{row[1]}**", 
                                            inline=False)
                await ctx.send(embed=monitorEmbed)
        except Exception as e:
                raise BotError(f"/show sent an error: {e}")


    @commands.hybrid_group()
    async def edit(self, ctx):
        pass


    @edit.command(name="permissions", description="Edit roles that can access the bot")
    @checks.has_access()
    @app_commands.describe(action="Desired edit action. Use 'add' to grant permissions and 'remove' to delete them")
    @app_commands.choices(action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove")])
    @app_commands.describe(role="Selected role")
    async def permissions(self, ctx, action: discord.app_commands.Choice[str], role: discord.Role):
        this_guildID = ctx.guild.id
        choice = action.value
        this_roleID = role.id
        editEmbed = discord.Embed(title=f"Edit Results {emojis.mantis}", 
                                  description="", 
                                  color=0x3ad407)

        # check if access is already given, if not add it
        if (choice == "add"):
            search_access = [
                (roleID, permLevel) for guildID, roleID, permLevel 
                in self.bot.data_manager.access_roles if (roleID == this_roleID)]
            if (search_access):
                perm = search_access[0][1]
                editEmbed.description=f"Unable to add permissions, <@&{this_roleID}> already has **{perm}**"
                editEmbed.color=0xFF0000
            else:
                query = f"""
                    INSERT INTO permissions VALUES 
                    ({this_guildID}, 
                    {this_roleID}, 
                    'Bot Admin');
                    """
                await self.bot.data_manager.execute_query(query, False)
                await self.bot.data_manager.update_cache(0)
                editEmbed.description=f"Added **Bot Admin** permissions to <@&{this_roleID}>"

        # check if user has access, if not do nothing
        if (choice == "remove"):
            search_access = [
                roleID for guildID, roleID, permLevel 
                in self.bot.data_manager.access_roles if (roleID == this_roleID)]
            if (search_access):
                query = f"""
                    DELETE FROM permissions WHERE 
                    (permissions.roleID = {this_roleID});
                    """
                await self.bot.data_manager.execute_query(query, False)
                await self.bot.data_manager.update_cache(0)
                editEmbed.description=f"Removed **Bot Admin** permissions from <@&{this_roleID}>"
            else:
                editEmbed.description=f"Unable to remove permissions, <@&{this_roleID}> does not have access"
                editEmbed.color=0xFF0000
        await ctx.send(embed=editEmbed)


    @edit.command(name="monitor", description="Edit monitored channels and categories")
    @checks.has_access()
    @app_commands.describe(action="Desired edit action. Use 'add' to add channels / categories and 'remove' to remove them")
    @app_commands.choices(action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove")])
    @app_commands.describe(channel="Modmail channel")
    @app_commands.describe(category="Tickets category")
    async def monitor(self, ctx, action: discord.app_commands.Choice[str], channel: discord.TextChannel = None, category: discord.CategoryChannel = None):

        if channel is None and category is None:
            errorEmbed = discord.Embed(title=f"", 
                                       description="❌ You must provide at least a channel or category", 
                                       color=0xFF0000)
            await ctx.send(embed=errorEmbed, ephemeral=True)
            return
        
        this_guildID = ctx.guild.id
        choice = action.value
        this_channelID = None
        this_categoryID = None

        if channel is not None:
            this_channelID = channel.id
        if category is not None:
            this_categoryID = category.id
        editEmbed = discord.Embed(title=f"Edit Results {emojis.mantis}", 
                                  description="", 
                                  color=0x3ad407)

        # check if channel / category is already added or not
        if (choice == "add"):
            if (this_channelID is not None):
                search_monitor = [
                    (channelID) for guildID, channelID, monitorType 
                    in self.bot.data_manager.monitored_channels if (guildID == this_guildID and monitorType == "Modmail log")]
                if (search_monitor):
                    if (search_monitor[0] == this_channelID):
                        editEmbed.description=f"Unable to add channel, <#{this_channelID}> is already set as **Modmail log**"
                        editEmbed.color=0xFF0000
                    elif (search_monitor[0] != this_channelID):
                        editEmbed.description=f"Unable to add channel, <#{search_monitor[0]}> is already set as this server's **Modmail log** \n\n(run **/edit monitor remove channel** to remove this set channel before attempting to add a new one)"
                        editEmbed.color=0xFF0000
                else:
                    query = f"""
                        INSERT INTO channel_monitor VALUES 
                        ({this_guildID}, 
                        {this_channelID}, 
                        'Modmail log');
                        """
                    await self.bot.data_manager.execute_query(query, False)
                    await self.bot.data_manager.update_cache(1)
                    editEmbed.description=f"Set <#{this_channelID}> as **Modmail log** channel"
                await ctx.send(embed=editEmbed)

            if (this_categoryID is not None):
                search_monitor = [
                    (channelID) for guildID, channelID, monitorType 
                    in self.bot.data_manager.monitored_channels if (channelID == this_categoryID and monitorType == "Tickets category")]
                if (search_monitor):
                    editEmbed.description=f"Unable to add category, <#{this_categoryID}> is already set as a **Tickets category**"
                    editEmbed.color=0xFF0000
                else:
                    query = f"""
                        INSERT INTO channel_monitor VALUES 
                        ({this_guildID}, 
                        {this_categoryID}, 
                        'Tickets category');
                        """
                    await self.bot.data_manager.execute_query(query, False)
                    await self.bot.data_manager.update_cache(1)
                    editEmbed.description=f"Set <#{this_categoryID}> as a **Tickets category**"
                await ctx.send(embed=editEmbed)

        # check if channel / category is already removed or not
        if (choice == "remove"):
            if (this_channelID is not None):
                search_monitor = [
                    (channelID) for guildID, channelID, monitorType 
                    in self.bot.data_manager.monitored_channels if (channelID == this_channelID and monitorType == "Modmail log")]
                if (search_monitor):
                    query = f"""
                        DELETE FROM channel_monitor WHERE 
                        ((channel_monitor.channelID = {this_channelID}) AND 
                        (channel_monitor.monitorType = 'Modmail log'));
                        """
                    await self.bot.data_manager.execute_query(query, False)
                    await self.bot.data_manager.update_cache(1)
                    editEmbed.description=f"Removed **Modmail log** status from <#{this_channelID}>"
                else:
                    editEmbed.description=f"Unable to remove channel, <#{this_channelID}> is not a **Modmail log** channel"
                    editEmbed.color=0xFF0000
                await ctx.send(embed=editEmbed)

            if (this_categoryID is not None):
                search_monitor = [
                    (channelID) for guildID, channelID, monitorType 
                    in self.bot.data_manager.monitored_channels if (channelID == this_categoryID and monitorType == "Tickets category")]
                if (search_monitor):
                    query = f"""
                        DELETE FROM channel_monitor WHERE 
                        ((channel_monitor.channelID = {this_categoryID}) AND 
                        (channel_monitor.monitorType = 'Tickets category'));
                        """
                    await self.bot.data_manager.execute_query(query, False)
                    await self.bot.data_manager.update_cache(1)
                    editEmbed.description=f"Removed **Tickets category** status from <#{this_categoryID}>"
                else:
                    editEmbed.description=f"Unable to remove category, <#{this_categoryID}> is not a **Tickets category**"
                    editEmbed.color=0xFF0000
                await ctx.send(embed=editEmbed)


    # @show.error
    # async def show_error(self, ctx, error):
    #     if isinstance(error, commands.NotOwner):
    #         logger.info(f"Denied '/show' permissions for {ctx.message.author.name}")
    #         errorEmbed = discord.Embed(title=f"", 
    #                                    description="❌ You do not have permission to use this command", 
    #                                    color=0xFF0000)
    #     else:
    #         errorEmbed.description="❌ An error occurred, please try again later"
    #         logger.exception(f"'/show' sent an error: {error}")
    #     await ctx.send(embed=errorEmbed, ephemeral=True)


    # @edit.error
    # async def edit_error(self, ctx, error):
    #     if isinstance(error, commands.NotOwner):
    #         logger.info(f"Denied '/edit' permissions for {ctx.message.author.name}")
    #         errorEmbed = discord.Embed(title=f"", 
    #                                    description="❌ You do not have permission to use this command", 
    #                                    color=0xFF0000)
    #     else:
    #         errorEmbed.description="❌ An error occurred, please try again later"
    #         logger.exception(f"'/edit' sent an error: {error}")
    #     await ctx.send(embed=errorEmbed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Config(bot))