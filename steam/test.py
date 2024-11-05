from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from openid.consumer.consumer import Consumer, SUCCESS, FAILURE
from openid.store.memstore import MemoryStore
import re

app = FastAPI()

# Add a session middleware for user session handling
app.add_middleware(SessionMiddleware, secret_key="your_secret_key")

# Steam OpenID endpoint
STEAM_OPENID_URL = "https://steamcommunity.com/openid"

# Set up the OpenID consumer using an in-memory store
store = MemoryStore()

def get_openid_consumer():
    return Consumer({}, None)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Simple homepage with a link to log in
    if "steam_id" in request.session:
        return f"Welcome, Steam user {request.session['steam_id']}! <a href='/logout'>Logout</a>"
    else:
        return 'Welcome! <a href="/login">Login with Steam</a>'

@app.get("/login")
async def login(request: Request):
    # Set up the OpenID request for Steam authentication
    consumer = get_openid_consumer()
    openid_request = consumer.begin(STEAM_OPENID_URL)

    # Set the return URL where Steam will redirect after authentication
    return_url = request.url_for("authenticate")
    redirect_url = openid_request.redirectURL(realm=str(request.base_url), return_to=str(return_url))
    print(f"Redirect URL: {redirect_url}")
    # Redirect the user to Steam's OpenID endpoint
    
    return RedirectResponse(url=str(redirect_url))

@app.get("/authenticate")
async def authenticate(request: Request):
    # Complete the OpenID response and check the authentication status
    consumer = get_openid_consumer()
    openid_response = consumer.complete(dict(request.query_params), str(request.url_for("authenticate")))

    # If authentication succeeded
    if openid_response.status == SUCCESS:
        # Extract Steam ID from the OpenID identity URL
        steam_id_match = re.search(r"^https://steamcommunity.com/openid/id/(\d+)", openid_response.identity_url)
        if steam_id_match:
            # Store only the Steam ID in the session
            steam_id = steam_id_match.group(1)
            request.session["steam_id"] = steam_id
            return RedirectResponse(url="/")
        else:
            return HTMLResponse("Failed to retrieve Steam ID", status_code=400)
    else:
        return HTMLResponse("Authentication with Steam failed", status_code=403)

@app.get("/logout")
async def logout(request: Request):
    # Clear the session to log the user out
    request.session.pop("steam_id", None)
    return RedirectResponse(url="/")