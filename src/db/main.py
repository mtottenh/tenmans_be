from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from config import Config
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
from typing import Dict

def get_postgres_config() -> Dict:
    """Get PostgreSQL-specific connection configurations."""
    return {
        # Connection pooling settings
        "pool_size": 20,  # Maximum number of connections in the pool
        "max_overflow": 10,  # Additional connections beyond pool_size
        "pool_timeout": 30,  # Timeout for acquiring connections
        "pool_recycle": 1800,  # Recycle connections after 30 minutes
        "pool_pre_ping": True,  # Enable health checks for pooled connections
    }


DB_URL= f"postgresql+asyncpg://{Config.POSTGRES_USER}:{Config.POSTGRES_PASSWORD}@db:5432/{Config.POSTGRES_DB}"
# Create async engine with PostgreSQL-specific configurations
engine = create_async_engine(
    DB_URL,
    echo=Config.DB_ECHO,
    future=True,
    **get_postgres_config()
)

# Register event listeners for connection-level settings
@event.listens_for(engine.sync_engine, "connect")
def set_postgres_session_settings(dbapi_connection, connection_record):
    """Set session-specific PostgreSQL settings."""
    cursor = dbapi_connection.cursor()
    
    # Set the search path explicitly for security
    cursor.execute("SET search_path TO public")
    
    # Enable parallel query execution
    cursor.execute("SET max_parallel_workers_per_gather = 2")
    
    # Set memory and timeout configurations
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
        await session.executeute("SET LOCAL statement_timeout = '60s'")
        await session.executeute("SET LOCAL lock_timeout = '30s'")
        
        yield session
