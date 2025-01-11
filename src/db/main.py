from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdapterPool
from src.config import Config
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
from typing import Dict

def get_postgres_config() -> Dict:
    """Get PostgreSQL-specific connection configurations."""
    return {
        # Connection pooling settings
        "pool_size": 20,  # Maximum number of connections in the pool
        "max_overflow": 10,  # Maximum number of connections that can be created beyond pool_size
        "pool_timeout": 30,  # Seconds to wait before giving up on getting a connection from the pool
        "pool_recycle": 1800,  # Recycle connections after 30 minutes
        "pool_pre_ping": True,  # Enable connection health checks

        # Query execution settings
        "statement_timeout": 60000,  # Maximum time (ms) any query can run (1 minute)
        "lock_timeout": 30000,  # Maximum time (ms) to wait for locks (30 seconds)
        "idle_in_transaction_session_timeout": 60000,  # Maximum time (ms) a transaction can be idle (1 minute)

        # Client-side character encoding
        "client_encoding": "utf8",

        # Time zone handling
        "timezone": "UTC",

        # Other optimizations
        "prepared_statements": False,  # Disable prepared statements for better compatibility with connection pooling
        "application_name": "cs2_10mans",  # Identify application in PostgreSQL logs
    }

# Create async engine with PostgreSQL-specific configurations
engine = create_async_engine(
    Config.DATABASE_URL,
    echo=Config.DB_ECHO,
    future=True,
    **get_postgres_config()
)

# Register event listeners for connection-level settings
@event.listens_for(engine.sync_engine, "connect")
def set_postgres_session_settings(dbapi_connection, connection_record):
    """Set session-specific PostgreSQL settings."""
    cursor = dbapi_connection.cursor()
    
    # Set search path explicitly for security
    cursor.execute("SET search_path TO public")
    
    # Enable parallel query execution where possible
    cursor.execute("SET max_parallel_workers_per_gather = 2")
    
    # Set a reasonable work memory limit per operation
    cursor.execute("SET work_mem = '16MB'")
    
    cursor.close()

async def init_db():
    """Initialize database and create all tables."""
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncSession:
    """Get a database session with optimized session settings."""
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        kwargs={
            # Session-level settings
            "isolation_level": "READ COMMITTED",  # Default isolation level
            "autoflush": False,  # Don't auto-flush for better performance
        }
    )
    
    async with async_session() as session:
        # Set session-specific timeouts
        await session.execute("SET LOCAL statement_timeout = '60s'")
        await session.execute("SET LOCAL lock_timeout = '30s'")
        
        yield session
