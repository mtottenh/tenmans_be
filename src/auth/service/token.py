from typing import Optional, Dict
from datetime import datetime, timedelta
import jwt
from auth.schemas import TokenResponse, AuthType
from config import Config
class TokenConfig:
    """Configuration for token generation and validation"""
    def __init__(
        self,
        secret_key: str,
        algorithm: str,
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire = timedelta(minutes=access_token_expire_minutes)
        self.refresh_token_expire = timedelta(days=refresh_token_expire_days)

class TokenService:
    """Service for handling authentication tokens"""
    
    def __init__(self, config: TokenConfig):
        self.config = config

    def create_token(
        self,
        player_id: str,
        auth_type: AuthType,
        expires_delta: timedelta,
        is_refresh: bool = False
    ) -> str:
        """Create a JWT token"""
        expire = datetime.utcnow() + expires_delta
        to_encode = {
            "player_id": str(player_id),
            "auth_type": auth_type,
            "exp": expire,
            "is_refresh": is_refresh
        }
        return jwt.encode(
            to_encode,
            self.config.secret_key,
            algorithm=self.config.algorithm
        )

    def create_auth_tokens(self, player_id: str, auth_type: AuthType) -> TokenResponse:
        """Create both access and refresh tokens"""
        access_token = self.create_token(
            player_id,
            auth_type,
            self.config.access_token_expire
        )
        refresh_token = self.create_token(
            player_id,
            auth_type,
            self.config.refresh_token_expire,
            is_refresh=True
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            auth_type=auth_type
        )

    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify and decode a JWT token"""
        try:
            return jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm]
            )
        except jwt.InvalidTokenError:
            return None

    def refresh_access_token(self, refresh_token: str) -> Optional[TokenResponse]:
        """Create new access token using refresh token"""
        token_data = self.verify_token(refresh_token)
        if not token_data or not token_data.get('is_refresh'):
            return None
            
        return self.create_auth_tokens(
            token_data['player_id'],
            AuthType(token_data['auth_type'])
        )
    

def create_token_service(config: Optional[TokenConfig] = None) -> TokenService:
    config = config or TokenConfig(
        secret_key=Config.JWT_SECRET,
        algorithm=Config.JWT_ALGORITHM,
    )
    
    return TokenService(config)