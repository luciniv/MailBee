import aiomysql
import asyncio
import json
import os
from datetime import datetime
import redis.asyncio as redis
from dotenv import load_dotenv
from typing import List, Dict
from utils.logger import *
from tenacity import retry, wait_random_exponential, stop_after_attempt, before_sleep


db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
db_host = os.getenv("DB_HOST")
redis_url = os.getenv("REDIS_URL")


class DataManager:
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = None
        self.access_roles = []            # Cache for access roles FIXME switch to redis
        self.monitored_channels = []      # Cache for monitored channels, will be removed for full system
        self.category_types = []          # Cache of categories to their types FIXME switch to redis
        self.types = []                   # Cache for ticket types FIXME switch to redis
        self.snip_list = []               # Cache for snip guildIDs, abbreviations, and summaries FIXME switch to redis
        self.mod_ids = {}              # Set of mod ids and names, will be removed for full system 
        self.redis_url = redis_url
        self.redis = None
        self.ticket_count = 0
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


    # Adds snip to DB
    async def add_snip(self, guildID: int, authorID: int, abbrev: str, summary: str, content: str):
        query = f"""
            INSERT INTO snips (guildID, authorID, abbrev, summary, content)
            VALUES (%s, %s, %s, %s, %s);
            """
        values = (guildID, authorID, abbrev, summary, content)
        await self.execute_query(query, False, False, values)
        await self.update_cache(4)


    # Removes snip from DB
    async def remove_snip(self, guildID: int, abbrev: str):
        query = f"""
            DELETE FROM snips WHERE 
            snips.guildID = {guildID} AND snips.abbrev = '{abbrev}';
            """
        await self.execute_query(query, False)
        await self.update_cache(4)


    # Removes snip from DB
    async def get_snip(self, guildID: int, abbrev: str):
        query = f"""
            SELECT snips.content FROM snips WHERE
            snips.guildID = {guildID} AND snips.abbrev = '{abbrev}';
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
        print("saving status")
        try:
            await self.redis.set("last_update_times", json.dumps(self.bot.channel_status.last_update_times))
            await self.redis.set("pending_updates", json.dumps(self.bot.channel_status.pending_updates))
            print("status saved")

        except Exception as e:
            logger.exception(f"Error saving status to Redis: {e}")


    # Load contents from Redis on startup
    async def load_status_dicts_from_redis(self):
        print("loading status")
        try:
            self.bot.channel_status.last_update_times = json.loads(await self.redis.get("last_update_times") or "{}")
            self.bot.channel_status.pending_updates = json.loads(await self.redis.get("pending_updates") or "{}")

            self.bot.channel_status.last_update_times = {
                int(key): int(value) for key, value 
                in self.bot.channel_status.last_update_times.items()}
            
            self.bot.channel_status.pending_updates = {
                int(key): value for key, value 
                in self.bot.channel_status.pending_updates.items()}

            print("status loaded", self.bot.channel_status.last_update_times, self.bot.channel_status.pending_updates)

        except Exception as e:
            logger.exception(f"Error loading status from Redis: {e}")


    # Save timers to Redis
    async def save_timers_to_redis(self):
        try:
            await self.redis.set("timers", json.dumps(self.bot.channel_status.timers))
            logger.debug(f"Saved timers to redis: {self.bot.channel_status.timers}")
        except Exception as e:
            logger.exception(f"Error saving timers to Redis: {e}")


    # Load timers from Redis
    async def load_timers_from_redis(self):
        try:
            self.bot.channel_status.timers = json.loads(await self.redis.get("timers") or "{}")
            self.bot.channel_status.timers = {int(key): int(value) for key, value in self.bot.channel_status.timers.items()}
            logger.success("Loaded timers from Redis:", self.bot.channel_status.timers)

        except Exception as e:
            logger.error(f"Error loading timers from Redis: {e}")


    # Save timers to Redis
    async def save_mods_to_redis(self):
        try:
            await self.redis.set("mods", json.dumps(self.bot.data_manager.mod_ids))
            logger.debug(f"Saved mod ids to redis: {self.bot.data_manager.mod_ids}")
        except Exception as e:
            logger.exception(f"Error saving mod ids to Redis: {e}")


    # Load timers from Redis
    async def load_mods_from_redis(self):
        try:
            self.bot.data_manager.mod_ids = json.loads(await self.redis.get("mods") or "{}")
            self.bot.data_manager.mod_ids = {key: int(value) for key, value in self.bot.data_manager.mod_ids.items()}
            logger.success("Loaded mod ids from Redis:", self.bot.data_manager.mod_ids)

        except Exception as e:
            logger.error(f"Error loading mod ids from Redis: {e}")


    # Add a ticket to the tickets cache, relies on channel_id
    async def add_ticket(self, channel_id: int, modmail_log_id: int):
        key = f"tickets:{channel_id}"
        try:
            # Redis hash
            await self.redis.hset(key, mapping={
                "modmail_log_id": modmail_log_id })
            logger.debug(f"Cached ticket for channel {channel_id}")

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
            logger.debug(f"Removed ticket for channel ID {channel_id}")
            return
        
        except Exception as e:
            logger.exception(f"Error removing ticket from Redis: {e}")
            return


    # Remove one ticket using modmail_message_id (cannot use key lookup)
    async def remove_ticket_modmail(self, modmail_message_id: int):
        try:
            keys = await self.redis.keys("tickets:*")
            if not keys:
                logger.warning("No tickets found in Redis")
                return

            # Iterate through keys to find the matching modmail_message_id
            for key in keys:
                ticket_data = await self.redis.hgetall(key)

                if ticket_data and int(ticket_data["modmail_log_id"]) == modmail_message_id:
                    await self.redis.delete(key)
                    logger.debug(f"Removed ticket with modmail_log_ID {modmail_message_id}")
                    return
                
            logger.info(f"No ticket found with modmail_log_ID {modmail_message_id}")

        except Exception as e:
            logger.exception(f"Error removing ticket from Redis: {e}")
            return


    # Returns a list of all channel IDs (cleaned of their Redis table name)
    async def get_all_channel_ids(self) -> List[int]:
        try:
            keys = await self.redis.keys("tickets:*")
            if not keys:
                logger.info("No tickets found in Redis")
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
                logger.info("Attempted to delete empty tickets cache")
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
                                 message_type: str):
        key = f"ticket_messages:{message_id}"
        try:
            await self.redis.hset(key, mapping={
                "modmail_messageID": modmail_message_id,
                "channelID": channel_id,
                "authorID": author_id,
                "date": date,
                "type": message_type
            })
            self.ticket_count += 1
            logger.debug(f"Added ticket message {message_id} to Redis")

            # Batch flush cache if 10 messages have collected
            if (self.ticket_count > 19):
                await self.flush_messages()
                logger.info(f"Called flush tickets")

        except Exception as e:
            logger.exception(f"Error adding ticket message to Redis: {e}")

    
    # Remove one ticket message from the cache, relies on the ticket's message_id
    async def remove_ticket_message(self, message_id: int):
        key = f"ticket_messages:{message_id}"
        try:
            await self.redis.delete(key)
            logger.debug(f"Removed ticket message of ID {message_id}")

        except Exception as e:
            logger.exception(f"Error removing ticket message from Redis: {e}")
            raise


    # Returns a list of dictionaries containing the data of each ticket message
    async def get_all_ticket_messages(self) -> List[Dict[str, str]]:
        try:
            keys = await self.redis.keys("ticket_messages:*")
            if not keys:
                logger.warning("No messages found in Redis")
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
    async def empty_messages(self):
        try:
            keys = await self.redis.keys("ticket_messages:*")
            if not keys:
                logger.info("Attempted to delete empty ticket messages cache")
                return

            for key in keys:
                await self.redis.delete(key)
            logger.success(f"Deleted {len(keys)} ticket messages from Redis")

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
                    logger.debug("Attempted to flush zero messages")
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
                logger.success(f"Flushed {len(messages_to_insert)} messages to DB")
