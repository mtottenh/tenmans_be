import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import DropTable
from sqlalchemy.ext.compiler import compiles
from sqlmodel import SQLModel
from db.main import get_session  # Import your actual session and engine
from config import Config  # Import your config for database settings

# Add CASCADE to DROP TABLE statements
@compiles(DropTable, "postgresql")
def _compile_drop_table(element, compiler, **kwargs):
    return compiler.visit_drop_table(element) + " CASCADE"

# Test database URL
TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{Config.POSTGRES_USER}:{Config.POSTGRES_PASSWORD}@db/{Config.POSTGRES_DB}"
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
@pytest_asyncio.fixture(scope="function", autouse=True)
async def prepare_test_database():
    # Drop all tables first to ensure clean state
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield
    
    # Clean up after test
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

# Provide an AsyncSession fixture for direct database access in tests
@pytest_asyncio.fixture
async def session():
    async with TestingSessionLocal() as session:
        yield session

# Apply dependency overrides
@pytest.fixture(autouse=True)
def override_dependencies():
    from main import app  # Replace with your FastAPI app import
    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.clear()

# Add admin user fixture
@pytest_asyncio.fixture
async def admin_user(session):
    from auth.models import Player, AuthType, VerificationStatus
    admin = Player(
        name="Test Admin",
        steam_id="76561197971721556",
        auth_type=AuthType.STEAM,
        verification_status=VerificationStatus.VERIFIED
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    return admin