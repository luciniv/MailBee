import discord
from typing import List


# Formats time as 0h 00m
def format_time(minutes) -> str:
    hours = int(minutes // 60) 
    remaining_minutes = int(minutes % 60)

    return f"{hours}h {remaining_minutes}m"


# Formats the data for each field, using two data items at a time
# Handles decimal and time results where needed
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
def generate_fields(data: List[int], index: int, columns: List[str]) -> List[str]:
    fields = []
    stop = index + 6
    col = 0

    while (index < stop):
        fields.append(format_data(data, index, columns[col]))
        col += 1
        index += 2
    
    return fields


def closing_queries(channelID: int):
    query = f"""
        SELECT
        (SELECT (TIMESTAMPDIFF(MINUTE, tickets_v2.dateOpen, tickets_v2.dateClose))
            FROM tickets_v2
            WHERE tickets_v2.channelID = {channelID}),
                            
        (SELECT (TIMESTAMPDIFF(MINUTE, tickets_v2.dateOpen, first_message.date))
            FROM tickets_v2
            INNER JOIN (
                SELECT ticket_messages_v2.channelID, MIN(date) AS date
                FROM ticket_messages_v2
                WHERE type = 'Sent'
                GROUP BY ticket_messages_v2.channelID
            ) AS first_message
            ON tickets_v2.channelID = first_message.channelID
            WHERE tickets_v2.channelID = {channelID});
        """
    return query


def hourly_queries(type: str, guildID: int, date: List[int], timezone: str):
    query = ""
    guild_str = ""
    timezone_val = ""

    if (timezone == "EST"):
        timezone_val = "-05:00"
    elif (timezone == "PST"):
        timezone_val = "-08:00"

    if (guildID != 0):
        guild_str = f"AND tickets.guildID = {guildID}"

    if (type == "open"):
        if (timezone == "UTC"):
            query = f"""
                SELECT 
                open_tickets.hour,
                COALESCE(open_tickets.tickets_opened, 0) AS tickets_opened,
                COALESCE(closed_tickets.tickets_closed, 0) AS tickets_closed
                FROM (
                    SELECT 
                    HOUR(dateOpen) AS hour,
                    COUNT(*) AS tickets_opened
                    FROM tickets
                    WHERE DATE(dateOpen) = DATE(CONCAT_WS('-', {date[0]}, {date[1]}, {date[2]}))
                    {guild_str}
                    GROUP BY HOUR(dateOpen)
                ) AS open_tickets
                LEFT JOIN (
                    SELECT 
                    HOUR(dateClose) AS hour,
                    COUNT(*) AS tickets_closed
                    FROM tickets
                    WHERE DATE(dateClose) = DATE(CONCAT_WS('-', {date[0]}, {date[1]}, {date[2]}))
                    {guild_str}
                    GROUP BY HOUR(dateClose)
                ) AS closed_tickets
                ON open_tickets.hour = closed_tickets.hour
                ORDER BY open_tickets.hour;"""
            
        else:
            query = f"""
                SELECT 
                open_tickets.hour,
                COALESCE(open_tickets.tickets_opened, 0) AS tickets_opened,
                COALESCE(closed_tickets.tickets_closed, 0) AS tickets_closed
                FROM (
                    SELECT 
                    HOUR(CONVERT_TZ(tickets.dateOpen, '+00:00', '{timezone_val}')) AS hour,
                    COUNT(*) AS tickets_opened
                    FROM tickets
                    WHERE DATE(CONVERT_TZ(tickets.dateOpen, '+00:00', '{timezone_val}')) = DATE(CONCAT_WS('-', {date[0]}, {date[1]}, {date[2]}))
                    {guild_str}
                    GROUP BY HOUR(CONVERT_TZ(tickets.dateOpen, '+00:00', '{timezone_val}'))
                ) AS open_tickets
                LEFT JOIN (
                    SELECT 
                    HOUR(CONVERT_TZ(tickets.dateClose, '+00:00', '{timezone_val}')) AS hour,
                    COUNT(*) AS tickets_closed
                    FROM tickets
                    WHERE DATE(CONVERT_TZ(tickets.dateClose, '+00:00', '{timezone_val}')) = DATE(CONCAT_WS('-', {date[0]}, {date[1]}, {date[2]}))
                    {guild_str}
                    GROUP BY HOUR(CONVERT_TZ(tickets.dateClose, '+00:00', '{timezone_val}'))
                ) AS closed_tickets
                ON open_tickets.hour = closed_tickets.hour
                ORDER BY open_tickets.hour;"""
            
    return query
    

def leaderboard_queries(type: str, guildID: int, interval: str):
    query = ""

    if (type == "open"):
        if (interval != "TOTAL"):
            query += f""" 
                SELECT tickets.guildID, COUNT(*) AS count
                FROM tickets
                WHERE tickets.status = 'open'
                AND tickets.dateClose >= NOW() - INTERVAL {interval}
                GROUP BY tickets.guildID
                ORDER BY count DESC;"""    
        else:
            query += f"""       
                SELECT tickets.guildID, COUNT(*) AS count
                FROM tickets
                WHERE tickets.status = 'open'
                GROUP BY tickets.guildID
                ORDER BY count DESC;"""
            
    elif (type == "duration"):
        if (interval != "TOTAL"):
            query += f""" 
                SELECT tickets.guildID, AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose)) AS avg
                FROM tickets
                WHERE tickets.status = 'closed'
                AND tickets.dateClose >= NOW() - INTERVAL {interval}
                GROUP BY tickets.guildID
                ORDER BY avg ASC;"""    
        else:
            query += f"""       
                SELECT tickets.guildID, AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose)) AS avg
                FROM tickets
                WHERE tickets.status = 'closed'
                GROUP BY tickets.guildID
                ORDER BY avg ASC;"""
            
    elif (type == "response"):
        if (interval != "TOTAL"):
            query += f""" 
                SELECT tickets.guildID, AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date)) AS avg
                FROM tickets
                INNER JOIN (
                    SELECT ticket_messages.modmail_messageID, MIN(date) AS date
                    FROM ticket_messages
                    WHERE type = 'Sent'
                    GROUP BY ticket_messages.modmail_messageID
                ) AS first_message
                ON tickets.messageID = first_message.modmail_messageID
                WHERE tickets.status = 'closed'
                AND tickets.flag = 'good'
                AND tickets.dateClose >= NOW() - INTERVAL {interval}
                GROUP BY tickets.guildID
                ORDER BY avg ASC;"""     
        else:
            query += f"""       
                SELECT tickets.guildID, AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date)) AS avg
                FROM tickets
                INNER JOIN (
                    SELECT ticket_messages.modmail_messageID, MIN(date) AS date
                    FROM ticket_messages
                    WHERE type = 'Sent'
                    GROUP BY ticket_messages.modmail_messageID
                ) AS first_message
                ON tickets.messageID = first_message.modmail_messageID
                WHERE tickets.status = 'closed'
                AND tickets.flag = 'good'
                GROUP BY tickets.guildID
                ORDER BY avg ASC;"""
            
    elif (type == "closed"):
        if (interval != "TOTAL"):
            query += f""" 
                SELECT tickets.closeByID, COUNT(*) AS count
                FROM tickets
                WHERE tickets.guildID = {guildID} 
                AND tickets.status = 'closed'
                AND tickets.dateClose >= NOW() - INTERVAL {interval}
                GROUP BY tickets.closeByID
                ORDER BY count DESC;"""   
        else:
            query += f"""       
                SELECT tickets.closeByID, COUNT(*) AS count
                FROM tickets
                WHERE tickets.guildID = {guildID} 
                AND tickets.status = 'closed'
                GROUP BY tickets.closeByID
                ORDER BY count DESC;"""
            
    elif (type == "sent"):
        if (interval != "TOTAL"):
            query += f""" 
                SELECT authorID, COUNT(*) AS count
                FROM tickets
                INNER JOIN ticket_messages 
                ON tickets.messageID = ticket_messages.modmail_messageID
                WHERE tickets.guildID = {guildID}
                AND ticket_messages.type = 'Sent'
                AND ticket_messages.date >= NOW() - INTERVAL {interval}
                GROUP BY ticket_messages.authorID
                ORDER BY count DESC;"""   
        else:
            query += f"""       
                SELECT authorID, COUNT(*) AS count
                FROM tickets
                INNER JOIN ticket_messages 
                ON tickets.messageID = ticket_messages.modmail_messageID
                WHERE tickets.guildID = {guildID}
                AND ticket_messages.type = 'Sent'
                GROUP BY ticket_messages.authorID
                ORDER BY count DESC;"""
            
    return query


# Query string for /server_stats
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


# Query string for /export_week
def week_CSV(guildIDs: List[int], weekISO: int, type_numbers: List[int]):
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
                    WHERE tickets.guildID = {guildID}
                    AND tickets.status = 'closed'),
                    
                (SELECT COUNT(*)
                    FROM tickets
                    WHERE tickets.guildID = {guildID}
                    AND YEARWEEK(tickets.dateOpen, 3) = {weekISO}),
                
                (SELECT COUNT(*)
                    FROM tickets
                    WHERE tickets.guildID = {guildID}
                    AND tickets.status = 'open'
                    AND YEARWEEK(tickets.dateOpen, 3) = {weekISO}),
                    
                (SELECT COUNT(*)
                    FROM tickets
                    WHERE tickets.guildID = {guildID}
                    AND tickets.status = 'closed'
                    AND YEARWEEK(tickets.dateOpen, 3) = {weekISO}),
                    
                (SELECT COUNT(*)
                    FROM tickets
                    WHERE tickets.guildID = {guildID}
                    AND tickets.status = 'closed'
                    AND YEARWEEK(tickets.dateClose, 3) = {weekISO}),  
                    
                (SELECT 
                    DATE(dateOpen) AS open_day
                    FROM tickets
                    WHERE tickets.guildID = {guildID}
                    AND YEARWEEK(tickets.dateOpen, 3) = {weekISO}
                    GROUP BY open_day
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),

                (SELECT 
                    DATE(dateClose) AS close_day
                    FROM tickets
                    WHERE tickets.guildID = {guildID}
                    AND YEARWEEK(tickets.dateOpen, 3) = {weekISO}
                    GROUP BY close_day
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),

                (SELECT AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, tickets.dateClose))
                    FROM tickets
                    WHERE tickets.guildID = {guildID}
                    AND tickets.status = 'closed'
                    AND YEARWEEK(tickets.dateClose, 3) = {weekISO}),
                    
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
                    AND tickets.flag = 'good'
                    AND YEARWEEK(tickets.dateOpen, 3) = {weekISO}),
                    
                (SELECT AVG(message_count)
                    FROM (
                    SELECT 
                        COUNT(ticket_messages.messageID) AS message_count
                        FROM tickets
                        INNER JOIN ticket_messages 
                        ON tickets.messageID = ticket_messages.modmail_messageID
                        WHERE tickets.guildID = {guildID}
                        AND tickets.status = 'closed'
                        AND YEARWEEK(tickets.dateClose, 3) = {weekISO}
                        GROUP BY tickets.messageID
                    ) AS ticket_counts),

                (SELECT ROUND(AVG(openerRobux), 2)
                    FROM tickets
                    WHERE tickets.guildID = {guildID}
                    AND tickets.openerRobux != '-1'
                    AND YEARWEEK(tickets.dateOpen, 3) = {weekISO}),
                    
                (SELECT ROUND(AVG(openerHours), 2)
                    FROM tickets
                    WHERE tickets.guildID = {guildID}
                    AND tickets.openerHours != '-1'
                    AND YEARWEEK(tickets.dateOpen, 3) = {weekISO}),

                (SELECT HOUR(tickets.dateOpen) AS hour_of_day
                    FROM tickets
                    WHERE tickets.guildID = {guildID}
                    AND YEARWEEK(tickets.dateOpen, 3) = {weekISO}
                    GROUP BY hour_of_day
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),
                    
                (SELECT HOUR(tickets.dateClose) AS hour_of_day
                    FROM tickets
                    WHERE tickets.guildID = {guildID} 
                    AND YEARWEEK(tickets.dateClose, 3) = {weekISO}
                    GROUP BY hour_of_day
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),
                    
                (SELECT hour_of_day
                    FROM (
                        SELECT HOUR(tickets.dateClose) AS hour_of_day, COUNT(*) AS activity_count
                        FROM tickets
                        WHERE tickets.guildID = {guildID}
                        AND tickets.dateClose IS NOT NULL
                        AND YEARWEEK(tickets.dateClose, 3) = {weekISO}
                        GROUP BY hour_of_day

                        UNION ALL

                        SELECT HOUR(ticket_messages.date) AS hour_of_day, COUNT(*) AS activity_count
                        FROM ticket_messages
                        JOIN tickets ON tickets.messageID = ticket_messages.modmail_messageID
                        WHERE tickets.guildID = {guildID}
                        AND YEARWEEK(ticket_messages.date, 3) = {weekISO}
                        AND ticket_messages.type IN ('Sent', 'Discussion')
                        GROUP BY hour_of_day
                    ) AS combined_activity
                    GROUP BY hour_of_day
                    ORDER BY SUM(activity_count) DESC
                    LIMIT 1),
                    
                (SELECT hour_of_day
                    FROM (
                        SELECT HOUR(tickets.dateClose) AS hour_of_day, COUNT(*) AS activity_count
                        FROM tickets
                        WHERE tickets.guildID = {guildID}
                        AND tickets.dateClose IS NOT NULL
                        AND YEARWEEK(tickets.dateClose, 3) = {weekISO}
                        GROUP BY hour_of_day

                        UNION ALL

                        SELECT HOUR(ticket_messages.date) AS hour_of_day, COUNT(*) AS activity_count
                        FROM ticket_messages
                        JOIN tickets ON tickets.messageID = ticket_messages.modmail_messageID
                        WHERE tickets.guildID = {guildID} 
                        AND YEARWEEK(ticket_messages.date, 3) = {weekISO}
                        AND ticket_messages.type IN ('Sent', 'Discussion')
                        GROUP BY hour_of_day
                    ) AS combined_activity
                    GROUP BY hour_of_day
                    ORDER BY SUM(activity_count) ASC
                    LIMIT 1),
                    
                (SELECT tickets.closeByID
                    FROM tickets
                    WHERE tickets.guildID = {guildID}
                    AND YEARWEEK(tickets.dateClose, 3) = {weekISO}
                    AND tickets.closeByID IS NOT NULL
                    GROUP BY tickets.closeByID
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),
                    
                (SELECT authorID
                    FROM tickets
                    INNER JOIN ticket_messages 
                    ON tickets.messageID = ticket_messages.modmail_messageID
                    WHERE tickets.guildID = {guildID}
                    AND ticket_messages.type = 'Sent'
                    AND YEARWEEK(date, 3) = {weekISO}
                    GROUP BY authorID
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),
                    
                (SELECT authorID
                    FROM tickets
                    INNER JOIN ticket_messages 
                    ON tickets.messageID = ticket_messages.modmail_messageID
                    WHERE tickets.guildID = {guildID}
                    AND ticket_messages.type = 'Discussion'
                    AND YEARWEEK(date, 3) = {weekISO}
                    GROUP BY authorID
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),
                    
                (SELECT COUNT(DISTINCT authorID) AS total_mods
                    FROM (
                    SELECT closeByID AS authorID 
                    FROM tickets 
                    WHERE tickets.guildID = {guildID}
                    AND YEARWEEK(tickets.dateClose, 3) = {weekISO}
                    UNION
                    SELECT authorID 
                    FROM tickets
                    INNER JOIN ticket_messages 
                    ON tickets.messageID = ticket_messages.modmail_messageID
                    WHERE tickets.guildID = {guildID}
                    AND (ticket_messages.type = 'Sent' OR ticket_messages.type = 'Discussion') 
                    AND YEARWEEK(ticket_messages.date, 3) = {weekISO}
                    ) AS unique_mods),"""
        
        type_queries = ""
        for num in type_numbers:
            type_queries += f"""
                (SELECT COUNT(*)
                    FROM tickets 
                    WHERE tickets.guildID = {guildID}
                    AND tickets.type = {num}
                    AND YEARWEEK(tickets.dateOpen, 3) = {weekISO}),
                
                (SELECT ROUND(AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, tickets.dateClose)), 2)
                    FROM tickets 
                    WHERE tickets.guildID = {guildID}
                    AND tickets.status = 'closed'
                    AND tickets.type = {num}
                    AND YEARWEEK(tickets.dateClose, 3) = {weekISO}),
                
                (SELECT ROUND(AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date)), 2)
                    FROM tickets
                    INNER JOIN (
                        SELECT modmail_messageID, MIN(date) AS date
                        FROM ticket_messages
                        WHERE type = 'Sent'
                        GROUP BY modmail_messageID
                    ) AS first_message
                    ON tickets.messageID = first_message.modmail_messageID
                    WHERE tickets.guildID = {guildID}
                    AND tickets.type = {num}
                    AND tickets.flag = 'good'
                    AND YEARWEEK(tickets.dateOpen, 3) = {weekISO}),"""
      
        query += type_queries
        # Fixes possible dangling comma
        query = query.rstrip(',') + ';'
        query_list.append(query)
    
    return query_list


# Query string for /server_stats_CSV
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


# Query string for /mod_activity
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


def get_mod_ids(guildID: int, intervals: List[str]):
    if "TOTAL" in intervals:
        query = f"""
            SELECT closeByID AS authorID 
            FROM tickets 
            WHERE tickets.guildID = {guildID}
            AND tickets.closeByID != NULL
            UNION
            SELECT authorID 
            FROM tickets
            INNER JOIN ticket_messages 
            ON tickets.messageID = ticket_messages.modmail_messageID
            WHERE tickets.guildID = {guildID}
            AND (ticket_messages.type = 'Sent' OR ticket_messages.type = 'Discussion');"""
    else:
        query = f"""
            SELECT closeByID AS authorID 
            FROM tickets 
            WHERE tickets.guildID = {guildID}
            AND tickets.closeByID != NULL
            AND tickets.dateClose >= NOW() - INTERVAL {intervals[0]}
            UNION
            SELECT authorID 
            FROM tickets
            INNER JOIN ticket_messages 
            ON tickets.messageID = ticket_messages.modmail_messageID
            WHERE tickets.guildID = {guildID}
            AND (ticket_messages.type = 'Sent' OR ticket_messages.type = 'Discussion')
            AND ticket_messages.date >= NOW() - INTERVAL {intervals[0]};"""
        
    return query


# Query string for /mod_activity_CSV
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
