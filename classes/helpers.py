import discord
import re
import asyncio
from datetime import datetime, timezone
from utils.logger import *


class Helper:
    def __init__(self, bot):
        self.bot = bot

    async def convert_mentions(self, text, guild):
        # Find all <#channel_id> patterns
        matches = re.findall(r'<#(\d+)>', text)
        for channel_id in matches:
            channel = None
            try:
                channel = guild.get_channel(int(channel_id))
                if channel is None:
                    channel = await asyncio.wait_for(self.bot.fetch_channel(channel_id), timeout=1)
            except Exception:
                pass
            if channel:
                text = text.replace(f'https://discord.com/channels/{guild.id}/{channel_id}', channel.mention)
        return text

