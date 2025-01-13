import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from db.main import get_session  # Import your actual session and engine
from config import Config  # Import your config for database settings

# Test database URL (different from your main DB)
TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{Config.POSTGRES_USER}:{Config.POSTGRES_PASSWORD}@db/test_db"
)

# Create a new async engine for testing
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,  # Disable verbose SQL logging during tests
    future=True,
    **{
        "pool_size": 5,
        "max_overflow": 5,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    },
)

# Create a session maker for the test engine
TestingSessionLocal = sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Fixture to override the database dependency
async def override_get_session() -> AsyncSession:
    async with TestingSessionLocal() as session:
        yield session


# Initialize and teardown the test database
@pytest.fixture(scope="module", autouse=True)
async def prepare_test_database():
    # Create tables in the test database
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield  # Run tests
    
    # Drop all tables after tests
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


# Apply dependency overrides
@pytest.fixture(scope="function", autouse=True)
def override_dependencies():
    from main import app  # Replace with your FastAPI app import
    app.dependency_overrides[get_session] = override_get_session


# Provide an AsyncSession fixture for direct database access in tests
@pytest.fixture
async def async_session():
    async with TestingSessionLocal() as session:
        yield session