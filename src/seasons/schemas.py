from pydantic import BaseModel

class SeasonCreateModel(BaseModel):
    name: str
