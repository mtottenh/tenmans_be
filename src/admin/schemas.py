from datetime import datetime
from pydantic import BaseModel

class RoundForfeitRequest(BaseModel):
    forfeit_notes: str

class ExtendRoundRequest(BaseModel):
    new_end_date: datetime
    reason: str

class UndoForfeitRequest(BaseModel):
    reason: str