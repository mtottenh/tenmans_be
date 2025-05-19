import pytest
import pytest_asyncio
from httpx import AsyncClient
from main import app  # Replace with your FastAPI app module

# Fixture for test client
@pytest_asyncio.fixture
async def client():
    async with AsyncClient(base_url="http://localhost:8000") as client:
        yield client

# Test cases for authentications
class TestAuthentication:
    @pytest.mark.asyncio
    async def test_login_valid_credentials(self, client):
        response = await client.post(
            "/api/v1/auth/login/email",
            json={"email": "test@example.com", "password": "securepassword"},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client):
        response = await client.post(
            "/api/v1/auth/login/email",
            json={"email": "wrong@example.com", "password": "wrongpassword"},
        )
        assert response.status_code == 401
        assert "access_token" not in response.json()

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, client):
        response = await client.post(
            "/api/v1/auth/login/email",
            json={"email": "test@example.com"},  # Missing password
        )
        assert response.status_code == 422
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_steam_login_flow(self, client):
        response = await client.get("/api/v1/auth/login/steam")
        assert response.status_code == 200
        # Add assertions if the response has specific properties, like a redirect URL

    @pytest.mark.asyncio
    async def test_token_exchange_valid_state(self, client):
        response = await client.get(
            "/api/v1/auth/exchange-state", params={"state_id": "valid-state-id"}
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    @pytest.mark.asyncio
    async def test_token_exchange_invalid_state(self, client):
        response = await client.get(
            "/api/v1/auth/exchange-state", params={"state_id": "invalid-state-id"}
        )
        assert response.status_code == 422
        assert "detail" in response.json()