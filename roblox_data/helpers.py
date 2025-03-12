import discord
import os
import requests
import urllib.parse
import json
import asyncio
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)
hl_key = os.getenv("HL_KEY")

from roblox_data.decoder import CONFIG
HEADERS = {'x-api-key': hl_key}
MAX_RETRIES = 3


def get_roblox_user_info(username):
    print("entered get_roblox_user_info")
    url = "https://users.roblox.com/v1/usernames/users"
    print("trying for a response")
    response = requests.post(url, json={"usernames": [username]})
    if response.status_code == 200:
        print("response good!")
        data = response.json().get('data')
        if data:
            print("there was data!")
            return data[0]
    print("response bad")
    return None

def get_datastore_entry(universe_id, datastore_name, entry_key, scope='global'):
    print("entered get data store entry")
    url = f'https://apis.roblox.com/datastores/v1/universes/{universe_id}/standard-datastores/datastore/entries/entry'
    params = {'datastoreName': datastore_name, 'entryKey': entry_key, 'scope': scope}
    # print(url, params, HEADERS)
    response = requests.get(url, params=params, headers=HEADERS)

    if response.status_code == 200:
        print("got the response")
        return response.text  # Successful response
    else:
        return None

def list_ordered_data_store_entries(universe_id, ordered_datastore, scope='global'):
    print("entered ordered data store entires")
    ordered_datastore = urllib.parse.quote(ordered_datastore, safe='')
    url = f'https://apis.roblox.com/ordered-data-stores/v1/universes/{universe_id}/orderedDataStores/{ordered_datastore}/scopes/{scope}/entries'
    params = {'max_page_size': 1, 'order_by': 'desc'}
    response = requests.get(url, headers=HEADERS, params=params)

    if response.status_code == 200:
        print("got the response")
        return response.json()
    else:
        return None

def get_player_data(game_type, game_id, user_id):
    print("hl_key is",hl_key)
    print("entered get_player_data")
    game_config = CONFIG[game_type]

    print("section checking if keys prefix is in game config")
    if 'keys_prefix' in game_config:
        print("running api call for ordered data store entries")
        key_data = list_ordered_data_store_entries(game_id, f"{game_config['keys_prefix']}{user_id}")
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
        player_data = get_datastore_entry(game_id, game_config['data_store_name'], user_key)
    else:
        print(2)
        player_data = get_datastore_entry(game_id, user_key, time_key)

    print(player_data)
    if player_data is None:
        return None
    else:
        return player_data


async def get_user_and_player_data(user: str, game_type: discord.app_commands.Choice[int]):
    print("entered get user and player data")
    game_config = CONFIG[game_type.name]
    user_info = get_roblox_user_info(user)
    
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
        player_data = get_player_data(game_type.name, game_type.value, user_id)

        if "NOT_FOUND" in player_data:
            return None, None, "User has no data"
        
        if player_data is not None:
            retries = MAX_RETRIES
            continue

        retries += 1
        if retries < MAX_RETRIES:
            await asyncio.sleep(3 * retries)
            
    print("loop for getting the data is done")
    print("THIS IS THE PLAYER DATA", player_data)

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
    try:
        robux_spent = game_config['robux_parser'](result_dict)
        time_played = game_config['time_parser'](result_dict)

        # Adds robux spent + hours converted to robux (1hr = 100 rbx)
        priority_value = robux_spent + (100 * time_played)
        message = f'{game_type.name} - {username} - R${robux_spent} - {time_played}hrs'
    except Exception as e:
        print(e)
        message = "Error retriving engagement statistics"

    return message, 'output.json', user_info