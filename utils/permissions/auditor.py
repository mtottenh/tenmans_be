
import logging
from typing import Dict, List, Set
from dataclasses import dataclass
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from auth.models import Player
from auth.service.auth import ScopeType
from teams.models import Team
from competitions.models.tournaments import Tournament
from services.auth import auth_service


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PermissionAuditResult:
    """Container for permission audit results"""
    player_id: str
    player_name: str
    steam_id: str
    roles: List[str]
    global_permissions: Set[str]
    team_permissions: Dict[str, Set[str]]  # team_id -> permissions
    tournament_permissions: Dict[str, Set[str]]  # tournament_id -> permissions
    issues: List[str]

class PermissionAuditor:
    """Utility for auditing user permissions"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.auth_service = auth_service
        
        # Cache for entity lookups
        self._team_cache: Dict[str, Team] = {}
        self._tournament_cache: Dict[str, Tournament] = {}

    async def audit_all_players(self) -> List[PermissionAuditResult]:
        """Perform permission audit for all players"""
        logger.info("Starting full permission audit...")
        
        # Get all players
        players = await self._get_all_players()
        
        # Audit each player
        results = []
        for player in players:
            result = await self.audit_player(player.id)
            results.append(result)
            
        logger.info(f"Completed audit of {len(results)} players")
        return results

    async def audit_player(self, player_id: str) -> PermissionAuditResult:
        """Audit permissions for a specific player"""
        logger.debug(f"Auditing player {player_id}")
        
        # Get player and their roles
        player = await self.auth_service.get_player_by_id(player_id, self.session)
        if not player:
            raise ValueError(f"Player {player_id} not found")
            
        # Initialize audit result
        result = PermissionAuditResult(
            player_id=str(player.id),
            player_name=player.name,
            steam_id=player.steam_id,
            roles=[],
            global_permissions=set(),
            team_permissions={},
            tournament_permissions={},
            issues=[]
        )
        
        # Get all roles and permissions using RoleService
        roles_and_scopes = await self.auth_service.get_player_roles(player, self.session)
        
        for role, scope_type, scope_id in roles_and_scopes:
            result.roles.append(role.name)
            
            # Get permissions for this role
            permissions = [p.name for p in await role.awaitable_attrs.permissions]  # Use role.permissions directly
            
            # Check scope type
            if scope_type == ScopeType.GLOBAL:
                result.global_permissions.update(permissions)
            elif scope_type == ScopeType.TEAM:
                team_id = str(scope_id)
                if team_id not in result.team_permissions:
                    result.team_permissions[team_id] = set()
                result.team_permissions[team_id].update(permissions)
            elif scope_type == ScopeType.TOURNAMENT:
                tournament_id = str(scope_id)
                if tournament_id not in result.tournament_permissions:
                    result.tournament_permissions[tournament_id] = set()
                result.tournament_permissions[tournament_id].update(permissions)
                
        # Validate permissions
        await self._validate_permissions(result)
        
        return result

    async def _get_all_players(self) -> List[Player]:
        """Get all players from database"""
        stmt = select(Player)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def _validate_permissions(self, result: PermissionAuditResult):
        """Validate permissions for consistency and common issues"""
        # Check for orphaned team permissions
        for team_id in result.team_permissions:
            if not await self._team_exists(team_id):
                result.issues.append(f"Permission for non-existent team: {team_id}")
                
        # Check for orphaned tournament permissions
        for tournament_id in result.tournament_permissions:
            if not await self._tournament_exists(tournament_id):
                result.issues.append(
                    f"Permission for non-existent tournament: {tournament_id}"
                )
                
        # Check for conflicting permissions
        self._check_permission_conflicts(result)

    def _check_permission_conflicts(self, result: PermissionAuditResult):
        """Check for conflicting or redundant permissions"""
        # Check for redundant team permissions
        if "manage_all_teams" in result.global_permissions:
            for team_perms in result.team_permissions.values():
                if "manage_team" in team_perms:
                    result.issues.append(
                        "Redundant team management permission with global manage_all_teams"
                    )
                    
        # Check for redundant tournament permissions
        if "manage_all_tournaments" in result.global_permissions:
            for tournament_perms in result.tournament_permissions.values():
                if "manage_tournament" in tournament_perms:
                    result.issues.append(
                        "Redundant tournament permission with global manage_all_tournaments"
                    )

    async def _team_exists(self, team_id: str) -> bool:
        """Check if a team exists (with caching)"""
        if team_id not in self._team_cache:
            stmt = select(Team).where(Team.id == team_id)
            result = await self.session.execute(stmt)
            team = result.scalar_one_or_none()
            self._team_cache[team_id] = team is not None
        return self._team_cache[team_id]

    async def _tournament_exists(self, tournament_id: str) -> bool:
        """Check if a tournament exists (with caching)"""
        if tournament_id not in self._tournament_cache:
            stmt = select(Tournament).where(Tournament.id == tournament_id)
            result = await self.session.execute(stmt)
            tournament = result.scalar_one_or_none()
            self._tournament_cache[tournament_id] = tournament is not None
        return self._tournament_cache[tournament_id]