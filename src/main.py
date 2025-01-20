from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from admin.routes import admin_router
from auth.routes import auth_router
from auth.test.routes import auth_test_router
from teams.routes import team_router
from teams.join_request.routes import team_join_request_router, global_join_request_router
from competitions.tournament.routes import tournament_router
from competitions.season.routes import season_router
from competitions.fixtures.routes import fixture_router, global_fixture_router
from upload.routes import upload_router
from maps.routes import map_router
from contextlib import asynccontextmanager
from db.main import init_db
from config import Config


@asynccontextmanager
async def life_span(app: FastAPI):
    print(f"Server starting up.")
    await init_db()
    yield
    print(f"Server stopped.")


version = Config.API_VERSION


STEAM_URLS=[
    "https://community.fastly.steamstatic.com/",
    "https://cdn.fastly.steamstatic.com/",
    "https://api.steampowered.com/",
    "https://recaptcha.net",
    "https://www.google.com/recaptcha/",
    "https://www.gstatic.cn/recaptcha/",
    "https://www.gstatic.com/recaptcha/", 
    "https://www.youtube.com/",
    "https://s.ytimg.com",
    "https://community.fastly.steamstatic.com/",
    "https://store.steampowered.com/",
    "https://checkout.steampowered.com/" ,
    "wss://community.steam-api.com/websocket/" ,
    "https://api.steampowered.com/",
    "https://login.steampowered.com/" ,
    "https://help.steampowered.com/",
    "https://steam.tv/",
    "https://steamcommunity.com/",
    "https://*.valvesoftware.com",
    "https://*.steambeta.net",
    "https://*.discovery.beta.steamserver.net",
    "https://*.steamcontent.com",
    "https://steambroadcast.akamaized.net",
    "https://steambroadcast-test.akamaized.net",
    "https://broadcast.st.dl.eccdnx.com",
    "https://lv.queniujq.cn",
    "https://steambroadcastchat.akamaized.net",
    "http://127.0.0.1:27060",
    "ws://127.0.0.1:27060",
    "https://store.steampowered.com/",
    "https://help.steampowered.com/",
    "https://login.steampowered.com/",
    "https://checkout.steampowered.com/",
    "https://www.youtube.com",
    "https://www.google.com",
    "https://sketchfab.com",
    "https://player.vimeo.com", 
    "https://medal.tv",
    "https://www.google.com/recaptcha/", 
    "https://recaptcha.net/recaptcha/",
    "https://help.steampowered.com/",
]

app = FastAPI(
    title="CS2 10mans",
    description="Site for the cs210mans league",
    version=version,
    lifespan=life_span,
)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173" ],   
                   allow_methods=["*"], 
                     allow_headers=["Authorization", "Content-Type", "Accept", 'Accept-Encoding', 'Accept-Language'],
                     allow_credentials=True)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"Incoming request: {request.method} {request.url}")
    print(f"Request headers: {dict(request.headers)}")
    
    response = await call_next(request)
    
    # Log CORS-related headers in the response
    cors_headers = {
        key: value for key, value in response.headers.items()
        if key.lower().startswith("access-control-")
    }
    print(f"CORS headers in response: {cors_headers}")
    
    return response
app.include_router(auth_router, prefix=f"/api/{version}")
app.include_router(admin_router, prefix=f"/api/{version}")
team_router.include_router(team_join_request_router)
team_router.include_router(global_join_request_router)
app.include_router(team_router, prefix=f"/api/{version}" )
app.include_router(season_router, prefix=f"/api/{version}")
tournament_router.include_router(fixture_router)
tournament_router.include_router(global_fixture_router)
app.include_router(tournament_router, prefix=f"/api/{version}")
app.include_router(upload_router, prefix=f"/api/{version}")
app.include_router(auth_test_router,  prefix=f"/api/{version}")
# TODO - Fixture router and map router currently missing.
# app.include_router(fixture_router, prefix=f"/api/{version}")
app.include_router(map_router, prefix=f"/api/{version}")

