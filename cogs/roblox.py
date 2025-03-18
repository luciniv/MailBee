import discord
from discord.ext import commands
from discord import app_commands
from roblox_data.helpers import *
from utils.logger import *
from utils import checks


GAME_TYPE_CHOICES = [
    discord.app_commands.Choice(name="Dragon Adventures", value=1235188606),
    discord.app_commands.Choice(name="Horse Life", value=5422546686)]


class Roblox(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @app_commands.command(name="engagement", description="Get Roblox engagement data for a user")
    @checks.is_user_app()
    @app_commands.describe(username="Roblox username")
    @app_commands.describe(game_type="Select the game")
    @app_commands.choices(game_type=GAME_TYPE_CHOICES)
    async def engagement(self, interaction: discord.Interaction, username: str, game_type: discord.app_commands.Choice[int]):
        await interaction.response.defer()

        try:
            message, file_path, error = await get_user_and_player_data(username, game_type)
        
            if isinstance(error, str):
                await interaction.followup.send(error)
                return

            await interaction.followup.send(message)

        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}")
            raise Exception


    @app_commands.command(name="getdata", description="Get player data file")
    @checks.is_user_app()
    @app_commands.describe(username="Roblox username")
    @app_commands.describe(game_type="Select the game")
    @app_commands.choices(game_type=GAME_TYPE_CHOICES)
    async def getdata(self, interaction: discord.Interaction, username: str, game_type: discord.app_commands.Choice[int]):
        await interaction.response.defer()

        try:
            _, file_path, error = await get_user_and_player_data(username, game_type)

            if isinstance(error, str):
                await interaction.followup.send(error)
                return

            await interaction.followup.send(f'Grabbing player data for {error["name"]}')

            with open(file_path, 'rb') as file:
                await interaction.followup.send(file=discord.File(file, filename='player_data.json'))

        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}")

async def setup(bot):
    await bot.add_cog(Roblox(bot))