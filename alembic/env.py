import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from db.main import DB_URL
# Import all models so they're available to Alembic
from auth.models import *
from audit.models import *

# Import all schemas containing StrEnums for Alembic
from admin.schemas import *
from auth.schemas import *
from audit.schemas import *
from moderation.schemas import *
from matches.schemas import *
from pugs.schemas import *
from substitutes.schemas import *
from teams.base_schemas import *
from teams.join_request.schemas import *
from competitions.base_schemas import *
from competitions.fixtures.schemas import *
from competitions.map_pool.schemas import *
from competitions.tournament.schemas import *

# Import all models
from competitions.models.fixtures import *
from competitions.models.rounds import *
from competitions.models.seasons import *
from competitions.models.tournaments import *
from competitions.models.scheduling import *
from competitions.models.lobby import *
from competitions.models.linked_tournaments import *
from competitions.map_pool.models import *
from maps.models import *
from matches.models import *
from matches.evidence.models import *
from moderation.models import *
from pugs.models import *
from substitutes.models import *
from teams.models import *
from teams.join_request.models import *
from upload.models import *
from config import Config

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option('sqlalchemy.url', DB_URL)
# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    connectable = async_engine_from_config(
        configuration=configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

def do_run_migrations(connection: Connection) -> None:

        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
