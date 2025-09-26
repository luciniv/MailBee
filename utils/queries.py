from typing import List

import discord


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

    if data[index] is None:
        return field

    elif data[index + 1] != 0:
        local_data = data[index]
        global_data = data[index + 1]
        percentage = (local_data / global_data) * 100

        if any(word in cleaned_words for word in time_words):
            local_data = format_time(local_data)
            global_data = format_time(global_data)

        elif "average" in cleaned_words:
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

    while index < stop:
        fields.append(format_data(data, index, columns[col]))
        col += 1
        index += 2

    return fields


def closing_queries(channel_id: int):
    query = f"""
        SELECT
        (SELECT (TIMESTAMPDIFF(MINUTE, tickets_v2.dateOpen, tickets_v2.dateClose))
            FROM tickets_v2
            WHERE tickets_v2.channelID = {channel_id}),
                            
        (SELECT (TIMESTAMPDIFF(MINUTE, tickets_v2.dateOpen, first_message.date))
            FROM tickets_v2
            INNER JOIN (
                SELECT ticket_messages_v2.channelID, MIN(date) AS date
                FROM ticket_messages_v2
                WHERE type = 'Sent'
                GROUP BY ticket_messages_v2.channelID
            ) AS first_message
            ON tickets_v2.channelID = first_message.channelID
            WHERE tickets_v2.channelID = {channel_id});
        """
    return query


def hourly_queries(type: str, guild_id: int, date: List[int], timezone: str):
    query = ""
    guild_str = ""
    timezone_val = ""

    if timezone == "EST":
        timezone_val = "-05:00"
    elif timezone == "PST":
        timezone_val = "-08:00"

    if guild_id != 0:
        guild_str = f"AND tickets.guildID = {guild_id}"

    if type == "open":
        if timezone == "UTC":
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
                    WHERE DATE(dateOpen) = DATE
                    (CONCAT_WS('-', {date[0]}, {date[1]}, {date[2]}))
                    {guild_str}
                    GROUP BY HOUR(dateOpen)
                ) AS open_tickets
                LEFT JOIN (
                    SELECT 
                    HOUR(dateClose) AS hour,
                    COUNT(*) AS tickets_closed
                    FROM tickets
                    WHERE DATE(dateClose) = DATE
                    (CONCAT_WS('-', {date[0]}, {date[1]}, {date[2]}))
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
                    HOUR(CONVERT_TZ(tickets.dateOpen, '+00:00', 
                    '{timezone_val}')) AS hour,
                    COUNT(*) AS tickets_opened
                    FROM tickets
                    WHERE DATE(CONVERT_TZ(tickets.dateOpen, '+00:00', 
                    '{timezone_val}')) = DATE
                    (CONCAT_WS('-', {date[0]}, {date[1]}, {date[2]}))
                    {guild_str}
                    GROUP BY HOUR(CONVERT_TZ(tickets.dateOpen, '+00:00', 
                    '{timezone_val}'))
                ) AS open_tickets
                LEFT JOIN (
                    SELECT 
                    HOUR(CONVERT_TZ(tickets.dateClose, '+00:00', 
                    '{timezone_val}')) AS hour,
                    COUNT(*) AS tickets_closed
                    FROM tickets
                    WHERE DATE(CONVERT_TZ(tickets.dateClose, '+00:00', 
                    '{timezone_val}')) = DATE
                    (CONCAT_WS('-', {date[0]}, {date[1]}, {date[2]}))
                    {guild_str}
                    GROUP BY HOUR(CONVERT_TZ(tickets.dateClose, '+00:00', 
                    '{timezone_val}'))
                ) AS closed_tickets
                ON open_tickets.hour = closed_tickets.hour
                ORDER BY open_tickets.hour;"""

    return query


def leaderboard_queries(type: str, guild_id: int, interval: str):
    query = ""

    if type == "open":
        if interval != "TOTAL":
            query += f""" 
                SELECT tickets_v2.guildID, COUNT(*) AS count
                FROM tickets_v2
                WHERE tickets_v2.state = 'open'
                AND tickets_v2.dateClose >= NOW() - INTERVAL {interval}
                GROUP BY tickets_v2.guildID
                ORDER BY count DESC;"""
        else:
            query += f"""       
                SELECT tickets_v2.guildID, COUNT(*) AS count
                FROM tickets_v2
                WHERE tickets_v2.state = 'open'
                GROUP BY tickets_v2.guildID
                ORDER BY count DESC;"""

    elif type == "duration":
        if interval != "TOTAL":
            query += f""" 
                SELECT tickets_v2.guildID, AVG
                (TIMESTAMPDIFF(MINUTE, dateOpen, dateClose)) AS avg
                FROM tickets_v2
                WHERE tickets_v2.state = 'closed'
                AND tickets_v2.dateClose >= NOW() - INTERVAL {interval}
                GROUP BY tickets_v2.guildID
                ORDER BY avg ASC;"""
        else:
            query += f"""       
                SELECT tickets_v2.guildID, AVG
                (TIMESTAMPDIFF(MINUTE, dateOpen, dateClose)) AS avg
                FROM tickets_v2
                WHERE tickets_v2.state = 'closed'
                GROUP BY tickets_v2.guildID
                ORDER BY avg ASC;"""

    elif type == "response":
        if interval != "TOTAL":
            query += f""" 
                SELECT tickets_v2.guildID, AVG
                (TIMESTAMPDIFF(MINUTE, tickets_v2.dateOpen, first_message.date)) 
                AS avg
                FROM tickets_v2
                INNER JOIN (
                    SELECT ticket_messages_v2.channelID, MIN(date) AS date
                    FROM ticket_messages_v2
                    WHERE type = 'Sent'
                    GROUP BY ticket_messages_v2.channelID
                ) AS first_message
                ON tickets_v2.channelID = first_message.channelID
                WHERE tickets_v2.state = 'closed'
                AND tickets_v2.dateClose >= NOW() - INTERVAL {interval}
                GROUP BY tickets_v2.guildID
                ORDER BY avg ASC;"""
        else:
            query += f"""       
                SELECT tickets_v2.guildID, AVG
                (TIMESTAMPDIFF(MINUTE, tickets_v2.dateOpen, first_message.date)) 
                AS avg
                FROM tickets_v2
                INNER JOIN (
                    SELECT ticket_messages_v2.channelID, MIN(date) AS date
                    FROM ticket_messages_v2
                    WHERE type = 'Sent'
                    GROUP BY ticket_messages_v2.channelID
                ) AS first_message
                ON tickets_v2.channelID = first_message.channelID
                WHERE tickets_v2.state = 'closed'
                GROUP BY tickets_v2.guildID
                ORDER BY avg ASC;"""

    elif type == "closed":
        if interval != "TOTAL":
            query += f""" 
                SELECT tickets_v2.closerID, COUNT(*) AS count
                FROM tickets_v2
                WHERE tickets_v2.guildID = {guild_id} 
                AND tickets_v2.state = 'closed'
                AND tickets_v2.dateClose >= NOW() - INTERVAL {interval}
                GROUP BY tickets_v2.closerID
                ORDER BY count DESC;"""
        else:
            query += f"""       
                SELECT tickets_v2.closerID, COUNT(*) AS count
                FROM tickets_v2
                WHERE tickets_v2.guildID = {guild_id} 
                AND tickets_v2.state = 'closed'
                GROUP BY tickets_v2.closerID
                ORDER BY count DESC;"""

    elif type == "sent":
        if interval != "TOTAL":
            query += f""" 
                SELECT authorID, COUNT(*) AS count
                FROM tickets_v2
                INNER JOIN ticket_messages_v2
                ON tickets_v2.channelID = ticket_messages_v2.channelID
                WHERE tickets_v2.guildID = {guild_id}
                AND ticket_messages_v2.type = 'Sent'
                AND ticket_messages_v2.date >= NOW() - INTERVAL {interval}
                GROUP BY ticket_messages_v2.authorID
                ORDER BY count DESC;"""
        else:
            query += f"""       
                SELECT authorID, COUNT(*) AS count
                FROM tickets_v2
                INNER JOIN ticket_messages_v2
                ON tickets_v2.channelID = ticket_messages_v2.channelID
                WHERE tickets_v2.guildID = {guild_id}
                AND ticket_messages_v2.type = 'Sent'
                GROUP BY ticket_messages_v2.authorID
                ORDER BY count DESC;"""

    return query


# Query string for /server_stats
def server_stats(guild_id: int, intervals: List[str]):
    query = f"""
        SELECT 
        (SELECT COUNT(*)
        FROM tickets_v2
        WHERE tickets_v2.guildID = {guild_id}
        AND tickets_v2.state = 'open'),

        (SELECT COUNT(*)
        FROM tickets_v2
        WHERE tickets_v2.state = 'open'),

        (SELECT COUNT(*)
        FROM tickets_v2
        WHERE tickets_v2.guildID = {guild_id}),

        (SELECT COUNT(*)
        FROM tickets_v2),
        """

    for span in intervals:
        if span != "TOTAL":
            query += f"""
                (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
                FROM tickets_v2
                WHERE guildID = {guild_id}
                AND state = 'closed'
                AND dateClose >= NOW() - INTERVAL {span}),
                
                (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
                FROM tickets_v2
                WHERE state = 'closed'
                AND dateClose >= NOW() - INTERVAL {span}),
                    
                (SELECT AVG
                (TIMESTAMPDIFF(MINUTE, tickets_v2.dateOpen, first_message.date))
                FROM tickets_v2
                INNER JOIN (
                    SELECT channelID, MIN(date) AS date
                    FROM ticket_messages_v2
                    WHERE type = 'Sent'
                    GROUP BY channelID
                ) AS first_message
                ON tickets_v2.channelID = first_message.channelID
                WHERE tickets_v2.guildID = {guild_id}
                AND tickets_v2.state = 'closed'
                AND tickets_v2.dateClose >= NOW() - INTERVAL {span}),
                
                (SELECT AVG
                (TIMESTAMPDIFF(MINUTE, tickets_v2.dateOpen, first_message.date))
                FROM tickets_v2
                INNER JOIN (
                    SELECT channelID, MIN(date) AS date
                    FROM ticket_messages_v2
                    WHERE type = 'Sent'
                    GROUP BY channelID
                ) AS first_message
                ON tickets_v2.channelID = first_message.channelID
                WHERE tickets_v2.state = 'closed'
                AND tickets_v2.dateClose >= NOW() - INTERVAL {span}),
                
                (SELECT AVG(message_count)
                FROM (
                    SELECT 
                    COUNT(ticket_messages_v2.messageID) AS message_count
                    FROM tickets_v2
                    INNER JOIN ticket_messages_v2
                    ON tickets_v2.channelID = ticket_messages_v2.channelID
                    WHERE tickets_v2.guildID = {guild_id}
                    AND tickets_v2.state = 'closed'
                    AND tickets_v2.dateClose >= NOW() - INTERVAL {span}
                    GROUP BY tickets_v2.channelID
                ) AS ticket_counts),
                
                (SELECT AVG(message_count)
                FROM (
                    SELECT 
                    COUNT(ticket_messages_v2.messageID) AS message_count
                    FROM tickets_v2
                    INNER JOIN ticket_messages_v2
                    ON tickets_v2.channelID = ticket_messages_v2.channelID
                    WHERE tickets_v2.state = 'closed'
                    AND tickets_v2.dateClose >= NOW() - INTERVAL {span}
                    GROUP BY tickets_v2.channelID
                ) AS ticket_counts),"""

    if "TOTAL" in intervals:
        query += f"""
            (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
            FROM tickets_v2
            WHERE guildID = {guild_id}
            AND state = 'closed'),
            
            (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
            FROM tickets_v2
            WHERE state = 'closed'),
                
            (SELECT 
            AVG(TIMESTAMPDIFF(MINUTE, tickets_v2.dateOpen, first_message.date))
            FROM tickets_v2
            INNER JOIN (
                SELECT channelID, MIN(date) AS date
                FROM ticket_messages_v2
                WHERE type = 'Sent'
                GROUP BY channelID
            ) AS first_message
            ON tickets_v2.channelID = first_message.channelID
            WHERE tickets_v2.guildID = {guild_id}
            AND tickets_v2.state = 'closed'),
            
            (SELECT 
            AVG(TIMESTAMPDIFF(MINUTE, tickets_v2.dateOpen, first_message.date))
            FROM tickets_v2
            INNER JOIN (
                SELECT channelID, MIN(date) AS date
                FROM ticket_messages_v2
                WHERE type = 'Sent'
                GROUP BY channelID
            ) AS first_message
            ON tickets_v2.channelID = first_message.channelID
            WHERE tickets_v2.state = 'closed'),

            (SELECT AVG(message_count)
            FROM (
                SELECT 
                COUNT(ticket_messages_v2.messageID) AS message_count
                FROM tickets_v2
                INNER JOIN ticket_messages_v2
                ON tickets_v2.channelID = ticket_messages_v2.channelID
                WHERE tickets_v2.guildID = {guild_id}
                AND tickets_v2.state = 'closed'
                GROUP BY tickets_v2.channelID
            ) AS ticket_counts),
            
            (SELECT AVG(message_count)
            FROM (
                SELECT 
                COUNT(ticket_messages_v2.messageID) AS message_count
                FROM tickets_v2
                INNER JOIN ticket_messages_v2 
                ON tickets_v2.channelID = ticket_messages_v2.channelID
                WHERE tickets_v2.state = 'closed'
                GROUP BY tickets_v2.channelID
            ) AS ticket_counts);"""
    else:
        # Fixes possible dangling comma
        query = query.rstrip(",") + ";"

    return query


# Query string for /export_week
def week_CSV(guild_ids: List[int], week_iso: int, type_numbers: List[int]):
    query_list = []

    for guild_id in guild_ids:
        query = f"""
            SELECT
                (SELECT COUNT(*)
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.status = 'open'),
                    
                (SELECT COUNT(*)
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.status = 'closed'),
                    
                (SELECT COUNT(*)
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND YEARWEEK(tickets.dateOpen, 3) = {week_iso}),
                
                (SELECT COUNT(*)
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.status = 'open'
                    AND YEARWEEK(tickets.dateOpen, 3) = {week_iso}),
                    
                (SELECT COUNT(*)
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.status = 'closed'
                    AND YEARWEEK(tickets.dateOpen, 3) = {week_iso}),
                    
                (SELECT COUNT(*)
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.status = 'closed'
                    AND YEARWEEK(tickets.dateClose, 3) = {week_iso}),  
                    
                (SELECT 
                    DATE(dateOpen) AS open_day
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND YEARWEEK(tickets.dateOpen, 3) = {week_iso}
                    GROUP BY open_day
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),

                (SELECT 
                    DATE(dateClose) AS close_day
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND YEARWEEK(tickets.dateOpen, 3) = {week_iso}
                    GROUP BY close_day
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),

                (SELECT 
                    AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, tickets.dateClose))
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.status = 'closed'
                    AND YEARWEEK(tickets.dateClose, 3) = {week_iso}),
                    
                (SELECT 
                    AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date))
                    FROM tickets
                    INNER JOIN (
                        SELECT modmail_messageID, MIN(date) AS date
                        FROM ticket_messages
                        WHERE type = 'Sent'
                        GROUP BY modmail_messageID
                    ) AS first_message
                    ON tickets.messageID = first_message.modmail_messageID
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.flag = 'good'
                    AND YEARWEEK(tickets.dateOpen, 3) = {week_iso}),
                    
                (SELECT AVG(message_count)
                    FROM (
                    SELECT 
                        COUNT(ticket_messages.messageID) AS message_count
                        FROM tickets
                        INNER JOIN ticket_messages 
                        ON tickets.messageID = ticket_messages.modmail_messageID
                        WHERE tickets.guildID = {guild_id}
                        AND tickets.status = 'closed'
                        AND YEARWEEK(tickets.dateClose, 3) = {week_iso}
                        GROUP BY tickets.messageID
                    ) AS ticket_counts),

                (SELECT ROUND(AVG(openerRobux), 2)
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.openerRobux != '-1'
                    AND YEARWEEK(tickets.dateOpen, 3) = {week_iso}),
                    
                (SELECT ROUND(AVG(openerHours), 2)
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.openerHours != '-1'
                    AND YEARWEEK(tickets.dateOpen, 3) = {week_iso}),

                (SELECT HOUR(tickets.dateOpen) AS hour_of_day
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND YEARWEEK(tickets.dateOpen, 3) = {week_iso}
                    GROUP BY hour_of_day
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),
                    
                (SELECT HOUR(tickets.dateClose) AS hour_of_day
                    FROM tickets
                    WHERE tickets.guildID = {guild_id} 
                    AND YEARWEEK(tickets.dateClose, 3) = {week_iso}
                    GROUP BY hour_of_day
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),
                    
                (SELECT hour_of_day
                    FROM (
                        SELECT HOUR(tickets.dateClose) AS hour_of_day, 
                        COUNT(*) AS activity_count
                        FROM tickets
                        WHERE tickets.guildID = {guild_id}
                        AND tickets.dateClose IS NOT NULL
                        AND YEARWEEK(tickets.dateClose, 3) = {week_iso}
                        GROUP BY hour_of_day

                        UNION ALL

                        SELECT HOUR(ticket_messages.date) AS hour_of_day, 
                        COUNT(*) AS activity_count
                        FROM ticket_messages
                        JOIN tickets 
                        ON tickets.messageID = ticket_messages.modmail_messageID
                        WHERE tickets.guildID = {guild_id}
                        AND YEARWEEK(ticket_messages.date, 3) = {week_iso}
                        AND ticket_messages.type IN ('Sent', 'Discussion')
                        GROUP BY hour_of_day
                    ) AS combined_activity
                    GROUP BY hour_of_day
                    ORDER BY SUM(activity_count) DESC
                    LIMIT 1),
                    
                (SELECT hour_of_day
                    FROM (
                        SELECT HOUR(tickets.dateClose) AS hour_of_day, 
                        COUNT(*) AS activity_count
                        FROM tickets
                        WHERE tickets.guildID = {guild_id}
                        AND tickets.dateClose IS NOT NULL
                        AND YEARWEEK(tickets.dateClose, 3) = {week_iso}
                        GROUP BY hour_of_day

                        UNION ALL

                        SELECT HOUR(ticket_messages.date) AS hour_of_day, 
                        COUNT(*) AS activity_count
                        FROM ticket_messages
                        JOIN tickets 
                        ON tickets.messageID = ticket_messages.modmail_messageID
                        WHERE tickets.guildID = {guild_id} 
                        AND YEARWEEK(ticket_messages.date, 3) = {week_iso}
                        AND ticket_messages.type IN ('Sent', 'Discussion')
                        GROUP BY hour_of_day
                    ) AS combined_activity
                    GROUP BY hour_of_day
                    ORDER BY SUM(activity_count) ASC
                    LIMIT 1),
                    
                (SELECT tickets.closeByID
                    FROM tickets
                    WHERE tickets.guildID = {guild_id}
                    AND YEARWEEK(tickets.dateClose, 3) = {week_iso}
                    AND tickets.closeByID IS NOT NULL
                    GROUP BY tickets.closeByID
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),
                    
                (SELECT authorID
                    FROM tickets
                    INNER JOIN ticket_messages 
                    ON tickets.messageID = ticket_messages.modmail_messageID
                    WHERE tickets.guildID = {guild_id}
                    AND ticket_messages.type = 'Sent'
                    AND YEARWEEK(date, 3) = {week_iso}
                    GROUP BY authorID
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),
                    
                (SELECT authorID
                    FROM tickets
                    INNER JOIN ticket_messages 
                    ON tickets.messageID = ticket_messages.modmail_messageID
                    WHERE tickets.guildID = {guild_id}
                    AND ticket_messages.type = 'Discussion'
                    AND YEARWEEK(date, 3) = {week_iso}
                    GROUP BY authorID
                    ORDER BY COUNT(*) DESC
                    LIMIT 1),
                    
                (SELECT COUNT(DISTINCT authorID) AS total_mods
                    FROM (
                    SELECT closeByID AS authorID 
                    FROM tickets 
                    WHERE tickets.guildID = {guild_id}
                    AND YEARWEEK(tickets.dateClose, 3) = {week_iso}
                    UNION
                    SELECT authorID 
                    FROM tickets
                    INNER JOIN ticket_messages 
                    ON tickets.messageID = ticket_messages.modmail_messageID
                    WHERE tickets.guildID = {guild_id}
                    AND (ticket_messages.type IN ('Sent','Discussion')) 
                    AND YEARWEEK(ticket_messages.date, 3) = {week_iso}
                    ) AS unique_mods),"""

        type_queries = ""
        for num in type_numbers:
            type_queries += f"""
                (SELECT COUNT(*)
                    FROM tickets 
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.type = {num}
                    AND YEARWEEK(tickets.dateOpen, 3) = {week_iso}),
                
                (SELECT ROUND(AVG
                (TIMESTAMPDIFF(MINUTE, tickets.dateOpen, tickets.dateClose)), 2)
                    FROM tickets 
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.status = 'closed'
                    AND tickets.type = {num}
                    AND YEARWEEK(tickets.dateClose, 3) = {week_iso}),
                
                (SELECT ROUND(AVG
                (TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date)), 2)
                    FROM tickets
                    INNER JOIN (
                        SELECT modmail_messageID, MIN(date) AS date
                        FROM ticket_messages
                        WHERE type = 'Sent'
                        GROUP BY modmail_messageID
                    ) AS first_message
                    ON tickets.messageID = first_message.modmail_messageID
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.type = {num}
                    AND tickets.flag = 'good'
                    AND YEARWEEK(tickets.dateOpen, 3) = {week_iso}),"""

        query += type_queries
        # Fixes possible dangling comma
        query = query.rstrip(",") + ";"
        query_list.append(query)

    return query_list


async def week_CSV_v2(self, guild_id: int, week_iso: int):
    types = await self.bot.data_manager.get_types_from_db_v2(guild_id)

    main_types = {}
    subtypes_map = {}

    for t in types:
        if t["sub_type"] == -1:
            main_types[t["category_id"]] = {
                "name": t["type_name"],
                "type_ids": [t["type_id"]],
            }
        else:
            subtypes_map.setdefault(t["sub_type"], []).append(t["type_id"])

    grouped_types = []
    for category_id, info in main_types.items():
        all_ids = info["type_ids"] + subtypes_map.get(category_id, [])
        grouped_types.append((info["name"], all_ids))

    # Base query parts
    query_parts = [
        f"""
        (SELECT COUNT(*) FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND state = 'open')""",
        f"""
        (SELECT COUNT(*) FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND state = 'closed')""",
        f"""
        (SELECT COUNT(*) FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND YEARWEEK(dateOpen, 3) = {week_iso})""",
        f"""
        (SELECT COUNT(*) FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND state = 'open' 
        AND YEARWEEK(dateOpen, 3) = {week_iso})""",
        f"""
        (SELECT COUNT(*) FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND state = 'closed' 
        AND YEARWEEK(dateOpen, 3) = {week_iso})""",
        f"""
        (SELECT COUNT(*) FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND state = 'closed' 
        AND YEARWEEK(dateClose, 3) = {week_iso})""",
        f"""
        (SELECT DATE(dateOpen) FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND YEARWEEK(dateOpen, 3) = {week_iso} 
        GROUP BY DATE(dateOpen) 
        ORDER BY COUNT(*) DESC LIMIT 1)""",
        f"""
        (SELECT DATE(dateClose) FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND YEARWEEK(dateOpen, 3) = {week_iso} 
        GROUP BY DATE(dateClose) 
        ORDER BY COUNT(*) DESC LIMIT 1)""",
        f"""
        (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose)) 
        FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND state = 'closed' 
        AND YEARWEEK(dateClose, 3) = {week_iso})""",
        f"""
        (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, first_message.date)) 
        FROM tickets_v2
            INNER JOIN (
                SELECT channelID, MIN(date) AS date 
                FROM ticket_messages_v2 
                WHERE ticket_messages_v2.type = 'Sent' 
                GROUP BY channelID
            ) AS first_message ON tickets_v2.channelID = first_message.channelID
            WHERE guildID = {guild_id} AND YEARWEEK(dateOpen, 3) = {week_iso})""",
        f"""
        (SELECT AVG(message_count) 
        FROM (
            SELECT COUNT(messageID) AS message_count FROM tickets_v2
                INNER JOIN ticket_messages_v2 
                ON tickets_v2.channelID = ticket_messages_v2.channelID
                WHERE guildID = {guild_id} 
                AND state = 'closed' 
                AND YEARWEEK(dateClose, 3) = {week_iso}
                GROUP BY tickets_v2.channelID
            ) AS ticket_counts)""",
        f"""
        (SELECT ROUND(AVG(robux), 2) FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND robux != '-1' 
        AND YEARWEEK(dateOpen, 3) = {week_iso})""",
        f"""
        (SELECT ROUND(AVG(hours), 2) 
        FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND hours != '-1' 
        AND YEARWEEK(dateOpen, 3) = {week_iso})""",
        f"""
        (SELECT HOUR(dateOpen) ROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND YEARWEEK(dateOpen, 3) = {week_iso} 
        GROUP BY HOUR(dateOpen) 
        ORDER BY COUNT(*) DESC LIMIT 1)""",
        f"""
        (SELECT HOUR(dateClose) FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND YEARWEEK(dateClose, 3) = {week_iso} 
        GROUP BY HOUR(dateClose) 
        ORDER BY COUNT(*) DESC LIMIT 1)""",
        f"""
        (SELECT hour_of_day 
        FROM (
            SELECT HOUR(dateClose) AS hour_of_day, 
            COUNT(*) AS activity_count FROM tickets_v2
            WHERE guildID = {guild_id} 
            AND dateClose IS NOT NULL 
            AND YEARWEEK(dateClose, 3) = {week_iso}
            GROUP BY hour_of_day
            UNION ALL
            SELECT HOUR(date) AS hour_of_day, 
            COUNT(*) AS activity_count FROM ticket_messages_v2
                JOIN tickets_v2 ON tickets_v2.channelID = ticket_messages_v2.channelID
                WHERE guildID = {guild_id} 
                AND YEARWEEK(date, 3) = {week_iso} 
                AND ticket_messages_v2.type IN ('Sent', 'Discussion')
                GROUP BY hour_of_day
        ) AS combined_activity 
        GROUP BY hour_of_day 
        ORDER BY SUM(activity_count) DESC LIMIT 1)""",
        f"""
        (SELECT hour_of_day 
        FROM (
            SELECT HOUR(dateClose) AS hour_of_day, 
            COUNT(*) AS activity_count FROM tickets_v2
            WHERE guildID = {guild_id} 
            AND dateClose IS NOT NULL 
            AND YEARWEEK(dateClose, 3) = {week_iso}
            GROUP BY hour_of_day
            UNION ALL
            SELECT HOUR(date) AS hour_of_day, 
            COUNT(*) AS activity_count FROM ticket_messages_v2
                JOIN tickets_v2 ON tickets_v2.channelID = ticket_messages_v2.channelID
                WHERE guildID = {guild_id} 
                AND YEARWEEK(date, 3) = {week_iso} 
                AND ticket_messages_v2.type IN ('Sent', 'Discussion')
                GROUP BY hour_of_day
            ) AS combined_activity 
            GROUP BY hour_of_day 
            ORDER BY SUM(activity_count) ASC LIMIT 1)""",
        f"""
        (SELECT closerID FROM tickets_v2 
        WHERE guildID = {guild_id} 
        AND closerID IS NOT NULL 
        AND closerID != -1 
        AND YEARWEEK(dateClose, 3) = {week_iso} 
        GROUP BY closerID ORDER BY COUNT(*) DESC LIMIT 1)""",
        f"""
        (SELECT authorID FROM tickets_v2 
        INNER JOIN ticket_messages_v2 
        ON tickets_v2.channelID = ticket_messages_v2.channelID 
        WHERE guildID = {guild_id} 
        AND ticket_messages_v2.type = 'Sent' 
        AND YEARWEEK(date, 3) = {week_iso} 
        GROUP BY authorID 
        ORDER BY COUNT(*) DESC LIMIT 1)""",
        f"""
        (SELECT authorID FROM tickets_v2 
        INNER JOIN ticket_messages_v2 
        ON tickets_v2.channelID = ticket_messages_v2.channelID 
        WHERE guildID = {guild_id} 
        AND ticket_messages_v2.type = 'Discussion' 
        AND YEARWEEK(date, 3) = {week_iso} 
        GROUP BY authorID 
        ORDER BY COUNT(*) DESC LIMIT 1)""",
        f"""
        (SELECT COUNT(DISTINCT authorID) FROM (
            SELECT closerID AS authorID FROM tickets_v2 
            WHERE guildID = {guild_id} AND YEARWEEK(dateClose, 3) = {week_iso}
            UNION
            SELECT authorID FROM tickets_v2
            INNER JOIN ticket_messages_v2 
            ON tickets_v2.channelID = ticket_messages_v2.channelID
            WHERE guildID = {guild_id} 
            AND ticket_messages_v2.type IN ('Sent', 'Discussion') 
            AND YEARWEEK(date, 3) = {week_iso}
        ) AS unique_mods)""",
    ]

    headers = [
        "Server ID",
        "Total Tickets Open",
        "Total Tickets Closed",
        "Num Tickets Opened This Week",
        "Num Tickets Still Open From This Week",
        "Num Tickets Closed From This Week",
        "Total Tickets Closed This Week",
        "Day Most Tickets Opened",
        "Day Most Tickets Closed",
        "Average Ticket Duration",
        "Average First Response Time",
        "Average Messages Per Ticket Resolved",
        "Value: Average Ticket Robux",
        "Value: Average Ticket Hours",
        "Activity: Daily Time Most Tickets Opened",
        "Activity: Daily Time Most Tickets Closed",
        "Activity: Daily Time Most Mod Activity",
        "Activity: Daily Time Least Mod Activity",
        "Mod: Closed The Most Tickets",
        "Mod: Sent The Most Replies",
        "Mod: Sent The Most Discussions",
        "Mod: Num Mods Answering Tickets",
    ]

    typeid_to_name = {t["type_id"]: t["type_name"] for t in types}
    main_types_inv = {info["name"]: cid for cid, info in main_types.items()}

    for type_name, type_ids in grouped_types:
        type_ids_sql = ", ".join(str(tid) for tid in type_ids)
        query_parts.extend(
            [
                f"""
                (SELECT COUNT(*) FROM tickets_v2 
                WHERE guildID = {guild_id} 
                AND tickets_v2.type IN ({type_ids_sql}) 
                AND YEARWEEK(dateOpen, 3) = {week_iso})""",
                f"""
                (SELECT ROUND(AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose)), 2) 
                FROM tickets_v2 
                WHERE guildID = {guild_id} 
                AND state = 'closed' 
                AND tickets_v2.type IN ({type_ids_sql}) 
                AND YEARWEEK(dateClose, 3) = {week_iso})""",
                f"""
                (SELECT ROUND(
                AVG(TIMESTAMPDIFF(MINUTE, dateOpen, first_message.date)), 2) 
                FROM tickets_v2
                    INNER JOIN (
                        SELECT channelID, MIN(date) AS date 
                        FROM ticket_messages_v2 
                        WHERE ticket_messages_v2.type = 'Sent' 
                        GROUP BY channelID
                    ) AS first_message 
                    ON tickets_v2.channelID = first_message.channelID
                    WHERE guildID = {guild_id} 
                    AND tickets_v2.type IN ({type_ids_sql}) 
                    AND YEARWEEK(dateOpen, 3) = {week_iso})""",
            ]
        )
        headers.extend(
            [
                f"{type_name} Opened This Week",
                f"{type_name} Avg Duration",
                f"{type_name} Avg First Response",
            ]
        )

        subtype_ids = subtypes_map.get(main_types_inv.get(type_name, -9999), [])
        for subtype_id in subtype_ids:
            subtype_name = typeid_to_name.get(subtype_id, f"subtype_{subtype_id}")
            query_parts.extend(
                [
                    f"""
                    (SELECT COUNT(*) FROM tickets_v2 
                    WHERE guildID = {guild_id} 
                    AND tickets_v2.type = {subtype_id} 
                    AND YEARWEEK(dateOpen, 3) = {week_iso})""",
                    f"""
                    (SELECT ROUND(AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose)), 2) 
                    FROM tickets_v2 
                    WHERE guildID = {guild_id} 
                    AND state = 'closed' 
                    AND tickets_v2.type = {subtype_id} 
                    AND YEARWEEK(dateClose, 3) = {week_iso})""",
                    f"""
                    (SELECT ROUND(
                    AVG(TIMESTAMPDIFF(MINUTE, dateOpen, first_message.date)), 2) 
                    FROM tickets_v2
                        INNER JOIN (
                            SELECT channelID, MIN(date) AS date 
                            FROM ticket_messages_v2 
                            WHERE ticket_messages_v2.type = 'Sent' 
                            GROUP BY channelID
                        ) AS first_message 
                        ON tickets_v2.channelID = first_message.channelID
                        WHERE guildID = {guild_id} 
                        AND tickets_v2.type = {subtype_id} 
                        AND YEARWEEK(dateOpen, 3) = {week_iso})""",
                ]
            )
            headers.extend(
                [
                    f"{type_name} - {subtype_name} Opened This Week",
                    f"{type_name} - {subtype_name} Avg Duration",
                    f"{type_name} - {subtype_name} Avg First Response",
                ]
            )

    # Final query string
    query = "SELECT\n" + ",\n".join(query_parts) + ";"
    return query, headers


# Query string for /server_stats_CSV
def server_stats_CSV(guild_ids: List[int], intervals: List[str]):
    query_list = []

    for guild_id in guild_ids:
        query = f"""
            SELECT 
            (SELECT COUNT(*)
            FROM tickets
            WHERE tickets.guildID = {guild_id}
            AND tickets.status = 'open'),

            (SELECT COUNT(*)
            FROM tickets
            WHERE tickets.guildID = {guild_id}),
            """

        for span in intervals:
            if span != "TOTAL":
                query += f"""
                    (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
                    FROM tickets
                    WHERE guildID = {guild_id}
                    AND status = 'closed'
                    AND dateClose >= NOW() - INTERVAL {span}),
                        
                    (SELECT 
                    AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date))
                    FROM tickets
                    INNER JOIN (
                        SELECT modmail_messageID, MIN(date) AS date
                        FROM ticket_messages
                        WHERE type = 'Sent'
                        GROUP BY modmail_messageID
                    ) AS first_message
                    ON tickets.messageID = first_message.modmail_messageID
                    WHERE tickets.guildID = {guild_id}
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
                        WHERE tickets.guildID = {guild_id}
                        AND tickets.status = 'closed'
                        AND tickets.dateClose >= NOW() - INTERVAL {span}
                        GROUP BY tickets.messageID
                    ) AS ticket_counts),"""

        if "TOTAL" in intervals:
            query += f"""
                (SELECT AVG(TIMESTAMPDIFF(MINUTE, dateOpen, dateClose))
                FROM tickets
                WHERE guildID = {guild_id}
                AND status = 'closed'),
                    
                (SELECT 
                AVG(TIMESTAMPDIFF(MINUTE, tickets.dateOpen, first_message.date))
                FROM tickets
                INNER JOIN (
                    SELECT modmail_messageID, MIN(date) AS date
                    FROM ticket_messages
                    WHERE type = 'Sent'
                    GROUP BY modmail_messageID
                ) AS first_message
                ON tickets.messageID = first_message.modmail_messageID
                WHERE tickets.guildID = {guild_id}
                AND tickets.status = 'closed'
                AND tickets.flag = 'good'),

                (SELECT AVG(message_count)
                FROM (
                    SELECT 
                    COUNT(ticket_messages.messageID) AS message_count
                    FROM tickets
                    INNER JOIN ticket_messages 
                    ON tickets.messageID = ticket_messages.modmail_messageID
                    WHERE tickets.guildID = {guild_id}
                    AND tickets.guildID = tickets.status = 'closed'
                    GROUP BY tickets.messageID
                ) AS ticket_counts);"""
        else:
            # Fixes possible dangling comma
            query = query.rstrip(",") + ";"
        query_list.append(query)

    return query_list


# Query string for /mod_activity
def mod_activity(guild_id: int, closer_id: int, intervals: List[str]):
    query = "SELECT"

    for span in intervals:
        if span != "TOTAL":
            query += f"""
                (SELECT COUNT(*) 
                FROM tickets_v2
                WHERE guildID = {guild_id}
                AND closerID = {closer_id}
                AND state = 'closed' 
                AND dateClose >= NOW() - INTERVAL {span}),

                (SELECT COUNT(*) 
                FROM tickets_v2 
                WHERE guildID = {guild_id}
                AND state = 'closed' 
                AND dateClose >= NOW() - INTERVAL {span}),
            
                (SELECT COUNT(*) 
                FROM ticket_messages_v2
                INNER JOIN tickets_v2 
                ON ticket_messages_v2.channelID = tickets_v2.channelID 
                WHERE tickets_v2.guildID = {guild_id}
                AND ticket_messages_v2.authorID = {closer_id}
                AND ticket_messages_v2.type = 'Sent'
                AND ticket_messages_v2.date >= NOW() - INTERVAL {span}),

                (SELECT COUNT(*) 
                FROM ticket_messages_v2
                INNER JOIN tickets_v2 
                ON ticket_messages_v2.channelID = tickets_v2.channelID 
                WHERE tickets_v2.guildID = {guild_id}
                AND ticket_messages_v2.type = 'Sent'
                AND ticket_messages_v2.date >= NOW() - INTERVAL {span}),

                (SELECT COUNT(*) 
                FROM ticket_messages_v2
                INNER JOIN tickets_v2 
                ON ticket_messages_v2.channelID = tickets_v2.channelID
                WHERE tickets_v2.guildID = {guild_id}
                AND ticket_messages_v2.authorID = {closer_id}
                AND ticket_messages_v2.type = 'Discussion'
                AND ticket_messages_v2.date >= NOW() - INTERVAL {span}),

                (SELECT COUNT(*) 
                FROM ticket_messages_v2
                INNER JOIN tickets_v2 
                ON ticket_messages_v2.channelID = tickets_v2.channelID
                WHERE tickets_v2.guildID = {guild_id}
                AND ticket_messages_v2.type = 'Discussion'
                AND ticket_messages_v2.date >= NOW() - INTERVAL {span}),"""

    if "TOTAL" in intervals:
        query += f"""
            (SELECT COUNT(*) 
            FROM tickets_v2 
            WHERE guildID = {guild_id}
            AND closerID = {closer_id} 
            AND state = 'closed'),

            (SELECT COUNT(*) 
            FROM tickets_v2 
            WHERE guildID = {guild_id}
            AND state = 'closed'),

            (SELECT COUNT(*) 
            FROM ticket_messages_v2
            INNER JOIN tickets_v2 
            ON ticket_messages_v2.channelID = tickets_v2.channelID
            WHERE tickets_v2.guildID = {guild_id}
            AND ticket_messages_v2.authorID = {closer_id}
            AND ticket_messages_v2.type = 'Sent'),

            (SELECT COUNT(*) 
            FROM ticket_messages_v2
            INNER JOIN tickets_v2 
            ON ticket_messages_v2.channelID = tickets_v2.channelID
            WHERE tickets_v2.guildID = {guild_id}
            AND ticket_messages_v2.type = 'Sent'),

            (SELECT COUNT(*) 
            FROM ticket_messages_v2
            INNER JOIN tickets_v2 
            ON ticket_messages_v2.channelID = tickets_v2.channelID
            WHERE tickets_v2.guildID = {guild_id}
            AND ticket_messages_v2.authorID = {closer_id}
            AND ticket_messages_v2.type = 'Discussion'),

            (SELECT COUNT(*) 
            FROM ticket_messages_v2
            INNER JOIN tickets_v2 
            ON ticket_messages_v2.channelID = tickets_v2.channelID
            WHERE tickets_v2.guildID = {guild_id}
            AND ticket_messages_v2.type = 'Discussion');"""
    else:
        # Fixes possible dangling comma
        query = query.rstrip(",") + ";"

    return query


def get_mod_ids(guild_id: int, intervals: List[str]):
    if "TOTAL" in intervals:
        query = f"""
            SELECT closeByID AS authorID 
            FROM tickets 
            WHERE tickets.guildID = {guild_id}
            AND tickets.closeByID != NULL
            UNION
            SELECT authorID 
            FROM tickets
            INNER JOIN ticket_messages 
            ON tickets.messageID = ticket_messages.modmail_messageID
            WHERE tickets.guildID = {guild_id}
            AND (ticket_messages.type IN ('Sent', 'Discussion'));"""
    else:
        query = f"""
            SELECT closeByID AS authorID 
            FROM tickets 
            WHERE tickets.guildID = {guild_id}
            AND tickets.closeByID != NULL
            AND tickets.dateClose >= NOW() - INTERVAL {intervals[0]}
            UNION
            SELECT authorID 
            FROM tickets
            INNER JOIN ticket_messages 
            ON tickets.messageID = ticket_messages.modmail_messageID
            WHERE tickets.guildID = {guild_id}
            AND (ticket_messages.type = 'Sent' OR ticket_messages.type = 'Discussion')
            AND ticket_messages.date >= NOW() - INTERVAL {intervals[0]};"""

    return query


# Query string for /mod_activity_CSV
def mod_activity_CSV(guild_id: int, mod_ids: int, intervals: List[str]):
    query_list = []

    for mod_id in mod_ids:
        query = "SELECT"
        for span in intervals:
            if span != "TOTAL":
                query += f"""
                    (SELECT COUNT(*) 
                    FROM tickets 
                    WHERE guildID = {guild_id}
                    AND closeByID = {mod_id}
                    AND status = 'closed' 
                    AND dateClose >= NOW() - INTERVAL {span}),
                    
                    (SELECT COUNT(*) 
                    FROM ticket_messages 
                    INNER JOIN tickets 
                    ON ticket_messages.modmail_messageID = tickets.messageID 
                    WHERE tickets.guildID = {guild_id}
                    AND ticket_messages.authorID = {mod_id}
                    AND ticket_messages.type = 'Sent'
                    AND ticket_messages.date >= NOW() - INTERVAL {span}),
                    
                    (SELECT COUNT(*) 
                    FROM ticket_messages 
                    INNER JOIN tickets 
                    ON ticket_messages.modmail_messageID = tickets.messageID 
                    WHERE tickets.guildID = {guild_id}
                    AND ticket_messages.authorID = {mod_id}
                    AND ticket_messages.type = 'Discussion'
                    AND ticket_messages.date >= NOW() - INTERVAL {span}),"""

        if "TOTAL" in intervals:
            query += f"""
                (SELECT COUNT(*) 
                FROM tickets 
                WHERE guildID = {guild_id}
                AND closeByID = {mod_id} 
                AND status = 'closed'),

                (SELECT COUNT(*) 
                FROM ticket_messages 
                INNER JOIN tickets 
                ON ticket_messages.modmail_messageID = tickets.messageID 
                WHERE tickets.guildID = {guild_id}
                AND ticket_messages.authorID = {mod_id}
                AND ticket_messages.type = 'Sent'),

                (SELECT COUNT(*) 
                FROM ticket_messages 
                INNER JOIN tickets 
                ON ticket_messages.modmail_messageID = tickets.messageID 
                WHERE tickets.guildID = {guild_id}
                AND ticket_messages.authorID = {mod_id}
                AND ticket_messages.type = 'Discussion');"""
        else:
            # Fixes possible dangling comma
            query = query.rstrip(",") + ";"
        query_list.append(query)

    return query_list
