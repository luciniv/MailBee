# MailBee 🐝

## What is this?
MailBee is a Python Discord bot built using the Discord.py library. At its core, MailBee is a customer-support ticketing application, allowing members of Discord servers to communicate with server staff. Tickets are created between a member's Direct Messages and a channel within a server, ensuring complete privacy on both ends. 

### Before you continue...
MailBee is still in development! This repository contains MailBee's public-facing code, which may be modified significantly as future updates roll out. You can expect core database, caching, and Discord gateway logic to remain consistent. (Database modifications can be viewed via `/setup/schema.sql`).

## Demos
Users can open a ticket in their Direct Messages with MailBee. The `/create_ticket` command starts the process. 
![Opening a ticket](demo/images/ticket_create.gif)

Staff are able to view the form submissions for tickets as well as any extra messages sent from the user. The `/snip` commands enable quick sending of pre-canned ticket responses, which are also searchable.
![Replying to a ticket](demo/images/ticket_reply.gif)


## Self-hosting
**NOTE:** MailBee uses a MySQL 8 Database and a Valkey 8 cache. 
- MySQL 8 requires SQL compatibility (e.g. PostgreSQL, MariaDB)
- Valkey is largely equivalent to Redis.


1. Clone the repository
```
git clone https://github.com/luciniv/MailBee.git
cd MailBee
```

2. Install dependencies
```
pip install -r requirements.txt
```

3. Set up environment variables
Copy `.env.example` to `.env` and fill in your values:
```
DB_USER=user
DB_PASSWORD=pass
DB_NAME=name
DB_HOST=place

REDIS_URL=redis://localhost:6379/0

BOT_TOKEN=your-bot-token
```

4. Set up the database
   
Initialize with MailBee's current schema (updated on changes):
```
mysql -u root -p dbname < schema.sql
```

5. Start the cache (Redis/Valkey)
```
redis-server
```

6. Run `main.py` to start the system

MailBee will inform you of startup errors relating to files (cogs), the database, and cache

## Features
### Current:
- DM-to-server ticketing system, with standard comment and reply features
- Analytics tracking of all ticketing activity
- **AI-driven** replies, sourced from per-server context
- Fine-grain configuration of the ticketing system + user permissions
- Multi-level ticket types, enabling ticket sub-categories
- Customizable forms (Discord modals) per ticket type
- Canned ticket replies, stored as **snips**
- **Persistent ticket logs** via threads, including saved images / files
- Onymous, standard anonymous, and anonymous profile ticketing modes
- Auto-redirect ticket types for guiding users to instant answers
- Ability to edit & delete past ticket replies

### In-Progress:
- Analytics dashboard (view it's current progress here!)
- Gmail integration for conversion of emails to MailBee tickets
- And more!

## Analytics & Data Tracking
With MailBee, your personal data is **not collected**. The system does not keep message content, length, or PII (as abiding by Discord Developer ToS). Data is transformed in a meaningful way to relate message send events to ticketing activity.

#### MailBee collects the following data:
- The message's ID, channel ID, and guild ID
- Sent timestamp
- Author (ID and username)
- The *type* of message sent in tickets (comment, staff reply, user reply)

## Get in touch!
MailBee is a solo project. As such, any feedback or insight into the system is always welcomed. 

I actively maintain a private version of MailBee across several large Discord communities, and use the input from their moderation teams to shape future development goals. If you're experienced in community moderation or management, please reach out! I'd love to see how MailBee can be shaped to fit your community's needs.

**Discord:** `luciniv`

**Email:** `hello@luciniv.com`
