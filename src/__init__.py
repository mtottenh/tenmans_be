from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.admin.routes import admin_router
from src.auth.routes import auth_router
from src.teams.routes import team_router

from src.competitions.season.routes import season_router

from contextlib import asynccontextmanager
from src.db.main import init_db
from src.config import Config


@asynccontextmanager
async def life_span(app: FastAPI):
    print(f"Server starting up.")
    await init_db()
    yield
    print(f"Server stopped.")


version = Config.API_VERSION

app = FastAPI(
    title="CS2 10mans",
    description="Site for the cs210mans league",
    version=version,
    lifespan=life_span,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],  allow_methods=["*"], allow_headers=['*'], allow_credentials=True)
app.include_router(auth_router, prefix=f"/api/{version}")
app.include_router(admin_router, prefix=f"/api/{version}")
# TODO - Roster endpoints are missing from team router, it should probably be it's own router/service
app.include_router(team_router, prefix=f"/api/{version}" )
app.include_router(season_router, prefix=f"/api/{version}")
# TODO - Fixture router and map router currently missing.
# app.include_router(fixture_router, prefix=f"/api/{version}")
# app.include_router(map_router, prefix=f"/api/{version}")
# TODO - Need to create a tournament router