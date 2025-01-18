from datetime import datetime, timedelta
import pprint
from typing import List, Optional, Tuple, Dict
from sqlalchemy import inspect
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.sql.operators import is_
from sqlalchemy.orm import selectinload
from sqlmodel import select, desc, or_
from auth.models import Player, Permission, Role, PlayerRole
from auth.schemas import PlayerWithTeamBasic, TokenResponse, AuthType, PlayerEmailCreate, PlayerLogin, PlayerUpdate
from passlib.context import CryptContext
import httpx
import jwt
from enum import StrEnum
import uuid
from config import Config
import logging

from roles.service import RoleService
from teams.models import Roster
from teams.schemas import TeamBase

LOG = logging.getLogger('uvicorn.error')
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class InvalidSteamResponseException(Exception):
    pass

class UninitializedDBException(Exception):
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
        self.role_service = RoleService()

    async def get_all_players(self, session: AsyncSession) -> List[Player]:
        stmnt = select(Player).order_by(desc(Player.created_at)).options(
                selectinload(Player.roles)
                .selectinload(Role.permissions)
            )
        players: List[Player] = (await session.execute(stmnt)).scalars().all()
        return players

    async def get_all_players_with_basic_team_info(self,  current_season_id: str, session: AsyncSession,) -> List[PlayerWithTeamBasic]:
        stmnt = select(Player).order_by(desc(Player.created_at)).options(
                selectinload(Player.roles)
                .selectinload(Role.permissions),
                selectinload(Player.team_rosters)
                .selectinload(Roster.team)
            )

        players: List[Player] = (await session.execute(stmnt)).scalars().all()
        players_with_status = []
        for player in players:
            # Check if the player is on a team in the current season
            roster = next(
                (r for r in player.team_rosters if r.season_id == current_season_id), 
                None
            )
            
            # Populate team info if the player is on a team
            team = TeamBase.model_validate(roster.team) if roster and roster.team else None
            
            # Add team info and other player attributes to the response
            player_with_status = PlayerWithTeamBasic(
            uid=player.uid,
            name=player.name,
            email=player.email,
            steam_id=player.steam_id,
            auth_type=player.auth_type,
            verification_status=player.verification_status,
            current_elo=player.current_elo,
            highest_elo=player.highest_elo,
            created_at=player.created_at,
            updated_at=player.updated_at,
            roles=player.roles,  # Ensure roles are populated
            team=team  # Add the computed team field
            )
            players_with_status.append(player_with_status)
    
    
        return players_with_status
    
    async def get_player_by_name(self, name: str, session: AsyncSession) -> Player | None:
        stmnt = select(Player).where(Player.name == name)
        result = (await session.execute(stmnt)).scalars()

        return result.first()

    async def get_player_by_uid(self, uid: str, session: AsyncSession) -> Optional[Player]:
        """Retrieve a player by their UID"""
        stmt = select(Player).where(Player.uid == uid).options(
            selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        result = await session.execute(stmt)
        return result.scalars().first()
        

    async def get_player_by_email(self, email: str, session: AsyncSession) -> Optional[Player]:
        """Retrieve a player by their email"""
        stmt = select(Player).where(Player.email == email).options(
            selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_player_by_steam_id(self, steam_id: str, session: AsyncSession) -> Optional[Player]:
        """Retrieve a player by their Steam ID"""
        stmt = select(Player).where(Player.steam_id == steam_id).options(
            selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_unranked_players(self, session) -> List[Player] | None:
        stmnt = select(Player).where(or_(is_(Player.current_elo,None), is_(Player.highest_elo, None)))
        result = (await session.execute(stmnt)).scalars()
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
        
        result = await session.execute(stmt)
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
        
        result = await session.execute(stmt)
        return [(row[0], ScopeType(row[1]), row[2]) for row in result]
    
    async def verify_role(self, player: Player, allowed_roles: List[str], session: AsyncSession) -> bool:
        role_list = await self.role_service.get_roles_by_names(allowed_roles, session)
        player_roles = await self.get_player_roles(player,session)
        player_role_ids = [ x[0].id for x in player_roles]

        has_role=False
        for r in role_list:
            if r.id in player_role_ids:
                has_role=True
                break
        return has_role


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
        # TODO - Create 'role creation' services.

        user_role = await self.role_service.get_role_by_name("user", session)
        if user_role is None:
            raise UninitializedDBException("No 'user' role in Database")
        await self.assign_role(new_player, user_role, ScopeType.GLOBAL, None, session)
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
            response = await client.get(base_url, params=params)
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

        await session.flush()
        await session.refresh(new_player)
        user_role = await self.role_service.get_role_by_name("user", session)
        if user_role is None:
            raise UninitializedDBException("No 'user' role in Database")
        await self.assign_role(new_player, user_role, ScopeType.GLOBAL, None, session)

        await session.refresh(new_player)
        return new_player
    
    import pprint
    async def update_player(
        self, player_uid: str, player_data: PlayerUpdate, session: AsyncSession
    ):
        player_to_update = await self.get_player_by_uid(player_uid, session)
        LOG.info(f"Player: {pprint.pformat(player_to_update)}")
        if player_to_update:
            update_data = player_data.model_dump()
            mapper = inspect(player_to_update.__class__)  # Get mapper to inspect fields

            for k, v in update_data.items():
                if v is not None:
                    if k == "password":
                        setattr(player_to_update, "password_hash", self.get_password_hash(v))
                    else:
                        # Check if the field is a relationship
                        if k in mapper.relationships:
                            # It's a relationship field; handle updates to related objects separately
                            raise ValueError(f"Cannot directly update relationship field '{k}'")
                        else:
                            # Update simple attributes
                            setattr(player_to_update, k, v)
            LOG.info(f"Player: {pprint.pformat(player_to_update)}")
            session.add(player_to_update)
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
