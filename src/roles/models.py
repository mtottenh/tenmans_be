# permissions/models.py

from enum import StrEnum
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from auth.service import ScopeType

class PermissionTemplate:
    """Predefined permission templates for common scenarios"""
    
    TEMPLATES = {
        "team_captain": {
            "roles": ["team_captain"],
            "permissions": [
                "manage_team",
                "manage_roster",
                "submit_results",
                "schedule_matches"
            ],
            "scope_type": ScopeType.TEAM
        },
        "tournament_admin": {
            "roles": ["tournament_admin"],
            "permissions": [
                "manage_tournament",
                "manage_fixtures",
                "manage_results",
                "manage_participants"
            ],
            "scope_type": ScopeType.TOURNAMENT
        },
        "moderator": {
            "roles": ["moderator"],
            "permissions": [
                "moderate_chat",
                "manage_bans",
                "verify_users"
            ],
            "scope_type": ScopeType.GLOBAL
        },
        "league_admin": {
            "roles": ["league_admin"],
            "permissions": [
                "manage_seasons",
                "manage_tournaments",
                "manage_teams",
                "manage_users",
                "manage_roles"
            ],
            "scope_type": ScopeType.GLOBAL
        }
    }

    @classmethod
    def get_template(cls, template_name: str) -> dict:
        """Get a permission template by name"""
        if template_name not in cls.TEMPLATES:
            raise ValueError(f"Template {template_name} not found")
        return cls.TEMPLATES[template_name]

    @classmethod
    def list_templates(cls) -> List[str]:
        """Get list of available templates"""
        return list(cls.TEMPLATES.keys())

@dataclass
class PermissionAuditResult:
    """Container for permission audit results"""
    player_uid: str
    player_name: str
    steam_id: str
    roles: List[str]
    global_permissions: Set[str]
    team_permissions: Dict[str, Set[str]]  # team_id -> permissions
    tournament_permissions: Dict[str, Set[str]]  # tournament_id -> permissions
    issues: List[str]