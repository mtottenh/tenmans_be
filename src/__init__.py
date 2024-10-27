from fastapi import FastAPI
from src.players.routes import player_router
from src.teams.routes import team_router, season_router
from contextlib import asynccontextmanager
from src.db.main import init_db


@asynccontextmanager
async def life_span(app: FastAPI):
    print(f"Server starting up.")
    await init_db()
    yield
    print(f"Server stopped.")


version = "v1"

app = FastAPI(
    title="CS2 10mans",
    description="Site for the cs210mans league",
    version=version,
    lifespan=life_span,
)

app.include_router(player_router, prefix=f"/api/{version}/players")
app.include_router(team_router, prefix=f"/api/{version}/teams" )
app.include_router(season_router, prefix=f"/api/{version}/seasons")