
import os
import oracledb
import logging
from config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    _read_pool = None
    _write_pool = None

    @classmethod
    def init_pool(cls):
        """
        Initializes separate OracleDB Session Pools for Read and Write operations.
        """
        if cls._read_pool is not None or cls._write_pool is not None:
             logger.warning("Database pools already initialized.")
             return

        try:
            user = settings.DB_USER
            password = settings.DB_PASSWORD
            dsn = settings.DB_DSN
            
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            wallet_location = os.path.join(backend_dir, 'wallet')

            logger.info(f"Initializing Parallel Database Pools (Read/Write) for user: {user}")

            # 1. READ POOL (Optimized for search/retrieval)
            cls._read_pool = oracledb.create_pool(
                user=user,
                password=password,
                dsn=dsn,
                min=max(2, settings.DB_POOL_MIN // 2),
                max=settings.DB_READ_POOL_MAX,
                increment=1,
                config_dir=wallet_location,
                wallet_location=wallet_location,
                wallet_password=password,
                getmode=oracledb.POOL_GETMODE_WAIT
            )

            # 2. WRITE POOL (Optimized for ingestion/logs)
            cls._write_pool = oracledb.create_pool(
                user=user,
                password=password,
                dsn=dsn,
                min=max(1, settings.DB_POOL_MIN // 4),
                max=settings.DB_WRITE_POOL_MAX,
                increment=1,
                config_dir=wallet_location,
                wallet_location=wallet_location,
                wallet_password=password,
                getmode=oracledb.POOL_GETMODE_WAIT
            )

            logger.info(
                f"✓ Database Pools initialized successfully.\n"
                f"  Read Pool: max={settings.DB_READ_POOL_MAX}\n"
                f"  Write Pool: max={settings.DB_WRITE_POOL_MAX}"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize Database Pools: {e}")
            raise e

    @classmethod
    def close_pool(cls):
        """
        Closes all pools. Should be called at application shutdown.
        """
        if cls._read_pool:
            cls._read_pool.close()
            cls._read_pool = None
        if cls._write_pool:
            cls._write_pool.close()
            cls._write_pool = None
        logger.info("Database Pools (Read/Write) closed.")

    @classmethod
    def get_read_connection(cls, timeout: int = 5):
        """Acquires a connection from the READ pool."""
        if cls._read_pool is None:
            cls.init_pool()
        return cls._acquire_from_pool(cls._read_pool, "READ", timeout)

    @classmethod
    def get_write_connection(cls, timeout: int = 5):
        """Acquires a connection from the WRITE pool."""
        if cls._write_pool is None:
            cls.init_pool()
        return cls._acquire_from_pool(cls._write_pool, "WRITE", timeout)

    @classmethod
    def get_connection(cls, timeout: int = 5):
        """Standard acquisition (defaults to READ for safety)."""
        return cls.get_read_connection(timeout)

    @classmethod
    def get_pool_stats(cls):
        """
        Returns statistics for both Read and Write pools.
        """
        stats = {
            "read": {"active": 0, "opened": 0, "max": settings.DB_READ_POOL_MAX},
            "write": {"active": 0, "opened": 0, "max": settings.DB_WRITE_POOL_MAX}
        }
        
        if cls._read_pool:
            stats["read"]["active"] = cls._read_pool.busy
            stats["read"]["opened"] = cls._read_pool.opened
            
        if cls._write_pool:
            stats["write"]["active"] = cls._write_pool.busy
            stats["write"]["opened"] = cls._write_pool.opened
            
        return stats

    @classmethod
    def _acquire_from_pool(cls, pool, pool_name: str, timeout: int):
        try:
            return pool.acquire()
        except Exception as e:
            if "PoolTimeout" in str(type(e)) or "timeout" in str(e).lower():
                logger.error(f"Database {pool_name} pool exhausted, wait timeout: {timeout}s")
                raise RuntimeError(f"Database {pool_name} temporarily unavailable (pool exhausted)")
            raise e

# Dependency for FastAPI routes
def get_db_connection():
    """FastAPI dependency generator. Default to Read pool."""
    connection = DatabaseManager.get_read_connection()
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

def safe_read_clob(clob_obj, max_chars: int = 10_000_000, chunk_size: int = 65_536) -> str:
    """
    Safely read CLOB-like values with a hard size cap.

    Supports three reader styles:
    1) Oracle LOB style: read(offset, amount)
    2) File-like style: read(size)
    3) Read-all style: read()
    """
    if clob_obj is None:
        return ""

    if isinstance(clob_obj, str):
        return clob_obj[:max_chars]

    read_fn = getattr(clob_obj, "read", None)
    if not callable(read_fn):
        try:
            return str(clob_obj)[:max_chars]
        except Exception:
            return ""

    # 1) Oracle LOB style reader (offset, amount)
    try:
        offset = 1  # Oracle LOB offsets are 1-based
        remaining = max_chars
        parts: list[str] = []

        while remaining > 0:
            amount = min(chunk_size, remaining)
            piece = read_fn(offset, amount)
            if not piece:
                break
            if not isinstance(piece, str):
                piece = str(piece)
            if len(piece) > remaining:
                piece = piece[:remaining]
            parts.append(piece)
            read_len = len(piece)
            if read_len <= 0:
                break
            remaining -= read_len
            offset += read_len

        text = "".join(parts)
        if text:
            return text
    except TypeError:
        # Not an Oracle-style reader; try other signatures.
        pass
    except Exception as e:
        logger.warning(f"Oracle-style CLOB read failed, falling back: {e}")

    # 2) File-like reader (size)
    try:
        remaining = max_chars
        parts: list[str] = []

        while remaining > 0:
            piece = read_fn(min(chunk_size, remaining))
            if not piece:
                break
            if not isinstance(piece, str):
                piece = str(piece)
            if len(piece) > remaining:
                piece = piece[:remaining]
            parts.append(piece)
            remaining -= len(piece)

        text = "".join(parts)
        if text:
            return text
    except TypeError:
        pass
    except Exception as e:
        logger.warning(f"Chunked CLOB read failed, falling back: {e}")

    # 3) Read-all fallback
    try:
        text = read_fn()
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)
        return text[:max_chars]
    except Exception as e:
        logger.error(f"Failed to read CLOB safely: {e}")
        return ""
