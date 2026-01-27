
import os
import oracledb
import logging
from config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    _pool = None

    @classmethod
    def init_pool(cls):
        """
        Initializes the OracleDB Session Pool using settings.
        Should be called once at application startup.
        """
        if cls._pool is not None:
             logger.warning("Database pool already initialized.")
             return

        try:
            user = settings.DB_USER
            password = settings.DB_PASSWORD
            dsn = settings.DB_DSN
            
            # Locate wallet if needed (assuming it's in a standard place relative to backend)
            # Adjust path logic as per original get_database_connection
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            wallet_location = os.path.join(backend_dir, 'wallet')

            logger.info(f"Initializing Database Pool for user: {user} with DSN: {dsn}")

            cls._pool = oracledb.create_pool(
                user=user,
                password=password,
                dsn=dsn,
                min=2,
                max=20,  # Increased from 10 to 20 for better concurrency
                increment=1,
                config_dir=wallet_location,
                wallet_location=wallet_location,
                wallet_password=password
            )
            logger.info("Database Pool initialized successfully.")
            
        except Exception as e:
            logger.error(f"Failed to initialize Database Pool: {e}")
            raise e

    @classmethod
    def close_pool(cls):
        """
        Closes the pool. Should be called at application shutdown.
        """
        if cls._pool:
            cls._pool.close()
            cls._pool = None
            logger.info("Database Pool closed.")

    @classmethod
    def get_connection(cls, timeout: int = 5):
        """
        Acquires a connection from the pool with optional timeout.
        
        Args:
            timeout: Maximum seconds to wait for a connection (default: 5)
        
        RECOMMENDED USAGE (Context Manager):
            with DatabaseManager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(...)
                    
        Legacy Usage:
            conn = DatabaseManager.get_connection()
            try:
                ...
            finally:
                conn.close()
        """
        if cls._pool is None:
            raise RuntimeError("Database Pool is not initialized. Call init_pool() first.")
        
        try:
            # oracledb Pool.acquire doesn't take timeout in all versions
            # and PoolTimeout is often under oracledb.exceptions
            return cls._pool.acquire()
        except Exception as e:
            # Check for timeout in a version-agnostic way
            if "PoolTimeout" in str(type(e)) or "timeout" in str(e).lower():
                logger.error(f"Database pool exhausted, wait timeout: {timeout}s")
                raise RuntimeError(f"Database temporarily unavailable (pool exhausted, timeout: {timeout}s)")
            raise e

# Dependency for FastAPI routes
def get_db_connection():
    """
    FastAPI dependency generator.
    Usage:
        def my_route(conn = Depends(get_db_connection)):
            ...
    
    Yields a connection and ensures it is closed/returned to pool after request.
    """
    if DatabaseManager._pool is None:
         # Fallback or initialization (though init_pool should be called at startup)
         DatabaseManager.init_pool()
         
    connection = DatabaseManager.get_connection()
    try:
        yield connection
    finally:
        # Returning connection to pool
        try:
            # oracledb connection closure returns it to pool if pooled
            connection.close() 
        except Exception as e:
            logger.error(f"Error closing DB connection: {e}")

def acquire_lock(cursor, lock_name: str, timeout: int = 10):
    """
    Acquires a distributed application lock using Oracle DBMS_LOCK.
    """
    try:
        # Allocate a unique handle for the lock name
        lock_handle = cursor.var(str)
        cursor.callproc("DBMS_LOCK.ALLOCATE_UNIQUE", [lock_name, lock_handle])
        
        # Request the lock (6 = X_MODE = Exclusive, timeout in seconds)
        # Returns 0 on success, 1 on timeout
        result = cursor.callfunc("DBMS_LOCK.REQUEST", int, [lock_handle, 6, timeout, True])
        
        if result != 0:
            raise RuntimeError(f"Could not acquire lock '{lock_name}'. Result: {result}")
            
    except Exception as e:
        logger.error(f"Failed to acquire lock {lock_name}: {e}")
        raise

def safe_read_clob(clob_obj) -> str:
    """
    Safely reads a CLOB object, handling None, errors, or closed connections.
    Returns empty string on failure to prevent crashes.
    """
    if not clob_obj:
        return ""
    try:
        return clob_obj.read()
    except Exception as e:
        logger.error(f"Failed to read CLOB: {e}")
        return ""
