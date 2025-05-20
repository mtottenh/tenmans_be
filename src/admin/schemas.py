from datetime import datetime
from enum import StrEnum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class RoundForfeitRequest(BaseModel):
    forfeit_notes: str


class ExtendRoundRequest(BaseModel):
    new_end_date: datetime
    reason: str


class UndoForfeitRequest(BaseModel):
    reason: str


class DisputeResolutionType(StrEnum):
    ACCEPT_RESULT = "accept_result"
    OVERRIDE_RESULT = "override_result"
    VOID_MATCH = "void_match"
    REPLAY_MATCH = "replay_match"


class DisputeResolution(BaseModel):
    resolution_type: DisputeResolutionType
    reason: str
    team_1_score: Optional[int] = Field(None, ge=0)
    team_2_score: Optional[int] = Field(None, ge=0)
    evidence_urls: Optional[list[str]] = None


class TournamentConfigUpdate(BaseModel):
    name: Optional[str] = None
    max_teams: Optional[int] = Field(None, ge=2)
    min_teams: Optional[int] = Field(None, ge=2)
    max_team_size: Optional[int] = Field(None, ge=1)
    min_team_size: Optional[int] = Field(None, ge=1)
    registration_start: Optional[datetime] = None
    registration_end: Optional[datetime] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    rules: Optional[str] = None
    format_config: Optional[dict] = None


class TournamentStatusForce(BaseModel):
    new_status: str
    reason: str
    skip_validations: bool = False


class RoundGeneration(BaseModel):
    round_number: int
    round_type: Optional[str] = None
    force_pairings: Optional[list[dict]] = None


class TeamDisbandRequest(BaseModel):
    reason: str
    ban_captain: bool = False
    remove_from_tournaments: bool = True


class RosterChangeRequest(BaseModel):
    player_id: str
    action: Literal["add", "remove", "promote_captain", "demote_captain"]
    reason: str


class PlayerEloAdjustment(BaseModel):
    new_elo: int = Field(ge=0, le=3000)
    reason: str
    adjustment_type: Literal["set", "add", "subtract"]


class ModerationActionRequest(BaseModel):
    action_type: Literal["warning", "suspension", "ban"]
    duration_days: Optional[int] = None
    reason: str
    scope: Literal["global", "tournament", "season"]
    scope_id: Optional[str] = None
