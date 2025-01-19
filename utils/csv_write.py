import discord
import csv
from utils.logger import *

def make_file(header, data) -> discord.File:
    file_path = "./tmp/output.csv"
    try:
        with open(file_path, mode="w", newline="") as file:
            writer = csv.writer(file)

            writer.writerow(header)
            writer.writerows(data)  

        with open(file_path, "rb") as file:
            file = discord.File(file, filename="output.csv")
            return file
        
    except Exception as e:
        logger.error(f"make_file sent an error: {e}")

    # await ctx.send("Here is your data:", file=discord_file)

