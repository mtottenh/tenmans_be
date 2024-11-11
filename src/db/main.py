from sqlmodel import create_engine, text,  SQLModel
from sqlalchemy.ext.asyncio import AsyncEngine
from src.config import Config
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker



connect_args = {"check_same_thread": False, "timeout": 30}
engine = AsyncEngine(create_engine(url=Config.DATABASE_URL, echo=Config.DB_ECHO, connect_args=connect_args))


async def init_db():
    async with engine.connect() as connection:
        await connection.execution_options(isolation_level="AUTOCOMMIT")  # Necessary for PRAGMA statements
        await connection.execute(text("PRAGMA journal_mode=WAL;"))  # Enables WAL mode
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncSession:
    Session = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with Session() as session:
        yield session
