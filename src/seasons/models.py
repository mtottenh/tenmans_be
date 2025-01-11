from sqlmodel import SQLModel, Field, Column
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
import uuid
from enum import Enum

class SeasonState(Enum):
    NOT_STARTED = 1
    GROUP_STAGE = 2
    KNOCKOUT_STAGE = 3
    FINISHED = 4


class Settings(SQLModel, table=True):
    __tablename__ = "tenman_settings"
    name: str = Field(primary_key=True)
    value: str

class Season(SQLModel, table=True):
    __tablename__ = "seasons"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True)), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    name: str = Field(unique=True),
    state: SeasonState = Field(sa_column=sa.Column(sa.Enum(SeasonState)))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
