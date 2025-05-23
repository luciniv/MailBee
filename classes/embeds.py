import discord
from discord.ext import commands
from datetime import datetime, timezone


# Create embed with pre-set footer and color
class Embeds(discord.Embed):
    def __init__(self, bot: commands.Bot, **kwargs):
        super().__init__(color=0x3ad407, **kwargs)

        # Ensure bot user is available
        if bot.user:
            self.set_footer(text=bot.user.name, icon_url=bot.user.avatar.url if bot.user.avatar else None)

        # Set timestamp
        self.timestamp = datetime.now(timezone.utc)
