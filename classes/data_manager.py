import aiomysql
from pymysql.err import OperationalError
import asyncio
import redis.asyncio as redis
from dotenv import load_dotenv
import os
from typing import List, Dict
from utils.logger import *
from tenacity import retry, wait_random_exponential, stop_after_attempt, before_sleep


db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
db_host = os.getenv("DB_HOST")
redis_url = os.getenv("REDIS_URL")


class DataManager:
    def __init__(self):
        self.db_pool = None
        self.monitored_channels = []      # Cache for monitored channels
        self.access_roles = []            # Cache for access roles
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
    @retry(wait=wait_random_exponential(multiplier=5, min=2, max=20), 
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
                    port=3306,
                    autocommit=True
                )
                logger.success("Database connection established")

            except Exception as e:
                logger.error(f"Error connecting to database: {e}")
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
    async def execute_query(self, query: str, fetch_results: bool = True, execute_many: bool = False, content = None):
        retry = 0
        max_retries = 3

      
        print("retried goodness me oh my!")
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
            
            print("passed connection tests, creating cursor")
            async with conn.cursor() as cursor:
                if execute_many:
                    if not content or not isinstance(content, list):
                        raise ValueError("Content for 'execute_many' must be a non-empty list of tuples")
                    
                    # Begin a transaction
                    await conn.begin()  
                    print("started transaction")
                    try:
                        await cursor.executemany(query, content)
                        await conn.commit()
                        print("transaction done and good")

                    except Exception as e:
                        logger.exception(f"Error during transaction: {e}")
                        await conn.rollback()
                        raise
                else:
                    await cursor.execute(query, content)
                    if fetch_results:
                        return await cursor.fetchall()
                    return None
                
        except aiomysql.OperationalError as e:
            logger.exception(f"Operational error occurred, retrying connection: {e}")

        

        except Exception as e:
            logger.exception(f"Unhandled error during query execution: {e}")


        finally:
            print("running finally section")
            if conn is not None:
                print("conn is not none, so im releasing it just in case")
                try:
                    self.db_pool.release(conn)

                except Exception as e:
                    logger.exception(f"Failed to release connection: {e}")
                    
    
        


    # Variably controlled cache updater
    # Handles roles given permission to use Mantid and the channels Mantid monitors
    async def update_cache(self, opt: int = 2):
        if opt in (0, 2):
            query = "SELECT * FROM permissions;"
            self.access_roles = await self.execute_query(query)
            logger.debug("'access_roles' cache updated from database")

        if opt in (1, 2):
            query = "SELECT * FROM channel_monitor;"
            self.monitored_channels = await self.execute_query(query)
            logger.debug("'monitored_channels' cache updated from database")


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
            if (self.ticket_count > 2):
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
        print("FLUSH CALLED OH MY GOD")
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

                # Delete only processed keys from Redis
                for key in keys:
                    await self.redis.delete(key)

                logger.success(f"Flushed {len(messages_to_insert)} messages to DB")

            except Exception as e:
                logger.exception(f"Error during DB flush: {e}")