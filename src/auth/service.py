from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.sql.operators import is_
from sqlmodel import select, desc, or_
from auth.models import Player, Permission, Role, PlayerRole
from auth.schemas import TokenResponse, AuthType, PlayerEmailCreate, PlayerLogin, PlayerUpdate
from passlib.context import CryptContext
import httpx
import jwt
from enum import StrEnum
import uuid
from config import Config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class InvalidSteamResponseException(Exception):
    pass

class ScopeType(StrEnum):
    GLOBAL = "global"
    TEAM = "team"
    TOURNAMENT = "tournament"

class AuthConfig:
    """Configuration for authentication/authorization settings"""
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    REFRESH_TOKEN_EXPIRE_DAYS = 7
    ALGORITHM = Config.JWT_ALGORITHM
    SECRET_KEY = Config.JWT_SECRET

class PermissionScope:
    def __init__(self, scope_type: ScopeType, scope_id: Optional[uuid.UUID] = None):
        self.scope_type = scope_type
        self.scope_id = scope_id

    def __eq__(self, other):
        if not isinstance(other, PermissionScope):
            return False
        return (self.scope_type == other.scope_type and 
                self.scope_id == other.scope_id)

class AuthService:
    def __init__(self):
        self.pwd_context = pwd_context

    async def get_all_players(self, session: AsyncSession) -> List[Player]:
        stmnt = select(Player).order_by(desc(Player.created_at))

        result = await session.execute(stmnt)

        return result.all()
    
    async def get_player_by_name(self, name: str, session: AsyncSession) -> Player | None:
        stmnt = select(Player).where(Player.name == name)
        result = await session.execute(stmnt)

        return result.first()

    async def get_player_by_uid(self, uid: str, session: AsyncSession) -> Optional[Player]:
        """Retrieve a player by their UID"""
        stmt = select(Player).where(Player.uid == uid)
        result = await session.executeute(stmt)
        return result.scalar_one_or_none()

    async def get_player_by_email(self, email: str, session: AsyncSession) -> Optional[Player]:
        """Retrieve a player by their email"""
        stmt = select(Player).where(Player.email == email)
        result = await session.executeute(stmt)
        return result.scalar_one_or_none()

    async def get_player_by_steam_id(self, steam_id: str, session: AsyncSession) -> Optional[Player]:
        """Retrieve a player by their Steam ID"""
        stmt = select(Player).where(Player.steam_id == steam_id)
        result = await session.executeute(stmt)
        return result.scalar_one_or_none()
    
    async def get_unranked_players(self, session) -> List[Player] | None:
        stmnt = select(Player).where(or_(is_(Player.current_elo,None), is_(Player.highest_elo, None)))
        result = await session.execute(stmnt)
        return result.all()


    async def player_exists_by_uid(self, player_uid: str, session: AsyncSession) -> bool:
        player = await self.get_player_by_uid(player_uid, session)
        if player:
            return True
        else:
            return False

    async def player_exists_by_email(self, email: str, session: AsyncSession) -> bool:
        player = await self.get_player_by_email(email, session)
        if player:
            return True
        else:
            return False

    async def get_player_permissions(
        self,
        player: Player,
        session: AsyncSession
    ) -> List[Tuple[str, ScopeType, Optional[uuid.UUID]]]:
        """
        Get all permissions for a player with their scopes
        Returns a list of tuples (permission_name, scope_type, scope_id)
        """
        stmt = select(
            Permission.name,
            PlayerRole.scope_type,
            PlayerRole.scope_id
        ).join(
            Role,
            Permission.roles
        ).join(
            PlayerRole,
            Role.id == PlayerRole.role_id
        ).where(
            PlayerRole.player_uid == player.uid
        )
        
        result = await session.executeute(stmt)
        return [(row[0], ScopeType(row[1]), row[2]) for row in result]

    async def get_player_roles(
        self,
        player: Player,
        session: AsyncSession
    ) -> List[Tuple[Role, ScopeType, Optional[uuid.UUID]]]:
        """Get all roles for a player with their scopes"""
        stmt = select(
            Role,
            PlayerRole.scope_type,
            PlayerRole.scope_id
        ).join(
            PlayerRole,
            Role.id == PlayerRole.role_id
        ).where(
            PlayerRole.player_uid == player.uid
        )
        
        result = await session.executeute(stmt)
        return [(row[0], ScopeType(row[1]), row[2]) for row in result]

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return self.pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Hash a password"""
        return self.pwd_context.hash(password)

    async def authenticate_player(
        self,
        login_data: PlayerLogin,
        session: AsyncSession
    ) -> Optional[Tuple[Player, TokenResponse]]:
        """Authenticate a player and return tokens if successful"""
        player = await self.get_player_by_email(login_data.email, session)
        
        if not player or not self.verify_password(login_data.password, player.password_hash):
            return None
            
        tokens = self.create_tokens(str(player.uid), player.auth_type)
        return player, tokens

    def create_token(
        self,
        player_uid: str,
        auth_type: AuthType,
        expires_delta: timedelta,
        is_refresh: bool = False
    ) -> str:
        """Create a JWT token"""
        expire = datetime.utcnow() + expires_delta
        to_encode = {
            "player_uid": str(player_uid),
            "auth_type": auth_type,
            "exp": expire,
            "is_refresh": is_refresh
        }
        return jwt.encode(to_encode, AuthConfig.SECRET_KEY, algorithm=AuthConfig.ALGORITHM)

    def create_tokens(self, player_uid: str, auth_type: AuthType) -> TokenResponse:
        """Create both access and refresh tokens"""
        access_token = self.create_token(
            player_uid,
            auth_type,
            timedelta(minutes=AuthConfig.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        refresh_token = self.create_token(
            player_uid,
            auth_type,
            timedelta(days=AuthConfig.REFRESH_TOKEN_EXPIRE_DAYS),
            is_refresh=True
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            auth_type=auth_type
        )

    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode a JWT token"""
        try:
            return jwt.decode(
                token,
                AuthConfig.SECRET_KEY,
                algorithms=[AuthConfig.ALGORITHM]
            )
        except jwt.InvalidTokenError:
            return None

    async def verify_permissions(
        self,
        player: Player,
        required_permissions: List[str],
        scope: Optional[PermissionScope],
        session: AsyncSession
    ) -> bool:
        """
        Verify if a player has all required permissions in the given scope
        If scope is None, checks for global permissions
        """
        player_permissions = await self.get_player_permissions(player, session)
        
        for required_perm in required_permissions:
            has_permission = False
            for perm_name, perm_scope_type, perm_scope_id in player_permissions:
                # Check if permission matches
                if perm_name != required_perm:
                    continue

                # Global permissions always apply
                if perm_scope_type == ScopeType.GLOBAL:
                    has_permission = True
                    break

                # If checking for specific scope
                if scope and perm_scope_type == scope.scope_type:
                    # For team/tournament specific permissions, check scope_id
                    if scope.scope_id is None or perm_scope_id == scope.scope_id:
                        has_permission = True
                        break

            if not has_permission:
                return False

        return True

    async def create_player(
        self,
        player_data: PlayerEmailCreate,
        session: AsyncSession
    ) -> Tuple[Player, TokenResponse]:
        """Create a new player and return their tokens"""
        # Check if player already exists
        existing_player = await self.get_player_by_email(player_data.email, session)
        if existing_player:
            raise ValueError("Player with this email already exists")

        # Create new player
        hashed_password = self.get_password_hash(player_data.password)
        player_dict = player_data.model_dump()
        del player_dict['password']
        
        new_player = Player(
            **player_dict,
            password_hash=hashed_password,
            auth_type=AuthType.EMAIL
        )
        
        session.add(new_player)
        await session.commit()
        await session.refresh(new_player)

        # Create tokens
        tokens = self.create_tokens(str(new_player.uid), new_player.auth_type)
        return new_player, tokens

    async def create_steam_player(self, steam_id: str, session: AsyncSession) -> Player:
        """Create a new player from Steam authentication"""
        # Here you could optionally fetch additional player info from Steam Web API

        base_url = "http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
        params = {
            "key": Config.STEAM_API_KEY,
            "steamids": steam_id
        }
        player_name = ""
        async with httpx.AsyncClient(timeout=60) as client:
            response = client.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            # Extract the personaname from the response
            players = data.get("response", {}).get("players", [])
            if players:
                player_name = players[0].get("personaname")
            else:
                raise InvalidSteamResponseException

        new_player = Player(
            steam_id=steam_id,
            auth_type=AuthType.STEAM,
            name=player_name        )
        
        session.add(new_player)
        await session.commit()
        await session.refresh(new_player)
        
        return new_player

    async def update_player(
        self, player_uid: str, player_data: PlayerUpdate, session: AsyncSession
    ):
        player_to_update = await self.get_player_by_uid(player_uid, session)
        if player_to_update is not None:
            update_data = player_data.model_dump()
            for k, v in update_data.items():
                if v is not None:
                    if k == "password":
                        setattr(player_to_update, 'password_hash', self.get_password_hash(v))
                    else:
                        setattr(player_to_update, k, v)
            await session.add(player_to_update)
            await session.commit()
            await session.refresh(player_to_update)
        return player_to_update

    async def delete_player(self, player_uid: str, session: AsyncSession):
        player_to_delete = await self.get_player_by_uid(player_uid, session)

        if player_to_delete is not None:
            await session.delete(player_to_delete)
            await session.commit()
            return {}
        else:
            return None


    async def assign_role(
        self,
        player: Player,
        role: Role,
        scope_type: ScopeType,
        scope_id: Optional[uuid.UUID],
        session: AsyncSession
    ) -> PlayerRole:
        """Assign a role to a player with scope"""
        if scope_type != ScopeType.GLOBAL and scope_id is None:
            raise ValueError("scope_id is required for non-global scopes")

        player_role = PlayerRole(
            player_uid=player.uid,
            role_id=role.id,
            scope_type=scope_type,
            scope_id=scope_id
        )
        
        session.add(player_role)
        await session.commit()
        await session.refresh(player_role)
        return player_role
