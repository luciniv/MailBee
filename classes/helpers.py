import discord
import re
import os
import asyncio
import aiohttp
import time
from datetime import datetime, timezone

tenor_key = os.getenv("TENOR_KEY")
tenor_cache = {}

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


    async def convert_to_direct_gif(self, url: str) -> str | None:
        # Tenor view links
        if "tenor.com/view/" in url:
            return await self.get_tenor_direct_gif_url(url)

        # Giphy share link
        elif "giphy.com/gifs/" in url:
            match = re.search(r'gifs/.+-(\w+)$', url)
            if match:
                gif_id = match.group(1)
                return f"https://media.giphy.com/media/{gif_id}/giphy.gif"
            return None

        # Imgur
        elif "imgur.com" in url:
            if url.endswith(".gifv"):
                return url.replace(".gifv", ".mp4")
            elif re.match(r'https?://i\.imgur\.com/\w+\.(gif|mp4)', url):
                return url  # Already direct link
            elif re.match(r'https?://imgur\.com/\w+', url):
                img_id = url.split("/")[-1]
                return f"https://i.imgur.com/{img_id}.gif"
            return None

        # Already a direct .gif link
        elif url.endswith(".gif"):
            return url

        return None


    async def get_tenor_direct_gif_url(self, view_url: str) -> str | None:
        try:
            # Extract numeric media ID at the end of the URL
            match = re.search(r'(\d+)$', view_url)
            if not match:
                return None
            
            media_id = match.group(1)

            # Check cache
            now = time.time()
            if media_id in tenor_cache:
                cached_url, expires_at = tenor_cache[media_id]
                if now < expires_at:
                    return cached_url
                else:
                    del tenor_cache[media_id]  # Expired

            # Call Tenor API to get direct GIF URL
            api_url = f"https://tenor.googleapis.com/v2/posts"
            params = {
                "ids": media_id,
                "key": tenor_key
            }

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                async with session.get(api_url, params=params) as response:
                    if response.status != 200:
                        return None

                    data = await response.json()
                    if not data.get("results"):
                        return None

                    gif_url = data["results"][0]["media_formats"]["gif"]["url"]

                    # Cache for 30 minutes
                    tenor_cache[media_id] = (gif_url, now + 1800)
                    return gif_url

        except asyncio.TimeoutError:
            return None

        except Exception as e:
            return None