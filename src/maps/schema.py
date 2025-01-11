from pydantic import BaseModel


class MapCreateModel(BaseModel):
    name: str


class MapRespModel(BaseModel):
    name: str
    id: str
    img: str
