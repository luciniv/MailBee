member_summary = """
    SELECT 
    (SELECT COUNT(*) 
    FROM tickets 
    WHERE guildID = 1217345476156985354
    AND closeByID = 429711831695753237 
    AND status = 'closed' 
    AND dateClose >= NOW() - INTERVAL 1 DAY) AS daily_closed,

    (SELECT COUNT(*) 
    FROM tickets 
    WHERE guildID = 1217345476156985354
    AND status = 'closed' 
    AND dateClose >= NOW() - INTERVAL 1 DAY) AS total_daily_closed,

    (SELECT COUNT(*) 
    FROM tickets 
    WHERE guildID = 1217345476156985354
    AND closeByID = 429711831695753237 
    AND status = 'closed' 
    AND dateClose >= NOW() - INTERVAL 7 DAY) AS weekly_closed,

    (SELECT COUNT(*) 
    FROM tickets 
    WHERE guildID = 1217345476156985354
    AND status = 'closed' 
    AND dateClose >= NOW() - INTERVAL 7 DAY) AS total_weekly_closed,

    (SELECT COUNT(*) 
    FROM tickets 
    WHERE guildID = 1217345476156985354
    AND closeByID = 429711831695753237
    AND status = 'closed' 
    AND dateClose >= NOW() - INTERVAL 1 MONTH) AS monthly_closed,

    (SELECT COUNT(*) 
    FROM tickets 
    WHERE guildID = 1217345476156985354
    AND status = 'closed' 
    AND dateClose >= NOW() - INTERVAL 1 MONTH) AS total_monthly_closed,

    (SELECT COUNT(*) 
    FROM tickets 
    WHERE guildID = 1217345476156985354
    AND closeByID = 429711831695753237 
    AND status = 'closed') AS total_closed,

    (SELECT COUNT(*) 
    FROM tickets 
    WHERE guildID = 1217345476156985354
    AND status = 'closed') AS total_closed_tickets;
"""
