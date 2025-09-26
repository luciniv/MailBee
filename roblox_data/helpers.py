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
api_key = os.getenv("API_KEY")


HEADERS = {"x-api-key": api_key}
MAX_RETRIES = 1


async def get_roblox_user_data(
    guild_id: int, discord_id: int, api_key: str
) -> tuple[str, int] | None:
    """Fetch Roblox username and ID linked to a Discord user via Bloxlink.

    Args:
        guild_id: The Discord guild ID.
        discord_id: The Discord user ID.
        api_key: API key for Bloxlink authorization.

    Returns:
        [username, roblox_id] if successful, otherwise None.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=4)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            username = None
            roblox_id = None

            bloxlink_url = (
                "https://api.blox.link/v4/public/guilds/"
                f"{guild_id}/discord-to-roblox/{discord_id}"
            )
            headers = {"Authorization": api_key}

            async with session.get(bloxlink_url, headers=headers) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                roblox_id = data.get("robloxID")
                if not roblox_id:
                    return None

                resolved = data.get("resolved", {})
                roblox_info = resolved.get("Roblox")
                if roblox_info:
                    username = roblox_info["Name"]
                else:
                    # Fallback: fetch Roblox username from Roblox API
                    roblox_url = f"https://users.roblox.com/v1/users/{roblox_id}"
                    async with session.get(roblox_url) as response:
                        if response.status != 200:
                            return None

                        data = await response.json()
                        username = data.get("name")

        return [username, roblox_id]

    except asyncio.TimeoutError:
        # logger.warning("get_roblox_username request timed out")
        return None

    except Exception as e:
        # logger.error(f"get_roblox_username sent an error: {e}")
        return None


async def get_datastore_entry(
    universe_id: int, datastore_name: str, entry_key: str, scope: str = "global"
) -> str | None:
    """
    Retrieve an entry from a Roblox datastore.

    Args:
        universe_id (int): The Roblox universe ID.
        datastore_name (str): The name of the datastore.
        entry_key (str): The key of the entry to retrieve.
        scope (str, optional): The datastore scope. Defaults to "global".

    Returns:
        str | None: The datastore entry content if successful,
        otherwise None.
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
        timeout = aiohttp.ClientTimeout(total=3)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params, headers=HEADERS) as response:
                if response.status == 200:
                    return await response.text()  # Successful response
        return None

    except asyncio.TimeoutError:
        # logger.warning("get_datastore_entry request timed out")
        return None

    except Exception as e:
        # logger.error(f"get_datastore_entry sent an error: {e}")
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
        params = {"max_page_size": 1, "order_by": "desc"}

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=3)
        ) as session:
            async with session.get(url, params=params, headers=HEADERS) as response:

                if response.status == 200:
                    return await response.json()

        return None

    except asyncio.TimeoutError:
        # logger.warning("list_ordered_data_store_entries request timed out")
        return None

    except Exception as e:
        # logger.error(f"list_ordered_data_store_entries sent an error: {e}")
        return None


async def get_player_data(game_type, game_id, user_id):
    try:
        game_config = CONFIG[game_type]

        if "keys_prefix" in game_config:
            key_data = await list_ordered_data_store_entries(
                game_id, f"{game_config['keys_prefix']}{user_id}"
            )
            if key_data is None:
                return None
            time_key = key_data.get("entries", [{}])[0].get("value")
        else:
            time_key = None

        user_key = f"{game_config['data_prefix']}{user_id}"

        if "data_store_name" in game_config:
            player_data = await get_datastore_entry(
                game_id, game_config["data_store_name"], user_key
            )
        else:
            player_data = await get_datastore_entry(game_id, user_key, time_key)

        if player_data is None:
            return None
        else:
            return player_data

    except Exception as e:
        # logger.error(f"get_player_data sent an error: {e}")
        return None


async def get_user_and_player_data(
    user: str, game_type: discord.app_commands.Choice[int]
):
    try:
        game_config = CONFIG[game_type.name]
        username, user_id = await get_roblox_user_data(user)

        if user_id is None:
            return None, None, "User account does not exist on Roblox"

        retries = 0
        while retries < MAX_RETRIES:
            player_data = await get_player_data(
                game_type.name, game_type.value, user_id
            )

            if player_data is not None:
                retries = MAX_RETRIES
                continue
            elif player_data is None:
                pass
            elif "NOT_FOUND" in player_data:
                return None, None, "User has no data"

            retries += 1
            if retries < MAX_RETRIES:
                await asyncio.sleep(3 * retries)

        if player_data is None:
            return None, None, "User has no data"

        if "json_decoder" in game_config:
            result = game_config["json_decoder"](player_data)
        else:
            result = player_data

        with open("output.json", "w") as file:
            file.write(result)

        result_dict = json.loads(result)
        values = []
        robux_spent = None
        time_played = None
        try:
            try:
                robux_spent = game_config["robux_parser"](result_dict)
                time_played = game_config["time_parser"](result_dict)
            except Exception as e:
                message = "Error retriving engagement statistics"
                return message, "output.json", username

            values.append(int(robux_spent.replace(",", "")))
            values.append(time_played)

            message = (
                f"{game_type.name} - {username} - R${robux_spent} - {time_played}hrs"
            )
        except Exception as e:
            message = "Error retriving engagement statistics"

        return message, "output.json", username
    except Exception as e:
        # logger.error(f"get_user_and_player_data sent an error: {e}")
        pass


async def ticket_get_player_data(game_name: str, game_id: int, user_id: int):
    try:
        game_config = CONFIG[game_name]
        retries = 0
        invalid_data = [-1, -1]

        while retries < MAX_RETRIES:
            player_data = await get_player_data(game_name, game_id, user_id)

            if player_data is not None:
                retries = MAX_RETRIES
                continue
            elif player_data is None:
                pass
            elif "NOT_FOUND" in player_data:
                return invalid_data

            retries += 1
            if retries < MAX_RETRIES:
                await asyncio.sleep(3 * retries)

        if player_data is None:
            return invalid_data

        if "json_decoder" in game_config:
            result = game_config["json_decoder"](player_data)
        else:
            result = player_data

        with open("output.json", "w") as file:
            file.write(result)

        result_dict = json.loads(result)
        values = []
        try:
            robux_spent = game_config["robux_parser"](result_dict)
            time_played = game_config["time_parser"](result_dict)

            values.append(int(robux_spent.replace(",", "")))
            values.append(time_played)

            return values

        except Exception as e:
            return invalid_data

    except Exception as e:
        # logger.error(f"ticket_get_player_data sent an error: {e}")
        return invalid_data


async def get_roblox_data(game_type: tuple, guild_id: int, user_id: int) -> list | None:
    try:
        user_info = await get_roblox_user_data(guild_id, user_id, game_type[2])
        if user_info:
            values = await ticket_get_player_data(
                game_type[0], game_type[1], user_info[1]
            )
            return user_info.extend(values)
        else:
            return None
    except Exception as e:
        # logger.error(f"get_roblox_data sent an error: {e}")
        return None
