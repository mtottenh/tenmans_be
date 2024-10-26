from sqlmodel import SQLModel, Field, Column
import sqlalchemy.dialects.sqlite as sl
from sqlalchemy_utils import UUIDType
from datetime import datetime
import uuid

class Player(SQLModel, table=True):
    __tablename__ = "players"

    uid: uuid.UUID = Field(
        sa_column=Column(
            UUIDType,
            nullable=False,
            primary_key=True,
            default=uuid.uuid4
        )
    )
    name: str
    SteamID: str
    email: str
    is_verified: bool = False
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    update_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))

    def __repr__(self):
        return f"<Player {self.name}>"