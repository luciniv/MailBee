import discord
import os
import requests
import aiohttp
import urllib.parse
import json
import asyncio
from dotenv import load_dotenv
from pathlib import Path
from utils.logger import *

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)
hl_key = os.getenv("HL_KEY")

from roblox_data.decoder import CONFIG
HEADERS = {'x-api-key': hl_key}
MAX_RETRIES = 3


async def get_roblox_username(guild_id, discord_id, api_key):
    try:
        print("entered get roblox username")
        print(guild_id, discord_id)
        async with aiohttp.ClientSession() as session:
            # Get Roblox ID from Bloxlink API
            bloxlink_url = f"https://api.blox.link/v4/public/guilds/{guild_id}/discord-to-roblox/{discord_id}"
            headers = {"Authorization": api_key}
            async with session.get(bloxlink_url, headers=headers) as response:
                print(f"Bloxlink API Status: {response.status}")
                if response.status != 200:
                    print("Failed to fetch Roblox ID")
                    return None
                
                data = await response.json()
                print("Bloxlink Response:", data)  # Debugging
                roblox_id = data.get("robloxID")
                if not roblox_id:
                    print("No linked Roblox ID found")
                    return None

            # Get Roblox username from Roblox API
            roblox_url = f"https://users.roblox.com/v1/users/{roblox_id}"
            async with session.get(roblox_url) as response:
                print(f"Roblox API Status: {response.status}")
                if response.status != 200:
                    print("Failed to fetch Roblox username")
                    return None

                data = await response.json()
                print("Roblox Response:", data)  # Debugging
                return data.get("name")
    except Exception as e:
        logger.exception(f"get_roblox_username sent an error: {e}")


async def get_roblox_user_info(username):
    try:
        print("entered get_roblox_user_info")
        url = "https://users.roblox.com/v1/usernames/users"
        print("trying for a response")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"usernames": [username]}) as response:
                print(f"Roblox API Status: {response.status}")

                if response.status == 200:
                    data = await response.json()
                    user_data = data.get('data')
                    
                    if user_data:
                        print("there was data!")
                        return user_data[0]  # Return first result

        print("response bad")
        return None
    except Exception as e:
        logger.exception(f"get_roblox_user_info sent an error: {e}")


async def get_datastore_entry(universe_id, datastore_name, entry_key, scope='global'):
    try:
        print("entered get_datastore_entry")
        url = f'https://apis.roblox.com/datastores/v1/universes/{universe_id}/standard-datastores/datastore/entries/entry'
        params = {'datastoreName': datastore_name, 'entryKey': entry_key, 'scope': scope}
        print("get_data_store_entry URL is ", url)

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=HEADERS) as response:
                print(f"Datastore API Status: {response.status}")

                if response.status == 200:
                    print("got the response")
                    return await response.text()  # Successful response

        return None
    except Exception as e:
        logger.exception(f"get_datastore_entry sent an error: {e}")


async def list_ordered_data_store_entries(universe_id, ordered_datastore, scope='global'):
    try:
        print("entered list_ordered_data_store_entries")
        ordered_datastore = urllib.parse.quote(ordered_datastore, safe='')
        url = f'https://apis.roblox.com/ordered-data-stores/v1/universes/{universe_id}/orderedDataStores/{ordered_datastore}/scopes/{scope}/entries'
        params = {'max_page_size': 1, 'order_by': 'desc'}
        print("list_ordered_data_store_entries URL is ", url)

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=HEADERS) as response:
                print(f"Ordered Datastore API Status: {response.status}")

                if response.status == 200:
                    print("got the response")
                    return await response.json()  # Parse JSON response

        return None
    except Exception as e:
        logger.exception(f"list_ordered_data_store_entries sent an error: {e}")
        

async def get_player_data(game_type, game_id, user_id):
    try: 
        print("entered get_player_data")
        game_config = CONFIG[game_type]

        print("section checking if keys prefix is in game config")
        if 'keys_prefix' in game_config:
            print("running api call for ordered data store entries")
            print(game_id, f"{game_config['keys_prefix']}{user_id}")
            key_data = await list_ordered_data_store_entries(game_id, f"{game_config['keys_prefix']}{user_id}")
            if key_data is None:
                return None
            time_key = key_data.get('entries', [{}])[0].get('value')
        else:
            time_key = None

        user_key = f"{game_config['data_prefix']}{user_id}"
        print("user key",user_key)

        print("running api call for get data store entry")
        if 'data_store_name' in game_config:
            print(1)
            player_data = await get_datastore_entry(game_id, game_config['data_store_name'], user_key)
        else:
            print(2)
            player_data = await get_datastore_entry(game_id, user_key, time_key)

        if player_data is None:
            return None
        else:
            return player_data
    except Exception as e:
        logger.exception(f"get_player_data sent an error: {e}")


async def get_user_and_player_data(user: str, game_type: discord.app_commands.Choice[int]):
    try:
        print("entered get user and player data")
        game_config = CONFIG[game_type.name]
        user_info = await get_roblox_user_info(user)
        
        if user_info is None:
            return None, None, "User account does not exist on Roblox"
        
        print("Got user info", user_info)

        user_id = user_info['id']
        username = user_info['name']
        display_name = user_info['displayName']

        print("starting loop to get_player_data")
        retries = 0
        while retries < MAX_RETRIES:
            print("called get_player_data")
            print(game_type.name, game_type.value, user_id)
            player_data = await get_player_data(game_type.name, game_type.value, user_id)

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
                
        print("loop for getting the data is done")

        print("starting the json_decoder section")
        if 'json_decoder' in game_config:
            result = game_config['json_decoder'](player_data)
        else:
            result = player_data

        with open("output.json", "w") as file:
            file.write(result)

        result_dict = json.loads(result)
        print("left the json_decoder section")

        print("parsing specific data to return")
        values = []
        try:
            robux_spent = game_config['robux_parser'](result_dict)
            time_played = game_config['time_parser'](result_dict)
            
            values.append(int(robux_spent.replace(",", "")))
            values.append(time_played)
            print(values)

            message = f'{game_type.name} - {username} - R${robux_spent} - {time_played}hrs'
        except Exception as e:
            print(e)
            message = "Error retriving engagement statistics"

        return message, 'output.json', user_info
    except Exception as e:
        logger.exception(f"get_user_and_player_data sent an error: {e}")


async def ticket_get_user_and_player_data(user: str, game_name: str, game_id: int):
    try:
        print("entered get user and player data")
        game_config = CONFIG[game_name]
        user_info = await get_roblox_user_info(user)
        
        if user_info is None:
            return None, None, "User account does not exist on Roblox"

        user_id = user_info['id']
        username = user_info['name']
        display_name = user_info['displayName']

        print("starting loop to get_player_data")
        retries = 0
        while retries < MAX_RETRIES:
            print("called get_player_data")
            player_data = await get_player_data(game_name, game_id, user_id)

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
                
        print("loop for getting the data is done")

        print("starting the json_decoder section")
        if 'json_decoder' in game_config:
            result = game_config['json_decoder'](player_data)
        else:
            result = player_data

        with open("output.json", "w") as file:
            file.write(result)

        result_dict = json.loads(result)
        print("left the json_decoder section")

        print("parsing specific data to return")
        values = []
        try:
            robux_spent = game_config['robux_parser'](result_dict)
            time_played = game_config['time_parser'](result_dict)
            
            values.append(int(robux_spent.replace(",", "")))
            values.append(time_played)
            print(values)

        except Exception as e:
            values = None

        return values, 'output.json', user_info
    except Exception as e:
        logger.exception(f"ticket_get_user_and_player_data sent an error: {e}")


async def get_priority(game_type: tuple, guildID: int, openID: int):
    try:
        roblox_username = await get_roblox_username(guildID, openID, game_type[2])
        print(roblox_username)

        if roblox_username:
            print("roblox_username was not none")
            values, file_path, error = await ticket_get_user_and_player_data(roblox_username, game_type[0], game_type[1])
            print(values)
            return values
        return None
    except Exception as e:
        logger.exception(f"get_priority sent an error: {e}")