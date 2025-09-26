# MailBee 🐝

## What is this?
MailBee is a Python Discord bot built using the Discord.py library. At its core, MailBee is a customer-support ticketing application, allowing members of Discord servers to communicate with server staff. Tickets are created between a member's Direct Messages and a channel within a server, ensuring complete privacy on both ends. 

### Before you continue...
MailBee is still in development! This repository contains MailBee's public-facing code, which may be modified significantly as future updates roll out. You can expect core database, caching, and Discord gateway logic to remain consistent. (The most significant database modifications will include adding / removing single columns).

## Demos

gif here

gif here

## Self-hosting
**NOTE:** MailBee uses a MySQL 8 Database and a Valkey 8 cache. 
- MySQL 8 requires SQL compatibility (e.g. PostgreSQL, MariaDB)
- Valkey is largely equivalent to Redis.

MailBee's current database structure is templated out `here`

```
code here
```

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

## Why MailBee?
TODO

## Get in touch!
MailBee is a solo project. As such, any feedback or insight into the system is always welcomed. 

I actively maintain a private version of MailBee across several large Discord communities, and use the input from their moderation teams to shape future development goals. If you're experienced in community moderation or management, please reach out! I'd love to see how MailBee can be shaped to fit your community's needs.

**Discord:** `luciniv`

**Email:** `hello@luciniv.com`
