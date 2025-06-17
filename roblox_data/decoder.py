import subprocess
import tempfile
import os
import json
from .compression.DA import ConversionTable


def prettify_json(data):
    try:
        json_data = json.loads(data)
        return json.dumps(json_data, indent=4)
    except json.JSONDecodeError:
        return data


def call_luau_script(input_string):
    with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix=".txt") as temp_file:
        temp_file.write(input_string)
        temp_file_path = temp_file.name

    result = subprocess.run(
        ["/root/.rokit/bin/lune", "run", "/root/Mantid/roblox_data/translate.luau", temp_file_path],
        text=True,
        capture_output=True
    )

    output = result.stdout.strip()
    os.remove(temp_file_path)

    return output


def da_decoder(player_data):
    if not isinstance(player_data, str):
        player_data = json.dumps(player_data)

    for uncompressed, compressed in ConversionTable:
        player_data = player_data.replace(f'"{compressed}"', f'"{uncompressed}"')

    return prettify_json(player_data)


def sonaria_decoder(player_data):
    return call_luau_script(player_data)


# def horse_life_decoder(player_data):
#     decoded_data = player_data.replace('\\\\\\"', '\\\\"')
#     decoded_data = decoded_data.replace('\\"', '"')
    
#     if decoded_data.startswith('"') and decoded_data.endswith('"'):
#         decoded_data = decoded_data[1:-1]

#     def simplify_data(data):
#         def process_node(node):
#             simplified_node = {}
#             for child in node.get("Children", []):
#                 if not child.get("Children"):
#                     simplified_node[child["Name"]] = child.get("Value")
#                 else:
#                     simplified_node[child["Name"]] = process_node(child) 
#             return simplified_node
      
#         return process_node(data["SerializedData"])
    
#     new_data = simplify_data(json.loads(decoded_data))

#     final_data = prettify_json(json.dumps(new_data))
#     return final_data


def horse_life_decoder(player_data):
    # Step 1: Ensure player_data is a string
    if not isinstance(player_data, str):
        raise ValueError("Expected stringified player data")

    # Step 2: Unwrap if quoted
    if player_data.startswith('"') and player_data.endswith('"'):
        player_data = player_data[1:-1]

    # Step 3: Decode escape characters
    try:
        decoded_str = bytes(player_data, "utf-8").decode("unicode_escape")
        json_obj = json.loads(decoded_str)
    except Exception as e:
        print("Failed decoding player data:", e)
        raise

    # Step 4: Simplify the Roblox nested structure
    def simplify_data(data):
        def process_node(node):
            simplified_node = {}
            for child in node.get("CH", []):  # Roblox uses "CH" for Children
                name = child.get("N")
                value = child.get("V")
                if "CH" in child:
                    simplified_node[name] = process_node(child)
                else:
                    simplified_node[name] = value
            return simplified_node

        return process_node(data["SerializedData"])

    simplified = simplify_data(json_obj)

    # Optionally write to file for inspection
    with open("test.json", "w") as file:
        file.write(json.dumps(simplified, indent=2))

    return simplified



CONFIG = {
    'Dragon Adventures': {
        'keys_prefix': 'keys/live',
        'data_prefix': 'data/live',
        'json_decoder': da_decoder,
        'robux_parser': lambda player_data: format(player_data['Monetization']['RobuxSpent'], ','),
        'time_parser': lambda player_data: round(player_data['Stats']['TimePlayed'] / 3600, 1),
    },
    'Creatures of Sonaria': {
        'keys_prefix': 'keys/live',
        'data_prefix': 'data/live',
        'json_decoder': sonaria_decoder,
        'robux_parser': lambda player_data: format(player_data['Monetization']['RobuxSpent'], ','),
        'time_parser': lambda player_data: round(player_data['Stats']['TimePlayed'] / 3600, 1),
    },
    'Horse Life': {
        'data_store_name': 'PlayerData',
        'data_prefix': 'keys/alpha1',
        'json_decoder': horse_life_decoder,
        'robux_parser': lambda player_data: format(player_data['MetaData']['RobuxSpent'], ','),
        'time_parser': lambda player_data: round(player_data['Stats']['PlayTime'] / 3600, 1),
    },
}