# import asyncio
# import discord
# from discord import NotFound
# from collections import namedtuple

# TicketRequest = namedtuple("TicketRequest", ["user_id", "guild_id", "category_id", "type_name", "modal_input"])
# ticket_queue: list[TicketRequest] = []

# async def ticket_queue_processor(bot):
#     while True:
#         await asyncio.sleep(10)

#         # Group tickets by guild and category to minimize category fetches
#         grouped = {}
#         for ticket in ticket_queue:
#             key = (ticket.guild_id, ticket.category_id)
#             grouped.setdefault(key, []).append(ticket)

#         to_remove = []
#         for (guild_id, category_id), tickets in grouped.items():
#             guild = bot.get_guild(guild_id)
#             if not guild:
#                 continue

#             category = guild.get_channel(category_id)
#             if not category:
#                 continue

#             current_ticket_count = len([c for c in category.channels if isinstance(c, discord.TextChannel)])
#             available_slots = 50 - current_ticket_count
#             process_now = tickets[:available_slots]
#             queued = tickets[available_slots:]

#             for ticket in process_now:
#                 member = await safe_fetch_member(bot, guild, ticket.user_id)
#                 if member:
#                     await open_ticket(ticket, member, category)
#                     to_remove.append(ticket)

#             for idx, ticket in enumerate(queued, start=1):
#                 await update_queue_dm(bot, ticket.user_id, guild_id, idx)

#         ticket_queue[:] = [t for t in ticket_queue if t not in to_remove]


# async def process_ready_tickets(bot, ready_tickets):
#     tasks = []

#     for ticket in ready_tickets:
#         guild = bot.get_guild(ticket.guild_id)
#         category = guild.get_channel(ticket.category_id)
#         if not category:
#             continue

#         tasks.append(process_single_ticket(bot, ticket, guild, category))

#     # Run them all at once
#     await asyncio.gather(*tasks, return_exceptions=True)


# async def process_ready_tickets_staggered(bot, ready_tickets):
#     for i, ticket in enumerate(ready_tickets):
#         guild = bot.get_guild(ticket.guild_id)
#         category = guild.get_channel(ticket.category_id)
#         if not category:
#             continue

#         asyncio.create_task(process_single_ticket(bot, ticket, guild, category))
#         await asyncio.sleep(0.2)  # Stagger a bit (200ms between launches)