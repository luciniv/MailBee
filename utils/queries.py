import discord
from typing import List


# Reads query data to create embed fields
# Implemented to reduce code repeption
def generate_fields(data: List[int], index: int) -> List[str]:
    field = ""
    fields = []
    stop = index + 6
    # Generate 3 at a time i have 3 name fields, so i need 3 corresponding values in a list
    # assume index is 0 to start, each time i loop add 2 to it (3 loops)
    while (index < stop):
        if (data[index + 1] != 0):
            percentage = (data[index] / data[index + 1]) * 100
            field = f"{data[index]} / {data[index + 1]}" + f" - {percentage:.0f}%"
        else:
            field = "No Data"
        fields.append(field)

        index += 2
    
    return fields


# Generate query string and get results for the member_stats command
def mod_data(guildID: discord.Guild, closeByID: int, intervals: List[str]):
    query = "SELECT"
    
    for span in intervals:
        if (span != "TOTAL"):
            query += f"""
                (SELECT COUNT(*) 
                FROM tickets 
                WHERE guildID = {guildID}
                AND closeByID = {closeByID}
                AND status = 'closed' 
                AND dateClose >= NOW() - INTERVAL {span}),

                (SELECT COUNT(*) 
                FROM tickets 
                WHERE guildID = {guildID}
                AND status = 'closed' 
                AND dateClose >= NOW() - INTERVAL {span}),
            
                (SELECT COUNT(*) 
                FROM ticket_messages 
                INNER JOIN tickets 
                ON ticket_messages.modmail_messageID = tickets.messageID 
                WHERE tickets.guildID = {guildID}
                AND ticket_messages.authorID = {closeByID}
                AND ticket_messages.type = 'Sent'
                AND ticket_messages.date >= NOW() - INTERVAL {span}),

                (SELECT COUNT(*) 
                FROM ticket_messages 
                INNER JOIN tickets 
                ON ticket_messages.modmail_messageID = tickets.messageID 
                WHERE tickets.guildID = {guildID}
                AND ticket_messages.type = 'Sent'
                AND ticket_messages.date >= NOW() - INTERVAL {span}),

                (SELECT COUNT(*) 
                FROM ticket_messages 
                INNER JOIN tickets 
                ON ticket_messages.modmail_messageID = tickets.messageID 
                WHERE tickets.guildID = {guildID}
                AND ticket_messages.authorID = {closeByID}
                AND ticket_messages.type = 'Discussion'
                AND ticket_messages.date >= NOW() - INTERVAL {span}),

                (SELECT COUNT(*) 
                FROM ticket_messages 
                INNER JOIN tickets 
                ON ticket_messages.modmail_messageID = tickets.messageID 
                WHERE tickets.guildID = {guildID}
                AND ticket_messages.type = 'Discussion'
                AND ticket_messages.date >= NOW() - INTERVAL {span}),"""
        
    if "TOTAL" in intervals:
        query += f"""
            (SELECT COUNT(*) 
            FROM tickets 
            WHERE guildID = {guildID}
            AND closeByID = {closeByID} 
            AND status = 'closed'),

            (SELECT COUNT(*) 
            FROM tickets 
            WHERE guildID = {guildID}
            AND status = 'closed'),

            (SELECT COUNT(*) 
            FROM ticket_messages 
            INNER JOIN tickets 
            ON ticket_messages.modmail_messageID = tickets.messageID 
            WHERE tickets.guildID = {guildID}
            AND ticket_messages.authorID = {closeByID}
            AND ticket_messages.type = 'Sent'),

            (SELECT COUNT(*) 
            FROM ticket_messages 
            INNER JOIN tickets 
            ON ticket_messages.modmail_messageID = tickets.messageID 
            WHERE tickets.guildID = {guildID}
            AND ticket_messages.type = 'Sent'),

            (SELECT COUNT(*) 
            FROM ticket_messages 
            INNER JOIN tickets 
            ON ticket_messages.modmail_messageID = tickets.messageID 
            WHERE tickets.guildID = {guildID}
            AND ticket_messages.authorID = {closeByID}
            AND ticket_messages.type = 'Discussion'),

            (SELECT COUNT(*) 
            FROM ticket_messages 
            INNER JOIN tickets 
            ON ticket_messages.modmail_messageID = tickets.messageID 
            WHERE tickets.guildID = {guildID}
            AND ticket_messages.type = 'Discussion');
            """
    else:
        # Fixes possible dangling comma
        query = query.rstrip(',') + ';'

    print(query)
    
    return query
