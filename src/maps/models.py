from sqlmodel import SQLModel, Field, Column
import sqlalchemy.dialects.sqlite as sl
from sqlalchemy_utils import UUIDType
from datetime import datetime
import uuid

class Map(SQLModel, table=True):
    __tablename__ = "maps"

    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    name: str = Field(unique=True)
    img: str = Field(nullable=True)
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    update_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
