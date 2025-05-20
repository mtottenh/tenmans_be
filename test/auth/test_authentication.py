import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from auth.schemas import AuthType, PlayerEmailCreate, PlayerStatus
from main import app
from services.auth import auth_service


# Fixture for test client
@pytest.fixture
def client():
    return TestClient(app)


# Test cases for authentications
class TestAuthentication:
    def test_login_valid_credentials(self, client, test_players, session, monkeypatch):
        # Create a test user with known credentials if needed
        async def mock_authenticate(*args, **kwargs):
            return test_players["regular_user"], "mock_token"
        
        # Patch the authenticate method
        import auth.service.auth
        monkeypatch.setattr(auth.service.auth, "authenticate_email", mock_authenticate)
        
        response = client.post(
            "/api/v1/auth/login/email",
            json={"email": "regular_user@gmail.com", "password": "abcdefgg1234"},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_login_invalid_credentials(self, client, monkeypatch):
        # Mock authentication failure
        async def mock_authenticate_fail(*args, **kwargs):
            return None, None
        
        # Patch the authenticate method
        import auth.service.auth
        monkeypatch.setattr(auth.service.auth, "authenticate_email", mock_authenticate_fail)
        
        response = client.post(
            "/api/v1/auth/login/email",
            json={"email": "wrong@example.com", "password": "wrongpassword"},
        )
        assert response.status_code == 401
        assert "detail" in response.json()

    def test_login_missing_fields(self, client):
        response = client.post(
            "/api/v1/auth/login/email",
            json={"email": "test@example.com"},  # Missing password
        )
        assert response.status_code == 422
        assert "detail" in response.json()

    def test_steam_login_flow(self, client):
        response = client.get("/api/v1/auth/login/steam")
        assert response.status_code in [200, 307]  # 307 for redirects

    def test_token_exchange_valid_state(self, client, monkeypatch):
        # Mock successful token exchange
        async def mock_exchange(*args, **kwargs):
            return "mock_token"
        
        # Patch the exchange method
        import auth.service.token
        monkeypatch.setattr(auth.service.token, "exchange_state_for_token", mock_exchange)
        
        response = client.get(
            "/api/v1/auth/exchange-state", params={"state_id": "valid-state-id"}
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_token_exchange_invalid_state(self, client, monkeypatch):
        # Mock failed token exchange
        async def mock_exchange_fail(*args, **kwargs):
            return None
        
        # Patch the exchange method
        import auth.service.token
        monkeypatch.setattr(auth.service.token, "exchange_state_for_token", mock_exchange_fail)
        
        response = client.get(
            "/api/v1/auth/exchange-state", params={"state_id": "invalid-state-id"}
        )
        assert response.status_code == 422
        assert "detail" in response.json()