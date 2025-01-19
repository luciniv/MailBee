import discord
from typing import List


# Formats time as 0h 00m
def format_time(minutes) -> str:
    hours = int(minutes // 60) 
    remaining_minutes = int(minutes % 60)

    return f"{hours}h {remaining_minutes}m"


# Formats the data for each field, using two data items at a time
def format_data(data: List[int], index: int, col_name) -> str:
    field = "No Data"
    cleaned_words = []
    time_words = ["duration", "time"]

    if col_name is not None:
        words = col_name.split()
        cleaned_words = [word.casefold() for word in words]

    if (data[index] is None):
        return field
    
    elif (data[index + 1] != 0):
        local_data = data[index]
        global_data = data[index + 1]
        percentage = (local_data / global_data) * 100

        if any(word in cleaned_words for word in time_words):
            local_data = format_time(local_data)
            global_data = format_time(global_data)

        elif ("average" in cleaned_words):
            local_data = f"{local_data:.2f}"
            global_data = f"{global_data:.2f}"

        field = f"{local_data} / {global_data}" + f" - {percentage:.0f}%"
        return field
    
    else:
        return field


# Reads query data to create embed fields
# Implemented to reduce code repetition
def generate_fields(data: List[int], index: int, columns: List[str]) -> List[str]:
    fields = []
    stop = index + 6
    col = 0
    # Generate 3 at a time i have 3 name fields, so i need 3 corresponding values in a list
    # assume index is 0 to start, each time i loop add 2 to it (3 loops)
    while (index < stop):
        fields.append(format_data(data, index, columns[col]))
        col += 1
        index += 2
    
    return fields


def server_stats(guildID: int, intervals: List[str]):
    query = f"""
        SELECT 
        (SELECT COUNT(*)
        FROM tickets
        WHERE tickets.guildID = {guildID}
        AND tickets.status = 'open'),

        (SELECT COUNT(*)
        FROM tickets
        WHERE tickets.status = 'open'),

        (SELECT COUNT(*)
        FROM tickets
        WHERE tickets.guildID = {guildID}),

        (SELECT COUNT(*)
        FROM tickets),
        """

    for span in intervals:
        if (span != "TOTAL"):
            query += f"""
                (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
                FROM tickets
                WHERE guildID = {guildID}
                AND status = 'closed'
                AND dateClose >= NOW() - INTERVAL {span}),
                
                (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
                FROM tickets
                WHERE status = 'closed'
                AND dateClose >= NOW() - INTERVAL {span}),
                    
                (SELECT AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date))
                FROM tickets
                INNER JOIN (
                    SELECT modmail_messageID, MIN(date) AS date
                    FROM ticket_messages
                    WHERE type = 'Sent'
                    GROUP BY modmail_messageID
                ) AS first_message
                ON tickets.messageID = first_message.modmail_messageID
                WHERE tickets.guildID = {guildID}
                AND tickets.status = 'closed'
                AND tickets.flag = 'good'
                AND tickets.dateClose >= NOW() - INTERVAL {span}),
                
                (SELECT AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date))
                FROM tickets
                INNER JOIN (
                    SELECT modmail_messageID, MIN(date) AS date
                    FROM ticket_messages
                    WHERE type = 'Sent'
                    GROUP BY modmail_messageID
                ) AS first_message
                ON tickets.messageID = first_message.modmail_messageID
                WHERE tickets.status = 'closed'
                AND tickets.flag = 'good'
                AND tickets.dateClose >= NOW() - INTERVAL {span}),
                
                (SELECT AVG(message_count)
                FROM (
                    SELECT 
                    COUNT(ticket_messages.messageID) AS message_count
                    FROM tickets
                    INNER JOIN ticket_messages 
                    ON tickets.messageID = ticket_messages.modmail_messageID
                    WHERE tickets.guildID = {guildID}
                    AND tickets.status = 'closed'
                    AND tickets.dateClose >= NOW() - INTERVAL {span}
                    GROUP BY tickets.messageID
                ) AS ticket_counts),
                
                (SELECT AVG(message_count)
                FROM (
                    SELECT 
                    COUNT(ticket_messages.messageID) AS message_count
                    FROM tickets
                    INNER JOIN ticket_messages 
                    ON tickets.messageID = ticket_messages.modmail_messageID
                    WHERE tickets.guildID = tickets.status = 'closed'
                    AND tickets.dateClose >= NOW() - INTERVAL {span}
                    GROUP BY tickets.messageID
                ) AS ticket_counts),"""

    if "TOTAL" in intervals:
        query += f"""
            (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
            FROM tickets
            WHERE guildID = {guildID}
            AND status = 'closed'),
            
            (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
            FROM tickets
            WHERE status = 'closed'),
                
            (SELECT AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date))
            FROM tickets
            INNER JOIN (
                SELECT modmail_messageID, MIN(date) AS date
                FROM ticket_messages
                WHERE type = 'Sent'
                GROUP BY modmail_messageID
            ) AS first_message
            ON tickets.messageID = first_message.modmail_messageID
            WHERE tickets.guildID = {guildID}
            AND tickets.status = 'closed'
            AND tickets.flag = 'good'),
            
            (SELECT AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date))
            FROM tickets
            INNER JOIN (
                SELECT modmail_messageID, MIN(date) AS date
                FROM ticket_messages
                WHERE type = 'Sent'
                GROUP BY modmail_messageID
            ) AS first_message
            ON tickets.messageID = first_message.modmail_messageID
            WHERE tickets.status = 'closed'
            AND tickets.flag = 'good'),

            (SELECT AVG(message_count)
            FROM (
                SELECT 
                COUNT(ticket_messages.messageID) AS message_count
                FROM tickets
                INNER JOIN ticket_messages 
                ON tickets.messageID = ticket_messages.modmail_messageID
                WHERE tickets.guildID = {guildID}
                AND tickets.guildID = tickets.status = 'closed'
                GROUP BY tickets.messageID
            ) AS ticket_counts),
            
            (SELECT AVG(message_count)
            FROM (
                SELECT 
                COUNT(ticket_messages.messageID) AS message_count
                FROM tickets
                INNER JOIN ticket_messages 
                ON tickets.messageID = ticket_messages.modmail_messageID
                WHERE tickets.guildID = tickets.status = 'closed'
                GROUP BY tickets.messageID
            ) AS ticket_counts);"""
    else:
        # Fixes possible dangling comma
        query = query.rstrip(',') + ';'
    
    return query


# Generate query string and get results for the member_stats command
def server_stats_CSV(guildIDs: List[int], intervals: List[str]):
    query_list = []

    for guildID in guildIDs:
        query = f"""
            SELECT 
            (SELECT COUNT(*)
            FROM tickets
            WHERE tickets.guildID = {guildID}
            AND tickets.status = 'open'),

            (SELECT COUNT(*)
            FROM tickets
            WHERE tickets.guildID = {guildID}),
            """
        
        for span in intervals:
            if (span != "TOTAL"):
                query += f"""
                    (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
                    FROM tickets
                    WHERE guildID = {guildID}
                    AND status = 'closed'
                    AND dateClose >= NOW() - INTERVAL {span}),
                        
                    (SELECT AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date))
                    FROM tickets
                    INNER JOIN (
                        SELECT modmail_messageID, MIN(date) AS date
                        FROM ticket_messages
                        WHERE type = 'Sent'
                        GROUP BY modmail_messageID
                    ) AS first_message
                    ON tickets.messageID = first_message.modmail_messageID
                    WHERE tickets.guildID = {guildID}
                    AND tickets.status = 'closed'
                    AND tickets.flag = 'good'
                    AND tickets.dateClose >= NOW() - INTERVAL {span}),
                    
                    (SELECT AVG(message_count)
                    FROM (
                        SELECT 
                        COUNT(ticket_messages.messageID) AS message_count
                        FROM tickets
                        INNER JOIN ticket_messages 
                        ON tickets.messageID = ticket_messages.modmail_messageID
                        WHERE tickets.guildID = {guildID}
                        AND tickets.status = 'closed'
                        AND tickets.dateClose >= NOW() - INTERVAL {span}
                        GROUP BY tickets.messageID
                    ) AS ticket_counts),"""
                
        if "TOTAL" in intervals:
            query += f"""
                (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
                FROM tickets
                WHERE guildID = {guildID}
                AND status = 'closed'),
                    
                (SELECT AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date))
                FROM tickets
                INNER JOIN (
                    SELECT modmail_messageID, MIN(date) AS date
                    FROM ticket_messages
                    WHERE type = 'Sent'
                    GROUP BY modmail_messageID
                ) AS first_message
                ON tickets.messageID = first_message.modmail_messageID
                WHERE tickets.guildID = {guildID}
                AND tickets.status = 'closed'
                AND tickets.flag = 'good'),

                (SELECT AVG(message_count)
                FROM (
                    SELECT 
                    COUNT(ticket_messages.messageID) AS message_count
                    FROM tickets
                    INNER JOIN ticket_messages 
                    ON tickets.messageID = ticket_messages.modmail_messageID
                    WHERE tickets.guildID = {guildID}
                    AND tickets.guildID = tickets.status = 'closed'
                    GROUP BY tickets.messageID
                ) AS ticket_counts);"""
        else:
            # Fixes possible dangling comma
            query = query.rstrip(',') + ';'
        query_list.append(query)
    
    return query_list


# Generate query string and get results for the member_stats command
def mod_activity(guildID: int, closeByID: int, intervals: List[str]):
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
            AND ticket_messages.type = 'Discussion');"""
    else:
        # Fixes possible dangling comma
        query = query.rstrip(',') + ';'
    
    return query

# Generate query string and get results for the member_stats command
def mod_activity_CSV(guildID: int, modIDs: int, intervals: List[str]):
    query_list = []

    for modID in modIDs:
        query = "SELECT"
        for span in intervals:
            if (span != "TOTAL"):
                query += f"""
                    (SELECT COUNT(*) 
                    FROM tickets 
                    WHERE guildID = {guildID}
                    AND closeByID = {modID}
                    AND status = 'closed' 
                    AND dateClose >= NOW() - INTERVAL {span}),
                    
                    (SELECT COUNT(*) 
                    FROM ticket_messages 
                    INNER JOIN tickets 
                    ON ticket_messages.modmail_messageID = tickets.messageID 
                    WHERE tickets.guildID = {guildID}
                    AND ticket_messages.authorID = {modID}
                    AND ticket_messages.type = 'Sent'
                    AND ticket_messages.date >= NOW() - INTERVAL {span}),
                    
                    (SELECT COUNT(*) 
                    FROM ticket_messages 
                    INNER JOIN tickets 
                    ON ticket_messages.modmail_messageID = tickets.messageID 
                    WHERE tickets.guildID = {guildID}
                    AND ticket_messages.authorID = {modID}
                    AND ticket_messages.type = 'Discussion'
                    AND ticket_messages.date >= NOW() - INTERVAL {span}),"""
                
        if "TOTAL" in intervals:
            query += f"""
                (SELECT COUNT(*) 
                FROM tickets 
                WHERE guildID = {guildID}
                AND closeByID = {modID} 
                AND status = 'closed'),

                (SELECT COUNT(*) 
                FROM ticket_messages 
                INNER JOIN tickets 
                ON ticket_messages.modmail_messageID = tickets.messageID 
                WHERE tickets.guildID = {guildID}
                AND ticket_messages.authorID = {modID}
                AND ticket_messages.type = 'Sent'),

                (SELECT COUNT(*) 
                FROM ticket_messages 
                INNER JOIN tickets 
                ON ticket_messages.modmail_messageID = tickets.messageID 
                WHERE tickets.guildID = {guildID}
                AND ticket_messages.authorID = {modID}
                AND ticket_messages.type = 'Discussion');"""
        else:
            # Fixes possible dangling comma
            query = query.rstrip(',') + ';'
        query_list.append(query)
    
    return query_list
