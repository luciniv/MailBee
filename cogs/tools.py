import discord
from discord.ext import commands
from utils.logger import *
from utils.emojis import *


class Tools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    # @commands.Cog.listener()
    # async def on_guild_channel_create(self, channel):
    #     if (isinstance(channel, discord.TextChannel)):
    #         guild = channel.guild
    #         category = channel.category
    #         open_overflow_cats = []
    #         full_overflow_cats = []

    #         # Gets all monitored channels / categories and their types for the guild
    #         search_monitor = [
    #             (channelID) for guildID, channelID, monitorType 
    #             in self.bot.data_manager.monitored_channels
    #             if (guildID == guild.id)]
            
    #         # Guild has no monitored channels
    #         if (len(search_monitor) == 0):
    #             return 
            
    #         # Category is monitored
    #         if category.id in search_monitor:
    #             for cat_channel in category.channels:
    #                 # Category contains modmail channel
    #                 if cat_channel in search_monitor:
    #                     if (len(category.channels) == 5):
    #                         # Scan for pre-exisitng non-full overflow categories
    #                         categories = guild.categories
    #                         for cat in categories:
    #                             if ((cat.name)[:-2] == "OVERFLOW"):
    #                                 if (len(cat.channels) < 5):
    #                                     open_overflow_cats.append(cat)
    #                                 else:
    #                                     full_overflow_cats.append(cat)
                            
    #                         # Determine if a new category needs made
    #                         if (len(open_overflow_cats) == 0) and (len(full_overflow_cats) == 0):
    #                             # Create OVERFLOW 1 category after MODMAIL, move channel there
    #                             pass
    #                         elif (len(open_overflow_cats) == 0):
    #                             open_id = 1
    #                             for cat in full_overflow_cats:
    #                                 pass

    #                             # All overflow cats are full vvv
    #                             # Create smallest numbered new overflow cat possible
    #                             pass
    #                         else:
    #                             open_id = 1
    #                             # Insert ticket into lowest numbered overflow cat with space
    #                             for cat in open_overflow_cats:
    #                                 if (id == int(((cat.name).split())[1])):
    #                                     pass
                                    
                            
    #                         position = category.position
    #                         overwrites = category.overwrites
    #                         new_category = await guild.create_category(name=f"OVERFLOW {ID}", overwrites=overwrites, position=position + 1)


async def setup(bot):
    await bot.add_cog(Tools(bot))
