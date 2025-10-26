import asyncio
import json
import os
import urllib.parse
from pathlib import Path

import aiohttp
import discord
from dotenv import load_dotenv

from roblox_data.decoder import CONFIG
from utils.logger import *

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)
api_key = os.getenv("ROBLOX_API_KEY")


HEADERS = {"x-api-key": api_key}
MAX_RETRIES = 2

SERVER_TO_GAME = {
    714722808009064492: ("Creatures of Sonaria", 1831550657, os.getenv("COS_KEY")),
    346515443869286410: ("Dragon Adventures", 1235188606, os.getenv("DA_KEY")),
    1196293227976863806: ("Horse Life", 5422546686, os.getenv("HL_KEY")),
    549701425958223895: ("World // Zero", 0, os.getenv("WZ_KEY")),
    1007432760027250740: ("Drive World", 0, os.getenv("DW_KEY")),
    1301233303734718474: ("Dungeon Heroes", 0, os.getenv("DH_KEY")),
}
"""
Maps server IDs to (game name, universe ID, API key env variable)
"""


async def api_call(
    url: str, params: dict | None = None, headers=HEADERS
) -> dict | None:
    """
    Generic function to make an API call and return the JSON response.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
        return None

    except asyncio.TimeoutError:
        return None

    except Exception as e:
        return None


async def get_roblox_user_data(
    guild_id: int, discord_id: int, api_key: str
) -> tuple[str, int] | None:
    print("getting roblox user data for", guild_id, discord_id)
    print("using api key", api_key)
    """
    Fetch Roblox username and ID linked to a Discord user via Bloxlink.
    """
    try:
        username = None
        roblox_id = None

        bloxlink_url = (
            "https://api.blox.link/v4/public/guilds/"
            f"{guild_id}/discord-to-roblox/{discord_id}"
        )
        headers = {"Authorization": api_key}

        response = await api_call(bloxlink_url, headers=headers)
        print("bloxlink response", response)
        if response:
            roblox_id = response.get("robloxID")
            if not roblox_id:
                return None
        else:
            return None

        resolved = response.get("resolved", {})
        if resolved:
            roblox_info = resolved.get("roblox")
            if roblox_info:
                username = roblox_info["name"]
                return [username, roblox_id]

        # Fallback: fetch Roblox username from Roblox API
        roblox_url = f"https://users.roblox.com/v1/users/{roblox_id}"

        response = await api_call(roblox_url)
        print("roblox user response", response)
        if response:
            username = response.get("name")
        else:
            return None

        return [username, roblox_id]

    except Exception as e:
        print("error in get_roblox_user_data", e)
        return None


async def get_datastore_entry(
    universe_id: int, datastore_name: str, entry_key: str, scope: str = "global"
) -> str | None:
    """
    Retrieve an entry from a Roblox datastore.
    """
    try:
        url = (
            "https://apis.roblox.com/datastores/v1/universes/"
            f"{universe_id}/standard-datastores/datastore/entries/entry"
        )
        params = {
            "datastoreName": datastore_name,
            "entryKey": entry_key,
            "scope": scope,
        }

        return await api_call(url, params)

    except Exception as e:
        return None


async def list_ordered_data_store_entries(
    universe_id: int, ordered_datastore: str, scope="global"
) -> dict | None:
    try:
        ordered_datastore = urllib.parse.quote(ordered_datastore, safe="")
        url = (
            f"https://apis.roblox.com/ordered-data-stores/v1/universes/"
            f"{universe_id}/orderedDataStores/{ordered_datastore}"
            f"/scopes/{scope}/entries"
        )
        params = {"max_page_size": 1, "order_by": "value desc"}

        return await api_call(url, params)

    except Exception as e:
        return None


async def get_game_data(game_type, game_id, user_id):
    try:
        game_config = CONFIG[game_type]

        if "keys_prefix" in game_config:
            key_data = await list_ordered_data_store_entries(
                game_id, f"{game_config['keys_prefix']}{user_id}"
            )
            if not key_data:
                return None

            time_key = key_data.get("entries", [{}])[0].get("value")
        else:
            time_key = None

        user_key = f"{game_config['data_prefix']}{user_id}"

        store_name = game_config.get("data_store_name")
        player_data = await get_datastore_entry(
            game_id,
            store_name if store_name else user_key,
            user_key if store_name else time_key,
        )
        return player_data

    except Exception as e:
        return None


async def get_roblox_game_data(game_name: str, game_id: int, user_id: int):
    try:
        game_config = CONFIG[game_name]
        retries = 0
        invalid_data = [-1, -1]

        while retries < MAX_RETRIES:
            player_data = await get_game_data(game_name, game_id, user_id)

            if "NOT_FOUND" in player_data:
                return invalid_data

            if player_data:
                retries = MAX_RETRIES
                continue

            retries += 1
            if retries < MAX_RETRIES:
                await asyncio.sleep(1 * retries)

        if not player_data:
            return invalid_data

        print("player data should be valid", len(player_data))

        result = ""
        if "json_decoder" in game_config:
            result = game_config["json_decoder"](player_data)
            print("result from json decoder", len(result))
        else:
            result = player_data
            print("result is just player data")

        result_dict = json.loads(result)
        values = []
        try:
            robux_spent = game_config["robux_parser"](result_dict)
            time_played = game_config["time_parser"](result_dict)

            values.append(int(robux_spent.replace(",", "")))
            values.append(time_played)

            return values

        except Exception as e:
            print("parsing error", e)
            return invalid_data

    except Exception as e:
        print("general error", e)
        return invalid_data


async def get_roblox_data(game_type: tuple, guild_id: int, user_id: int) -> list | None:
    try:
        print("called get roblox data for", game_type, guild_id, user_id)
        user_info = await get_roblox_user_data(guild_id, user_id, game_type[2])
        print("user info was", user_info)
        if user_info:
            print("attempted to get game data")
            values = await get_roblox_game_data(
                game_type[0], game_type[1], user_info[1]
            )
            print("got game data values", values)
            return user_info.extend(values)
        else:
            print("no user info found")
            return None
    except Exception as e:
        print("error in get_roblox_data", e)
        print("returning None for some reason")
        return None
