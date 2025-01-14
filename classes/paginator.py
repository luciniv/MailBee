import discord
from discord.ext import commands
from discord.ui import View, Button

class Paginator(View):
    def __init__(self, pages, timeout=120):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.message = None


    # Logic for the previous button, takes the view back a page
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.success)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            await interaction.response.defer()


    # Logic for the next button, takes the view forward a page
    @discord.ui.button(label="Next", style=discord.ButtonStyle.success)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            await interaction.response.defer()


    # Disables buttons after view times out
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

        if self.message:
            await self.message.edit(view=self)

