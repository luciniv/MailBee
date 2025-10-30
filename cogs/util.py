import os
import subprocess
import tempfile

import discord
from discord.ext import commands
from discord import PartialEmoji, SelectOption

from classes.error_handler import *
from classes.embeds import Embeds
from utils import checks, emojis
from utils.logger import *

SERVER_TO_GAME = {
    714722808009064492: ("Creatures of Sonaria", 1831550657, os.getenv("COS_KEY")),
    346515443869286410: ("Dragon Adventures", 1235188606, os.getenv("DA_KEY")),
    1196293227976863806: ("Horse Life", 5422546686, os.getenv("HL_KEY")),
}


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

    async def callback(self, interaction: discord.Interaction):
        print("hooray")

    @classmethod
    async def create(cls, bot, guild_id, dm_channel_id, types, parent_category_id=None):
        try:
            print("creating category select...")

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

            print("created options:", options)

            return cls(bot, guild_id, dm_channel_id, types, options, parent_category_id)
        except Exception as e:
            logger.exception(e)


class CategorySelectView(discord.ui.View):
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


class Util(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @checks.is_owner()
    async def category_embed(self, ctx):
        guild = ctx.guild
        guild_id = ctx.guild.id
        dm_channel = await ctx.author.create_dm()
        types = await self.bot.data_manager.get_or_load_guild_types(guild_id)

        embed = Embeds.info(
            title="Select Ticket Type",
            description="Please select a type for your ticket with the "
            "drop-down menu below.\n\nIf you're unsure what to choose, or "
            'your topic isn\'t listed, select "Other."',
        )
        if guild.icon:
            embed.set_author(name=guild.name, icon_url=guild.icon.url)
            embed.set_thumbnail(url=guild.icon.url)
        else:
            embed.set_author(name=guild.name)

        view = CategorySelectView(self.bot, guild.id, dm_channel.id, types)
        await view.setup()
        sent_msg = await dm_channel.send(embed=embed, view=view)

    @commands.command()
    @checks.is_owner()
    async def test_dm(self, ctx):
        user = ctx.author
        print(user)
        try:
            dm_channel = await user.create_dm()
            await dm_channel.send("This is a test DM message, via dm channel.")
            await user.send("This is a test DM message, via user send.")
        except discord.Forbidden:
            await ctx.send("I couldn't send you a DM.")

    @commands.command()
    @checks.is_owner()
    async def refresh_ap(self, ctx, user: discord.Member):
        await self.bot.data_manager.get_or_load_ap(ctx.guild.id, user.id, False)
        await ctx.send(f"Refreshed AP for {user.name}")

    @commands.command()
    @checks.is_owner()
    async def leave(self, ctx, *, guild_name: str):
        for guild in self.bot.guilds:
            print("found guild", guild.name)
            if guild.name.casefold() == guild_name.casefold():
                await guild.leave()
                await ctx.send(f"Left server: {guild.name}")

    @commands.command()
    @checks.is_owner()
    async def embed(self, ctx, channel: discord.TextChannel):
        postEmbed = discord.Embed(
            title="Example title",
            description="Example description",
            color=discord.Color.green(),
        )
        postEmbed.add_field(
            name="Example field", value="Example field content", inline=False
        )
        await channel.send(embed=postEmbed)

    @commands.command()
    @checks.is_owner()
    async def say_reply(
        self, ctx, channel: discord.TextChannel, message_id: str, *, message: str
    ):
        await ctx.message.delete()
        try:
            found_message = await channel.fetch_message(int(message_id))
        except Exception:
            embed = discord.Embed(
                description="❌ I couldn't find that message", color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        await found_message.reply(message, mention_author=True)

    @commands.command()
    @checks.is_owner()
    async def say_reply_np(
        self, ctx, channel: discord.TextChannel, message_id: str, *, message: str
    ):
        await ctx.message.delete()
        try:
            found_message = await channel.fetch_message(int(message_id))
        except Exception:
            embed = discord.Embed(
                description="❌ I couldn't find that message", color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        await found_message.reply(message, mention_author=False)

    @commands.command()
    @checks.is_owner()
    async def say(self, ctx, channel: discord.TextChannel, *, message: str):
        await ctx.message.delete()
        await channel.send(message)

    @commands.command()
    @checks.is_owner()
    async def refresh_types(self, ctx, all: str = None):
        if all == "all":
            for guild in self.bot.guilds:
                await self.bot.data_manager.get_or_load_guild_types(guild.id, False)
            await ctx.send("Refreshed all ticket types")
        else:
            await self.bot.data_manager.get_or_load_guild_types(ctx.guild.id, False)
            await ctx.send("Refreshed ticket types")

    @commands.command()
    @checks.is_owner()
    async def refresh_config(self, ctx, all: str = None):
        if all == "all":
            for guild in self.bot.guilds:
                await self.bot.data_manager.get_or_load_config(guild.id, False)
            await ctx.send("Refreshed all configs")
        else:
            await self.bot.data_manager.get_or_load_config(ctx.guild.id, False)
            await ctx.send("Refreshed config")

    @commands.command()
    @checks.is_owner()
    async def del_rticket(self, ctx, user_id, guild_id):
        await self.bot.data_manager.delete_user_ticket(user_id, guild_id)
        await ctx.send(f"Deleted ticket from redis, guild {guild_id}")

    # Runs an SQL query from a message
    @commands.command()
    @checks.is_owner()
    async def sql(self, ctx, message: str):
        result = await self.bot.data_manager.safe_execute_query(message)
        output = ""
        if result:
            for row in result:
                for item in row:
                    output += str(item) + " "
        else:
            output = "Nothing to send"
        await ctx.send(f"{emojis.mantis} Results: {output}")

    # Displays current tickets in cache
    # @commands.command()
    # @checks.is_owner()
    # async def tickets(self, ctx):
    #     tickets = await self.bot.data_manager.get_all_channel_ids()
    #     message = "**Tickets**\n"
    #     if len(tickets) != 0:
    #         for key in tickets:
    #             message += f"<#{key}> {key}\n"
    #         await ctx.send(f"{message}")
    #     else:
    #         await ctx.send("No tickets found!")

    # Deletes one ticket
    @commands.command()
    @checks.is_owner()
    async def del_ticket(self, ctx, channel: int):
        await self.bot.data_manager.remove_ticket(channel)
        await ctx.send(f"Deleted ticket channel {channel}")

    # Empties tickets cache
    @commands.command()
    @checks.is_owner()
    async def empty_tickets(self, ctx):
        await self.bot.data_manager.empty_tickets()
        await ctx.send("Emptied tickets cache")

    # Empties messages cache
    @commands.command()
    @checks.is_owner()
    async def empty_messages(self, ctx):
        await self.bot.data_manager.empty_messages()
        await ctx.send("Emptied messages cache")

    # Empties messages cache
    @commands.command()
    @checks.is_owner()
    async def empty_messages_v2(self, ctx):
        await self.bot.data_manager.empty_messages_v2()
        await ctx.send("Emptied messages_v2 cache")

    # Flushes ticket messages to SQL
    @commands.command()
    @checks.is_owner()
    async def flush(self, ctx):
        await self.bot.data_manager.flush_messages()
        await ctx.send("Emptied messages cache")

    # Example error
    @commands.command()
    async def error(self, ctx):
        raise BotError("Example of an error occurring")

    # Ping for latency
    @commands.command()
    async def ping(self, ctx):
        await ctx.send(f"🐝 pong! {round(self.bot.latency * 1000,2)} ms")


async def setup(bot):
    await bot.add_cog(Util(bot))
