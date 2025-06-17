import aiomysql
import asyncio
import json
import os
import time
from datetime import datetime, timezone
import redis.asyncio as redis
from typing import List, Dict
from utils.logger import *
from tenacity import retry, wait_random_exponential, stop_after_attempt, before_sleep


db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
db_host = os.getenv("DB_HOST")
redis_url = os.getenv("REDIS_URL")

REDIS_TTL = 60 * 60 * 12  # 12 hours


class DataManager:
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = None
        self.access_roles = []            # Cache for access roles FIXME switch to redis - NOTE, did this
        self.monitored_channels = []      # Cache for monitored channels, will be removed for full system
        self.category_types = []          # Cache of categories to their types FIXME switch to redis - NOTE, did this
        self.types = []                   # Cache for ticket types FIXME switch to redis - NOTE, did this
        self.snip_list = []               # Cache for snip guildIDs, abbreviations, and summaries FIXME switch to redis MAYBE
        self.mod_ids = {}              # Set of mod ids and names, will be removed for full system 
        self.redis_url = redis_url
        self.redis = None
        self.ticket_count = 0
        self.ticket_count_v2 = 0
        self.flush_lock = asyncio.Lock()  # Initializes lock for flushing Redis


    async def log_retry(retry_state):
        logger.warning(
        f"Retrying after exception: {retry_state.outcome.exception()}\n"
        f"Next retry in {retry_state.next_action.sleep:.2f} seconds")


    # -------------------------------------------------------------------------
    # --------------------- DATABASE MANAGEMENT FUNCTIONS ---------------------
    # -------------------------------------------------------------------------

    # mySQL DB connection function, creates a single connection pool where 
    # connections are open and closed from
    @retry(wait=wait_random_exponential(multiplier=6, min=2, max=20), 
           stop=stop_after_attempt(3), 
           before_sleep=log_retry)
    async def connect_to_db(self):
        if self.db_pool is None:  
            try:
                self.db_pool = await aiomysql.create_pool(
                    user=db_user,
                    password=db_password, 
                    db=db_name,
                    host=db_host,
                    port=25060,
                    autocommit=True
                )
                logger.success("Database connection established")

            except Exception as e:
                logger.exception(f"Error connecting to database: {e}")
                raise


    # Closes DB upon bot shutdown or critical state
    async def close_db(self):
        if self.db_pool is not None:
            try:
                self.db_pool.close()
                await self.db_pool.wait_closed()
                self.db_pool = None
                logger.success("Database connection pool closed")

            except Exception as e:
                logger.error(f"Error closing database connection pool: {e}")
        

    # mySQL query executor
    @retry(wait=wait_random_exponential(multiplier=4, min=2, max=20), 
           stop=stop_after_attempt(3), 
           before_sleep=log_retry)
    async def execute_query(self, query: str, fetch_results: bool = True, execute_many: bool = False, content = None):
        result = None
        timeout = 6

        try:
            # Check if connection pool exists (again)
            if self.db_pool is None:
                logger.warning("Connection pool not found: Reconnecting...")
                await self.connect_to_db()

            conn = await self.db_pool.acquire()

            if conn is None:
                logger.warning("Connection not acquired from pool: Reconnecting...")
                await self.connect_to_db()
                conn = await self.db_pool.acquire()
            
            async with conn.cursor() as cursor:
                if execute_many:
                    if not content or not isinstance(content, list):
                        raise ValueError("Content for 'execute_many' must be a non-empty list of tuples")
                    
                    # Begin a transaction
                    await conn.begin()  
                    try:
                        await asyncio.wait_for(cursor.executemany(query, content), timeout=timeout)
                        await conn.commit()

                    except asyncio.TimeoutError:
                        await conn.rollback()
                        logger.error(f"Transaction execution timed out after {timeout} seconds")
                        raise

                    except Exception as e:
                        await conn.rollback()
                        logger.error(f"Error during transaction: {e}")
                        raise
                else:
                    try:
                        await asyncio.wait_for(cursor.execute(query, content), timeout=timeout)

                    except asyncio.TimeoutError:
                        await conn.rollback()
                        logger.error(f"Query execution timed out after {timeout} seconds")
                        raise

                    except Exception as e:
                        logger.error(f"Error during query: {e}")
                        raise

                    if fetch_results:
                        result = await cursor.fetchall()

        except Exception as e:
            logger.error(f"Unhandled error during query execution: {e}")
            raise

        finally:
            if conn is not None:
                try:
                    self.db_pool.release(conn)

                except Exception as e:
                    logger.exception(f"Failed to release connection: {e}")
        return result
    

    async def data_startup(self):
        await self.update_cache()
        # Connect to redis
        await self.connect_to_redis()

        # Pull DB data, send to redis
        # FIXME change these to expire after 5 min
        # Pull redis data to local variables
        await self.load_status_dicts_from_redis() # keep local
        await self.load_timers_from_redis() # keep local

        # NOTE this one stays, for mantid
        await self.load_mods_from_redis() 
        await self.bot.channel_status.start_worker()


    async def data_shutdown(self):
        await self.bot.channel_status.shutdown()
        await self.save_status_dicts_to_redis()
        await self.save_timers_to_redis()
        await self.save_mods_to_redis()
        await self.close_db()
        await self.close_redis()
                    

    # Variably controlled local cache updater
    # Handles locally stored and redis caches
    async def update_cache(self, opt: int = 5):
        if opt in (0, 5):
            query = "SELECT * FROM permissions;"
            self.access_roles = await self.execute_query(query)
            logger.debug("'access_roles' cache updated from database")

        if opt in (1, 5):
            query = "SELECT * FROM channel_monitor;"
            self.monitored_channels = await self.execute_query(query)
            logger.debug("'monitored_channels' cache updated from database")

        if opt in (2, 5):
            query = "SELECT * FROM category_types;"
            self.category_types = await self.execute_query(query)
            logger.debug("'category_types' cache updated from database")

        if opt in (3, 5):
            query = "SELECT * FROM types;"
            self.types = await self.execute_query(query)
            logger.debug("'types' cache updated from database")

        if opt in (4, 5):
            query = "SELECT guildID, abbrev, summary FROM snips;"
            self.snip_list = await self.execute_query(query)
            logger.debug("'snip_list' cache updated from database")
    

    # V2 FUNCTIONS BELOW -----------------------------------------


    # Load server config from the database
    async def load_config_from_db(self, guildID):
        query = f"""
            SELECT * FROM config
            WHERE guildID = {guildID};"""
        data = await self.execute_query(query)
        return data
    

    # run setup
    # 1 check for admin perms
    # 2 check db for config (specifically inbox and log)
    #   if found, check if valid (aka they exist), remake them if they dont
    #   if they do exist, just tell user setup is done (re-set perms for these channels for the default role only)
    # 3 prompt for next steps

    # edit permissions
    # add role --> change 
    

    # Add base config (guild + channels)
    async def add_config_to_db(self, guildID, logID, inboxID, responsesID, feedbackID, reportID):
        query = """
            INSERT INTO config (guildID, logID, inboxID, responsesID, feedbackID, reportID) 
            VALUES (%s, %s, %s, %s, %s, %s);
            """
        params = (guildID, logID, inboxID, responsesID, feedbackID, reportID)
        await self.execute_query(query, False, False, params)


    # get or load config to use config data
    # run database queries, re-load full config from DB (arguably easier)

    async def set_ticket_log(self, guildID, channelID):
        query = f"""
            UPDATE config
            SET logID = {channelID}
            WHERE guildID = {guildID};
        """
        await self.execute_query(query, False)

    
    async def set_ticket_inbox(self, guildID, categoryID):
        query = f"""
            UPDATE config
            SET inboxID = {categoryID}
            WHERE guildID = {guildID};
        """
        await self.execute_query(query, False)


    async def set_ticket_responses(self, guildID, channelID):
        query = f"""
            UPDATE config
            SET responsesID = {channelID}
            WHERE guildID = {guildID};
        """
        await self.execute_query(query, False)


    async def set_feedback_thread(self, guildID, threadID):
        query = f"""
            UPDATE config
            SET feedbackID = {threadID}
            WHERE guildID = {guildID};
        """
        await self.execute_query(query, False)


    async def set_report_thread(self, guildID, threadID):
        query = f"""
            UPDATE config
            SET reportID = {threadID}
            WHERE guildID = {guildID};
        """
        await self.execute_query(query, False)


    # edit config calls
    async def set_anon_status(self, guildID, anon):
        query = f"""
            UPDATE config
            SET anon = '{anon}'
            WHERE guildID = {guildID};
        """
        await self.execute_query(query, False)


    async def set_ticket_accepting(self, guildID, accepting):
        query = f"""
            UPDATE config
            SET accepting = '{accepting}'
            WHERE guildID = {guildID};
        """
        await self.execute_query(query, False)


    async def set_greeting(self, guildID, greeting):
        query = f"""
            UPDATE config
            SET greeting = %s
            WHERE guildID = {guildID};
            """
        params = (greeting)
        await self.execute_query(query, False, False, params)


    async def set_closing(self, guildID, closing):
        query = f"""
            UPDATE config
            SET closing = %s
            WHERE guildID = {guildID};
            """
        params = (closing)
        await self.execute_query(query, False, False, params)


    # Get all open tickets from database per user
    async def load_tickets_from_db(self, userID):
        query = f"""
            SELECT guildID, channelID 
            FROM tickets_v2
            WHERE openerID = {userID}
            AND state = 'open';
            """
        open_tickets = await self.execute_query(query)
        return open_tickets
    

    async def get_guild_and_log(self, channelID):
        query = f"""
            SELECT guildID, logID
            FROM tickets_v2
            WHERE channelID = {channelID};
            """
        result = await self.execute_query(query)
        return result
        

    async def get_ticket_history(self, guildID, userID):
        query = f"""
            SELECT ticketID, logID, dateOpen, dateClose, closerID, state, typeName 
            FROM tickets_v2 INNER JOIN ticket_types ON tickets_v2.type = ticket_types.typeID
            WHERE tickets_v2.guildID = {guildID}
            AND tickets_v2.openerID = {userID}
            ORDER BY dateOpen Desc;
            """
        history = await self.execute_query(query)
        return history
    

    # Create a new ticket entry in the database
    async def create_ticket(self, guildID, ticketID, channelID, memberID, threadID, typeID,
                            time_taken, robux, hours, queue = 0):
        timestamp = datetime.now(timezone.utc)
        dateOpen = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        query = f"""
            INSERT IGNORE INTO tickets_v2 (guildID, ticketID, channelID, logID, 
            dateOpen, openerID, state, type, time, robux, hours, queue) VALUES
            ({guildID},
            {ticketID},
            {channelID},
            {threadID},
            '{dateOpen}',
            {memberID},
            'open',
            {typeID},
            {time_taken},
            {robux},
            {hours},
            {queue});
            """
        await self.execute_query(query, False)
        

    # Update an open database entry as closed
    async def close_ticket(self, channelID, closeID, closeUN):
        timestamp = datetime.now(timezone.utc)
        dateClose = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        query = f"""
            UPDATE tickets_v2
            SET dateClose = '{dateClose}',
                closerID = {closeID},
                closerUN = '{closeUN}',
                state = 'closed'
            WHERE channelID = {channelID};
            """
        await self.execute_query(query, False)


    async def update_rating(self, channelID, rating):
        query = f"""
            UPDATE tickets_v2
            SET rating = %s
            WHERE channelID = {channelID};
            """
        params = (rating)
        await self.execute_query(query, False, False, params)


    # Add note to user / ticket
    # async def add_ticket_note(self, userID, token):
    #     query = f"""
    #         INSERT INTO notes VALUES
    #         ({userID},
    #         '{token}');
    #         """
    #     await self.execute_query(query, False)
    #     print("added verified user", userID, token)


    # Get a verified user from database
    async def get_verified_user_from_db(self, userID):
        query = f"""
            SELECT token FROM verified_users
            WHERE userID = {userID};
            """
        user = await self.execute_query(query)
        return user


    # Add verified user to database
    async def add_verified_user_to_db(self, userID, token):
        query = f"""
            INSERT INTO verified_users VALUES
            ({userID},
            '{token}');
            """
        await self.execute_query(query, False)


    # Get all blacklist entries from database
    async def get_all_blacklist_from_db(self, guildID):
        query = f"""
            SELECT * from blacklist
            WHERE guildID = {guildID};
            """
        blacklist = await self.execute_query(query)
        return blacklist


    # Get one blacklist entry from database
    async def get_blacklist_from_db(self, guildID, userID):
        query = f"""
            SELECT userID from blacklist
            WHERE guildID = {guildID}
            AND userID = {userID};
            """
        user = await self.execute_query(query)
        return user
    

    # Add blacklist entry
    async def add_blacklist_to_db(self, guildID, userID, reason, mod):
        epoch_time = int(time.time())

        query = """
            INSERT INTO blacklist (guildID, userID, reason, modID, modName, date) 
            VALUES (%s, %s, %s, %s, %s, %s);
            """
        params = (guildID, userID, reason, mod.id, mod.name, epoch_time)
        await self.execute_query(query, False, False, params)
    

    # Delete blacklist entry
    async def delete_blacklist_from_db(self, guildID, userID):
        query = f"""
            DELETE FROM blacklist
            WHERE guildID = {guildID}
            AND userID = {userID};
            """
        await self.execute_query(query, False)
        

    # Get ticket types from database
    async def get_types_from_db(self, guildID):
        query = f"""
            SELECT * FROM ticket_types
            WHERE guildID = {guildID}
            ORDER BY typeID ASC;
            """
        types = await self.execute_query(query)
        return types
    

    async def get_types_from_db_v2(self, guildID: int):
        query = f"""
            SELECT
                typeID, guildID, categoryID, typeName, subType
            FROM ticket_types
            WHERE guildID = {guildID};
        """
        rows = await self.execute_query(query)

        result = []
        for row in rows:
            typeID, guildID, categoryID, typeName, subType = row
            result.append({
                "typeID": typeID,
                "guildID": guildID,
                "categoryID": categoryID,
                "typeName": typeName,
                "subType": subType})

        return result


    # Add ticket type
    # Add ticket type safely with parameterized query
    async def add_type_to_db(self, guildID, categoryID, typeName, typeDescrip, typeEmoji, subType = -1):
        formJson = {
            "title": f"{typeName}",
            "fields": [
                {
                    "label": "Explain your issue in detail.",
                    "placeholder": "If you have any relevant evidence, send it in this DM channel after your ticket is created.",
                    "style": "paragraph",
                    "max_length": 1024
                }
            ]
        }

        query = """
            INSERT INTO ticket_types (guildID, categoryID, typeName, typeDescrip, typeEmoji, formJson, subType) 
            VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
        params = (
            guildID,
            categoryID,
            typeName,
            typeDescrip,
            typeEmoji,
            json.dumps(formJson),
            subType)

        await self.execute_query(query, False, False, params)


    async def set_form(self, guildID, categoryID, form=None):
        if form is None:
            form = {
                "title": "Submit Form",
                "fields": [
                    {
                        "label": "Explain your issue in detail.",
                        "placeholder": "If you have any relevant evidence, send it in this DM channel after your ticket is created.",
                        "style": "paragraph",
                        "min_length": 20,
                        "max_length": 1024,
                        "required" : True
                    }
                ]
            }

        query = """
            UPDATE ticket_types
            SET formJson = %s
            WHERE guildID = %s AND categoryID = %s;
            """
        params = (json.dumps(form), guildID, categoryID)
        await self.execute_query(query, False, False, params)


    # Delete ticket type
    async def delete_type_from_db(self, guildID, categoryID):
        query = f"""
            DELETE FROM ticket_types 
            WHERE guildID = {guildID}
            AND categoryID = {categoryID};
            """
        await self.execute_query(query, False)


    async def replace_type(self, old_categoryID, newcategoryID):
        # gpt here yeaaaaah
        pass
                             

    # on ticket create, add ticket in category based on categoryID
    # default is the inbox category
    # if category cant be found, default to inbox

    # create new type --> creates category
    # ticket stored in database with type linked via typeID (categoryID)
    # if category is deleted? 
    # pick a new category to reroute tickets to if you want, elsewise theyre now uncategorized 


    async def get_permissions_from_db(self, guildID):
        query = f"""
            SELECT roleID, permLevel FROM permissions
            WHERE guildID = {guildID};
            """
        permissions = await self.execute_query(query)
        return permissions
    

    # Add permission
    async def add_permission_to_db(self, guildID, roleID, permLevel):
        query = f"""
            INSERT INTO permissions VALUES
            ({guildID},
            {roleID},
            '{permLevel}');
            """
        await self.execute_query(query, False)
    

    # Delete permission
    async def delete_permission_from_db(self, guildID, roleID):
        query = f"""
            DELETE FROM permissions 
            WHERE guildID = {guildID}
            AND roleID = {roleID};
            """
        await self.execute_query(query, False)


    # Adds monitored channels / categories to DB
    async def add_monitor(self, guildID: int, channelID: int, type: str):
        query = f"""
            INSERT INTO channel_monitor VALUES 
            ({guildID}, 
            {channelID}, 
            '{type}');
            """
        await self.execute_query(query, False)
        await self.update_cache(1)


    # Removes monitored channels / categories from DB
    async def remove_monitor(self, channelID: int):
        query = f"""
            DELETE FROM channel_monitor WHERE 
            channel_monitor.channelID = {channelID};
            """
        await self.execute_query(query, False)
        await self.update_cache(1)


    # Query for setting category as a type in the database
    async def set_type(self, guildID: int, categoryID: int, typeID: int):
        query = f"""
            INSERT INTO category_types
            VALUES ({guildID}, {categoryID}, {typeID}) as matches
            ON DUPLICATE KEY UPDATE 
            guildID = matches.guildID,
            categoryID = matches.categoryID,
            type = matches.type;
            """
        await self.execute_query(query, False)
        await self.update_cache(2)


    # Adds verbal to DB
    async def add_note(self, messageID: int, guildID: int, userID: int, authorID: int, authorName: str, content: str):
        epoch_time = int(datetime.now(timezone.utc).timestamp())

        query = """
            INSERT INTO verbals (messageID, guildID, userID, authorID, authorName, date, content)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
        values = (messageID, guildID, userID, authorID, authorName, epoch_time, content)
        await self.execute_query(query, False, False, values)


    # Removes verbal from DB
    async def remove_note(self, messageID: int):
        query = f"""
            DELETE FROM verbals WHERE 
            verbals.messageID = {messageID};
            """
        await self.execute_query(query, False)


    # Edit verbal in DB
    async def edit_note(self, messageID: int, authorID: int, authorName: str, content: str):
        epoch_time = int(datetime.now(timezone.utc).timestamp())

        query = """
            UPDATE verbals
            SET verbals.authorID = %s, 
            verbals.authorName = %s, 
            verbals.date = %s, 
            verbals.content = %s
            WHERE verbals.messageID = %s;
            """
        params = (authorID, authorName, epoch_time, content, messageID)
        await self.execute_query(query, False, False, params)

    
    # Gets verbal from DB
    async def get_note(self, messageID: int):
        query = f"""
            SELECT * FROM verbals WHERE
            verbals.messageID = {messageID};
            """
        content = await self.execute_query(query)
        return content
    

    # Get all verbals for user from DB
    async def get_note_history(self, guildID: int, userID: int):
        query = f"""
            SELECT verbals.messageID, verbals.authorID, verbals.authorName, verbals.date, verbals.content
            FROM verbals WHERE
            verbals.guildID = {guildID} AND verbals.userID = {userID};
            """
        content = await self.execute_query(query)
        return content


    # Adds verbal to DB
    async def add_verbal(self, messageID: int, guildID: int, userID: int, authorID: int, authorName: str, content: str):
        epoch_time = int(datetime.now(timezone.utc).timestamp())

        query = """
            INSERT INTO verbals (messageID, guildID, userID, authorID, authorName, date, content)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
        values = (messageID, guildID, userID, authorID, authorName, epoch_time, content)
        await self.execute_query(query, False, False, values)


    # Removes verbal from DB
    async def remove_verbal(self, messageID: int):
        query = f"""
            DELETE FROM verbals WHERE 
            verbals.messageID = {messageID};
            """
        await self.execute_query(query, False)


    # Edit verbal in DB
    async def edit_verbal(self, messageID: int, authorID: int, authorName: str, content: str):
        epoch_time = int(datetime.now(timezone.utc).timestamp())

        query = """
            UPDATE verbals
            SET verbals.authorID = %s, 
            verbals.authorName = %s, 
            verbals.date = %s, 
            verbals.content = %s
            WHERE verbals.messageID = %s;
            """
        params = (authorID, authorName, epoch_time, content, messageID)
        await self.execute_query(query, False, False, params)

    
    # Gets verbal from DB
    async def get_verbal(self, messageID: int):
        query = f"""
            SELECT * FROM verbals WHERE
            verbals.messageID = {messageID};
            """
        content = await self.execute_query(query)
        return content
    

    # Get all verbals for user from DB
    async def get_verbal_history(self, guildID: int, userID: int):
        query = f"""
            SELECT verbals.messageID, verbals.authorID, verbals.authorName, verbals.date, verbals.content
            FROM verbals WHERE
            verbals.guildID = {guildID} AND verbals.userID = {userID};
            """
        content = await self.execute_query(query)
        return content


    # Adds snip to DB
    async def add_snip(self, guildID: int, authorID: int, abbrev: str, content: str, summary: str = "None"):
        epoch_time = int(time.time())
        query = """
            INSERT INTO snips (guildID, authorID, abbrev, summary, content, date)
            VALUES (%s, %s, %s, %s, %s, %s);
            """
        values = (guildID, authorID, abbrev, summary, content, epoch_time)
        await self.execute_query(query, False, False, values)


    # Removes snip from DB
    async def remove_snip(self, guildID: int, abbrev: str):
        query = f"""
            DELETE FROM snips WHERE 
            snips.guildID = {guildID} AND snips.abbrev = '{abbrev}';
            """
        await self.execute_query(query, False)


    # Gets snip from DB
    async def get_snip(self, guildID: int, abbrev: str):
        query = f"""
            SELECT snips.content FROM snips WHERE
            snips.guildID = {guildID} AND snips.abbrev = '{abbrev}';
            """
        content = await self.execute_query(query)
        return content


    # Get all snips from DB
    async def get_all_snips(self, guildID: int):
        query = f"""
            SELECT * FROM snips WHERE
            snips.guildID = {guildID};
            """
        content = await self.execute_query(query)
        return content


    # DB health check, not currently active
    async def check_db_health(self):
        try:
            async with self.db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    # Test connection
                    await cursor.execute("SELECT 1;")
                    await cursor.fetchall()
            logger.info("Database connection is healthy")
            return True
        
        except Exception as e:
            logger.exception(f"Database health check failed: {e}")
            return False
        

    # -------------------------------------------------------------------------
    # ---------------------- REDIS MANAGEMENT FUNCTIONS -----------------------
    # -------------------------------------------------------------------------


    async def set_with_expiry(self, key: str, value: str, expiry: int = REDIS_TTL):
        await self.redis.set(key, value, ex=expiry)


    async def hset_field_with_expiry(self, key: str, field: str, value: str, expiry: int = REDIS_TTL):
        await self.redis.hset(key, field, value)
        await self.redis.expire(key, expiry)


    async def hset_with_expiry(self, key: str, data: dict, expiry: int = REDIS_TTL):
        json_data = {field: json.dumps(value) for field, value in data.items()}
        await self.redis.hset(key, mapping=json_data)
        await self.redis.expire(key, expiry)


    # Redis connection function, creates a single connection
    async def connect_to_redis(self):
        if self.redis is None:
            try:
                self.redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
                # Test connection
                await self.redis.ping()
                logger.success("Redis cache connection established")

            except Exception as e:
                logger.error(f"Error connecting to Redis cache: {e}")


    # Closes Redis upon bot shutdown or critical state
    async def close_redis(self):
        if self.redis is not None:
            try:
                await self.redis.close()
                logger.success("Redis cache connection closed")

            except Exception as e:
                logger.error(f"Error closing Redis cache connection: {e}")


    # Save contents to Redis before shutdown
    async def save_status_dicts_to_redis(self):
        try:
            await self.redis.set("last_update_times", json.dumps(self.bot.channel_status.last_update_times))
            await self.redis.set("pending_updates", json.dumps(self.bot.channel_status.pending_updates))

        except Exception as e:
            logger.exception(f"Error saving status to Redis: {e}")


    # Load contents from Redis on startup
    async def load_status_dicts_from_redis(self):
        try:
            self.bot.channel_status.last_update_times = json.loads(await self.redis.get("last_update_times") or "{}")
            self.bot.channel_status.pending_updates = json.loads(await self.redis.get("pending_updates") or "{}")

            self.bot.channel_status.last_update_times = {
                int(key): int(value) for key, value 
                in self.bot.channel_status.last_update_times.items()}
            
            self.bot.channel_status.pending_updates = {
                int(key): value for key, value 
                in self.bot.channel_status.pending_updates.items()}

        except Exception as e:
            logger.exception(f"Error loading status from Redis: {e}")


    # Save timers to Redis
    async def save_timers_to_redis(self):
        try:
            await self.redis.set("timers", json.dumps(self.bot.channel_status.timers))
            print("TIMERS ARE", self.bot.channel_status.timers)
        except Exception as e:
            logger.exception(f"Error saving timers to Redis: {e}")


    # Load timers from Redis
    async def load_timers_from_redis(self):
        try:
            self.bot.channel_status.timers = json.loads(await self.redis.get("timers") or "{}")
            self.bot.channel_status.timers = {int(key): value for key, value in self.bot.channel_status.timers.items()}
            print("TIMERS ARE", self.bot.channel_status.timers)
        except Exception as e:
            logger.error(f"Error loading timers from Redis: {e}")


    # Save timers to Redis
    async def save_mods_to_redis(self):
        try:
            await self.redis.set("mods", json.dumps(self.bot.data_manager.mod_ids))
        except Exception as e:
            logger.exception(f"Error saving mod ids to Redis: {e}")


    # Load timers from Redis
    async def load_mods_from_redis(self):
        try:
            self.bot.data_manager.mod_ids = json.loads(await self.redis.get("mods") or "{}")
            self.bot.data_manager.mod_ids = {key: int(value) for key, value in self.bot.data_manager.mod_ids.items()}
        except Exception as e:
            logger.error(f"Error loading mod ids from Redis: {e}")

   
    # Returns the next auto-incrementing ticket ID for the given guild
    async def get_next_ticket_id(self, guildID: int) -> int:
        key = f"ticket_counter:{guildID}"
        return await self.redis.incr(key)


    def format_config(self, guildID, logID, inboxID, 
                      responsesID, feedbackID, reportID,
                      accepting, anon, blacklisted, 
                      greeting, closing, 
                      analytics, logging):
        
        if greeting is None:
            greeting = ""
        if closing is None:
            closing = ""
            
        return {
            "guildID": guildID,
            "logID": logID,
            "inboxID": inboxID,
            "responsesID": responsesID,
            "feedbackID": feedbackID,
            "reportID": reportID,
            "accepting": accepting,
            "anon": anon,
            "blacklisted": blacklisted,
            "greeting": greeting,
            "closing": closing,
            "analytics": analytics,
            "logging": logging}

    
    async def get_or_load_config(self, guildID: int, get = True):
        redis_key = f"config:{guildID}"
        if get:
            cached = await self.redis.get(redis_key)

            if cached:
                return json.loads(cached)

        config = await self.load_config_from_db(guildID)
        if not config:
            return None

        formatted = self.format_config(*config[0])
        await self.set_with_expiry(redis_key, json.dumps(formatted))
        return formatted


    # Combined load/get user tickets from Redis, with fallback to DB
    async def get_or_load_user_tickets(self, userID: int, get = True) -> list[dict]:
        redis_key = f"user_tickets:{userID}"
        if get:
            redis_key = f"user_tickets:{userID}"
            fields = await self.redis.hgetall(redis_key)

            if fields:
                return [json.loads(data) for data in fields.values()]

        db_tickets = await self.load_tickets_from_db(userID)
        if not db_tickets:
            return None

        for guildID, channelID in db_tickets:
            ticket_data = {"guildID": guildID, "channelID": channelID}
            await self.hset_field_with_expiry(redis_key, str(guildID), json.dumps(ticket_data))

        return [dict(guildID=g, channelID=c) for g, c in db_tickets]


    # Delete an open ticket from a user in a specific guild
    async def delete_user_ticket(self, userID: int, guildID: int):
        redis_key = f"user_tickets:{userID}"
        await self.redis.hdel(redis_key, str(guildID))
    

    # verified users code 
    # Lazy get or load verified user
    async def get_or_load_verified_user(self, userID: int, get = True):
        redis_key = f"verified_users:{userID}"
        if get:
            cached = await self.redis.hget(redis_key, "data")

            if cached:
                return json.loads(cached)

        user = await self.get_verified_user_from_db(userID)
        if not user:
            return None

        token = user[0]
        await self.hset_field_with_expiry(redis_key, "data", json.dumps({"token": token}))
        return {"token": token}


    # delete verified user
    async def delete_verified_user(self, userID):
        await self.delete_ver

        redis_key = f"verified_users:{userID}"
        await self.redis.delete(redis_key)


    def format_blacklist_entry(self, userID):
        return {"userID": userID}


    async def get_or_load_blacklist_entry(self, guildID: int, userID: int, get = True):
        redis_key = f"blacklist:{guildID}:{userID}"
        if get:
            cached = await self.redis.get(redis_key)

            if cached:
                return json.loads(cached)
            return None

        entry = await self.get_blacklist_from_db(guildID, userID)
        if len(entry) < 1:
            return None

        formatted = self.format_blacklist_entry(entry[0][0])
        await self.set_with_expiry(redis_key, json.dumps(formatted))
        return formatted


    async def delete_blacklist_entry(self, guildID: int, userID: int):
        # Delete from DB
        await self.delete_blacklist_from_db(guildID, userID)

        # Delete from Redis
        redis_key = f"blacklist:{guildID}:{userID}"
        await self.redis.delete(redis_key)


    def format_snip_entry(self, authorID, abbrev, summary, content, date):
        return {
            "authorID": authorID,
            "abbrev": abbrev,
            "summary": summary,
            "content": content,
            "date": date}


    async def get_or_load_snips(self, guildID, get = True):
        redis_key = f"snips:{guildID}"

        if get:
            cached = await self.redis.get(redis_key)
            if cached:
                return json.loads(cached)

        snips = await self.get_all_snips(guildID)

        if not snips:
            await self.set_with_expiry(redis_key, json.dumps([]))
            return []

        result = []
        for entry in snips:
            _, authorID, abbrev, summary, content, date = entry
            data = self.format_snip_entry(authorID, abbrev, summary, content, date)
            result.append(data)

        await self.set_with_expiry(redis_key, json.dumps(result))
        return result


    # delete snip
    async def delete_snip(self, guildID, categoryID):
        # Delete from DB
        await self.delete_type_from_db(guildID, categoryID)

        redis_key = f"ticket_types:{guildID}"
        await self.redis.hdel(redis_key, str(categoryID))


    def format_guild_type_entry(self, typeID, categoryID, typeName, typeDescrip, typeEmoji, form, subType, redirectText):
        return {
            "typeID": typeID,
            "categoryID": categoryID,
            "typeName": typeName,
            "typeDescrip": typeDescrip,
            "typeEmoji": typeEmoji,
            "form": form,
            "subType": subType,
            "redirectText": redirectText}


    async def get_or_load_guild_types(self, guildID, get = True):
        redis_key = f"ticket_types:{guildID}"

        if get:
            cached = await self.redis.get(redis_key)
            if cached:
                return json.loads(cached)

        types = await self.get_types_from_db(guildID)

        if not types:
            return []

        result = []
        for entry in types:
            typeID, _, categoryID, typeName, typeDescrip, typeEmoji, formJson, subType, redirectText = entry
            form = json.loads(formJson)
            data = self.format_guild_type_entry(typeID, categoryID, typeName, typeDescrip, typeEmoji, form, subType, redirectText)
            result.append(data)

        await self.set_with_expiry(redis_key, json.dumps(result))
        return result


    # delete guild type
    async def delete_guild_type(self, guildID, categoryID):
        # Delete from DB
        await self.delete_type_from_db(guildID, categoryID)

        redis_key = f"ticket_types:{guildID}"
        await self.redis.hdel(redis_key, str(categoryID))


    # Lazy get or load permissions for a guild
    async def get_or_load_permissions(self, guildID, get = True):
        redis_key = f"permissions:{guildID}"
        if get:
            cached = await self.redis.hgetall(redis_key)

            if cached:
                return {int(roleID): json.loads(data)["permLevel"] for roleID, data in cached.items()}

        permissions = await self.get_permissions_from_db(guildID)
        if not permissions:
            return {}

        result = {}
        for roleID, permLevel in permissions:
            data = {"permLevel": permLevel}
            await self.hset_field_with_expiry(redis_key, str(roleID), json.dumps(data))
            result[int(roleID)] = permLevel
            
        return result


    # delete permission
    async def delete_permission(self, guildID, roleID):
        # Delete from DB
        await self.delete_permission_from_db(guildID, roleID)

        redis_key = f"permissions:{guildID}"
        await self.redis.hdel(redis_key, str(roleID))


    # Add a ticket to the tickets cache, relies on channel_id
    async def add_ticket(self, channel_id: int, modmail_log_id: int):
        key = f"tickets:{channel_id}"
        try:
            # Redis hash
            await self.redis.hset(key, mapping={
                "modmail_log_id": modmail_log_id })

        except Exception as e:
            logger.exception(f"Error adding ticket to Redis: {e}")


    # Get a ticket from the cache, returns modmail_log_id (int)
    async def get_ticket(self, channel_id: int):
        key = f"tickets:{channel_id}"
        try:
            ticket_data = await self.redis.hgetall(key)
            if ticket_data:
                
                return int(ticket_data["modmail_log_id"])
            return None
        
        except Exception as e:
            logger.exception(f"Error retrieving ticket from Redis: {e}")
            return None


    # Remove one ticket from the cache, relies on channel_id
    async def remove_ticket(self, channel_id: int):
        key = f"tickets:{channel_id}"
        try:
            await self.redis.delete(key)
            return
        
        except Exception as e:
            logger.exception(f"Error removing ticket from Redis: {e}")
            return


    # Remove one ticket using modmail_message_id (cannot use key lookup)
    async def remove_ticket_modmail(self, modmail_message_id: int):
        try:
            keys = await self.redis.keys("tickets:*")
            if not keys:
                return

            # Iterate through keys to find the matching modmail_message_id
            for key in keys:
                ticket_data = await self.redis.hgetall(key)

                if ticket_data and int(ticket_data["modmail_log_id"]) == modmail_message_id:
                    await self.redis.delete(key)
                    return

        except Exception as e:
            logger.exception(f"Error removing ticket from Redis: {e}")
            return


    # Returns a list of all channel IDs (cleaned of their Redis table name)
    async def get_all_channel_ids(self) -> List[int]:
        try:
            keys = await self.redis.keys("tickets:*")
            if not keys:
                return []
            
            # Extract channel IDs from the keys
            channel_ids = [int(key.split(":")[1]) for key in keys]
            return channel_ids
        
        except Exception as e:
            logger.exception(f"Error retrieving ticket channel IDs from Redis: {e}")
            return []
        

    # Deletes all tickets (NOT REVERSIBLE)
    async def empty_tickets(self):
        try:
            keys = await self.redis.keys("tickets:*")
            if not keys:
                return

            for key in keys:
                await self.redis.delete(key)
            logger.success(f"Deleted {len(keys)} tickets from Redis")

        except Exception as e:
            logger.exception(f"Error during Redis tickets empty: {e}")
        

    # Add a ticket message to the messages cache, relies on complete ticket data
    async def add_ticket_message(self, 
                                 message_id: int, 
                                 modmail_message_id: int, 
                                 channel_id: int, 
                                 author_id: int, 
                                 date: str, 
                                 message_type: str,
                                 v2: bool = False):
        key = ""
        mapping = {}

        if v2:
            key = f"ticket_messages_v2:{message_id}"
            mapping = {
                "channelID": channel_id,
                "authorID": author_id,
                "date": date,
                "type": message_type
                }
        else:
            key = f"ticket_messages:{message_id}"
            mapping = {
                "modmail_messageID": modmail_message_id,
                "channelID": channel_id,
                "authorID": author_id,
                "date": date,
                "type": message_type
                }
        try:
            await self.redis.hset(key, mapping=mapping)
            if v2:
                self.ticket_count_v2 += 1
            else:
                self.ticket_count += 1

            # Batch flush cache if 20 messages have collected
            if (self.ticket_count > 19): 
                await self.flush_messages()

            if (self.ticket_count_v2 > 19): 
                await self.flush_messages_v2()

        except Exception as e:
            logger.exception(f"Error adding ticket message to Redis: {e}")

    
    # Remove one ticket message from the cache, relies on the ticket's message_id
    async def remove_ticket_message(self, message_id: int, v2: bool = False):
        key = f"ticket_messages:{message_id}"
        try:
            await self.redis.delete(key)

        except Exception as e:
            logger.exception(f"Error removing ticket message from Redis: {e}")
            raise


    # Returns a list of dictionaries containing the data of each ticket message
    async def get_all_ticket_messages(self) -> List[Dict[str, str]]:
        try:
            keys = await self.redis.keys("ticket_messages:*")
            if not keys:
                return []
            messages = []

            for key in keys:
                message_data = await self.redis.hgetall(key)
                if message_data:
                    # Extract message ID from the key
                    message_id = key.split(":")[1]  
                    messages.append({
                        "messageID": int(message_id),
                        "modmail_messageID": int(message_data["modmail_messageID"]),
                        "channelID": int(message_data["channelID"]),
                        "authorID": int(message_data["authorID"]),
                        "date": message_data["date"],
                        "type": message_data["type"]
                    })
            return messages
        
        except Exception as e:
            logger.exception(f"Error retrieving all ticket messages from Redis: {e}")
            return []
        

    # Deletes all ticket messages (NOT REVERSIBLE)
    async def empty_messages(self, v2: bool = False):
        try:
            keys = await self.redis.keys("ticket_messages:*")
            if not keys:
                return

            for key in keys:
                await self.redis.delete(key)
            logger.success(f"Deleted {len(keys)} ticket messages from Redis")

        except Exception as e:
            logger.exception(f"Error during Redis empty: {e}")



    # Deletes all ticket messages (NOT REVERSIBLE)
    async def empty_messages_v2(self, v2: bool = False):
        try:
            keys = await self.redis.keys("ticket_messages_v2:*")
            if not keys:
                return

            for key in keys:
                await self.redis.delete(key)
            logger.success(f"Deleted {len(keys)} ticket messages_v2 from Redis")

        except Exception as e:
            logger.exception(f"Error during Redis empty: {e}")
        

    # Copies all ticket messages to DB, then deletes them
    # Uses asyncio.Lock() to ensure another flush cannot occur before the current flush is done
    async def flush_messages(self):
        # Get the lock
        async with self.flush_lock:
            try:
                keys = await self.redis.keys("ticket_messages:*")
                if not keys:
                    return

                messages_to_insert = []
                for key in keys:
                    message = await self.redis.hgetall(key)
                    # Extract message ID from the key
                    messageID = key.split(':')[1]
                    if message:
                        messages_to_insert.append((
                            message["modmail_messageID"],
                            messageID,
                            message["channelID"],
                            message["authorID"],
                            message["date"],
                            message["type"]
                        ))

                # Attempt SQL transaction, roll back changes if any message fails to insert
                query = """
                    INSERT INTO ticket_messages (modmail_messageID, messageID, channelID, authorID, date, type)
                    VALUES (%s, %s, %s, %s, %s, %s) AS messages
                    ON DUPLICATE KEY UPDATE 
                        modmail_messageID = messages.modmail_messageID,
                        channelID = messages.channelID,
                        authorID = messages.authorID,
                        date = messages.date,
                        type = messages.type; 
                        """
                await self.execute_query(query, False, True, messages_to_insert)

            except Exception as e:
                logger.exception(f"Error during cache flush: {e}")
            else:
                # Delete only processed keys from Redis
                for key in keys:
                    await self.redis.delete(key)
                
                self.ticket_count = 0



    # Copies all ticket messages_v2 to DB, then deletes them
    # Uses asyncio.Lock() to ensure another flush cannot occur before the current flush is done
    async def flush_messages_v2(self):
        # Get the lock
        async with self.flush_lock:
            try:
                keys = await self.redis.keys("ticket_messages_v2:*")
                if not keys:
                    logger.debug("Attempted to flush zero v2 messages")
                    return

                messages_to_insert = []
                for key in keys:
                    message = await self.redis.hgetall(key)
                    # Extract message ID from the key
                    messageID = key.split(':')[1]
                    if message:
                        messages_to_insert.append((
                            message["channelID"],
                            messageID,
                            message["authorID"],
                            message["date"],
                            message["type"]
                        ))

                # Attempt SQL transaction, roll back changes if any message fails to insert
                query = """
                        INSERT INTO ticket_messages_v2 (channelID, messageID, authorID, date, type)
                        VALUES (%s, %s, %s, %s, %s) AS messages
                        ON DUPLICATE KEY UPDATE 
                            channelID = messages.channelID,
                            authorID = messages.authorID,
                            date = messages.date,
                            type = messages.type; 
                            """
                await self.execute_query(query, False, True, messages_to_insert)
                
            except Exception as e:
                logger.exception(f"Error during v2 cache flush: {e}")
            else:
                # Delete only processed keys from Redis
                for key in keys:
                    await self.redis.delete(key)

                self.ticket_count_v2 = 0
