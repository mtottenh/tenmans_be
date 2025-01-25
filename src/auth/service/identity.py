from typing import List, Optional
from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload
import httpx
import logging
from audit.context import AuditContext
from audit.schemas import AuditEventType
from audit.service import AuditService
from auth.models import Player, Role
from teams.models import Roster
from teams.base_schemas import TeamBase
from auth.schemas import PlayerEmailCreate, PlayerWithTeamBasic,  AuthType, PlayerStatus
from config import Config
from passlib.context import CryptContext
LOG = logging.getLogger('uvicorn.error')

class InvalidSteamResponseException(Exception):
    pass

class IdentityService:
    """Service handling basic player identity and CRUD operations"""
    
    def __init__(self, pwd_context):
        self.pwd_context = pwd_context
        
    def get_password_hash(self, password: str) -> str:
        return self.pwd_context.hash(password)
        
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return self.pwd_context.verify(plain_password, hashed_password)

    async def get_all_players(self, session: AsyncSession) -> List[Player]:
        stmt = select(Player).order_by(desc(Player.created_at)).options(
            selectinload(Player.roles).selectinload(Role.permissions)
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_all_players_with_basic_team_info(
        self,
        current_season_id: str,
        session: AsyncSession
    ) -> List[PlayerWithTeamBasic]:
        stmt = select(Player).order_by(desc(Player.created_at)).options(
            selectinload(Player.roles).selectinload(Role.permissions),
            selectinload(Player.team_rosters).selectinload(Roster.team)
        )
        result = (await session.execute(stmt)).scalars()
        players = result.all()
        
        return [
            self._create_player_with_team_info(player, current_season_id)
            for player in players
        ]
    
    def _create_player_with_team_info(
        self,
        player: Player,
        current_season_id: str
    ) -> PlayerWithTeamBasic:
        roster = next(
            (r for r in player.team_rosters if r.season_id == current_season_id),
            None
        )
        team = TeamBase.model_validate(roster.team) if roster and roster.team else None
        
        return PlayerWithTeamBasic(
            id=player.id,
            name=player.name,
            email=player.email,
            steam_id=player.steam_id,
            auth_type=player.auth_type,
            status=player.status,
            current_elo=player.current_elo,
            highest_elo=player.highest_elo,
            created_at=player.created_at,
            updated_at=player.updated_at,
            roles=player.roles,
            team=team
        )

    async def get_player_by_name(self, name: str, session: AsyncSession) -> Optional[Player]:
        stmt = select(Player).where(Player.name == name)
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def get_player_by_id(self, player_id: str, session: AsyncSession) -> Optional[Player]:
        stmt = select(Player).where(Player.id == player_id).options(
            selectinload(Player.roles).selectinload(Role.permissions)
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    async def get_player_by_email(self, email: str, session: AsyncSession) -> Optional[Player]:
        stmt = select(Player).where(Player.email == email).options(
            selectinload(Player.roles).selectinload(Role.permissions)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_player_by_steam_id(self, steam_id: str, session: AsyncSession) -> Optional[Player]:
        stmt = select(Player).where(Player.steam_id == steam_id).options(
            selectinload(Player.roles).selectinload(Role.permissions)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @AuditService.audited_transaction(
            action_type=AuditEventType.CREATE,
            entity_type='Player'
    )
    async def create_player_with_email(
        self,
        player_data: PlayerEmailCreate,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> Player:
        if await self.get_player_by_email(player_data.email, session):
            raise ValueError("Player with this email already exists")

        # Create player
        hashed_password = self.get_password_hash(player_data.password)
        player_dict = player_data.model_dump(exclude={'password'})
        
        player = Player(
            **player_dict,
            password_hash=hashed_password,
            auth_type=AuthType.EMAIL,
            status=PlayerStatus.ACTIVE
        )
        
        session.add(player)
        return player

    @AuditService.audited_transaction(
            action_type=AuditEventType.CREATE,
            entity_type='Player'
    )
    async def create_player_with_steam(self,
                                       steam_id: str, 
                                       actor: Player,
                                       session: AsyncSession,
                                       audit_context: Optional[AuditContext] = None
                                       ) -> Player:
        player_name = await self._fetch_steam_player_name(steam_id)
        
        player = Player(
            steam_id=steam_id,
            auth_type=AuthType.STEAM,
            name=player_name,
            status=PlayerStatus.ACTIVE
        )
        
        session.add(player)
        return player

    async def _fetch_steam_player_name(self, steam_id: str) -> str:
        """Fetch player name from Steam API"""
        base_url = "http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
        params = {
            "key": Config.STEAM_API_KEY,
            "steamids": steam_id
        }
        
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            players = data.get("response", {}).get("players", [])
            if not players:
                raise InvalidSteamResponseException("No player data returned from Steam")

            return players[0].get("personaname")
        

def create_identity_service() -> IdentityService:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return IdentityService(pwd_context)