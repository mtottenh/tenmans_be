import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from admin.schemas import (
    DisputeResolution,
    ExtendRoundRequest,
    ModerationActionRequest,
    PlayerEloAdjustment,
    RosterChangeRequest,
    RoundForfeitRequest,
    RoundGeneration,
    TeamDisbandRequest,
    TournamentConfigUpdate,
    TournamentStatusForce,
    UndoForfeitRequest,
)
from auth.dependencies import (
    get_current_player,
    require_ban_management,
    require_role_management,
    require_tournament_manage,
    require_user_management,
    require_verification,
)
from auth.models import Player
from auth.schemas import (
    PlayerPrivate,
    PlayerRoleAssign,
    PlayerVerificationUpdate,
)
from competitions.fixtures.schemas import FixtureForfeit, FixtureReschedule
from competitions.fixtures.service import FixtureServiceError
from competitions.models.fixtures import Fixture
from competitions.models.rounds import Round
from competitions.models.tournaments import Tournament
from competitions.rounds.service import RoundServiceError
from db.main import get_session
from matches.models import Result
from matches.schemas import AdminResultOverride
from moderation.schemas import BanCreate, BanDetailed
from services.admin import admin_service
from services.fixture import fixture_service
from services.round import round_service
from services.tournament import tournament_service

from .service import AdminServiceError


admin_router = APIRouter(prefix="/admin")


@admin_router.get(
    "/players",
    response_model=list[PlayerPrivate],
    dependencies=[Depends(require_user_management)],
)
async def get_all_players(
    skip: int = 0,
    limit: int = 100,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Get all players with full details (admin view)"""
    try:
        return await admin_service.get_all_players(
            skip=skip, limit=limit, actor=current_admin, session=session
        )
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.patch(
    "/players/id/{player_id}/verify",
    response_model=PlayerPrivate,
    dependencies=[Depends(require_verification)],
)
async def verify_player(
    player_id: str,
    verification: PlayerVerificationUpdate,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Process a player verification request"""
    try:
        return await admin_service.verify_player(
            player_id=player_id,
            verification=verification,
            actor=current_admin,
            session=session,
        )
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@admin_router.post(
    "/players/id/{player_id}/ban",
    response_model=BanDetailed,
    dependencies=[Depends(require_ban_management)],
)
async def ban_player(
    player_id: str,
    ban_data: BanCreate,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Ban a player"""
    try:
        return await admin_service.ban_player(
            player_id=player_id, ban_data=ban_data, actor=current_admin, session=session
        )
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@admin_router.patch(
    "/bans/id/{ban_id}/revoke",
    response_model=BanDetailed,
    dependencies=[Depends(require_ban_management)],
)
async def revoke_ban(
    ban_id: str,
    reason: str,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Revoke an active ban"""
    try:
        return await admin_service.revoke_ban(
            ban_id=ban_id, reason=reason, actor=current_admin, session=session
        )
    except AdminServiceError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.get(
    "/players/id/{player_id}/bans",
    response_model=list[BanDetailed],
    dependencies=[Depends(require_user_management)],
)
async def get_player_bans(
    player_id: str,
    session: AsyncSession = Depends(get_session),
    include_inactive: bool = False,
):
    """Get a player's ban history"""
    try:
        return await admin_service.get_player_bans(
            player_id=player_id, include_inactive=include_inactive, session=session
        )
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.patch(
    "/players/id/{player_id}/roles",
    response_model=PlayerPrivate,
    dependencies=[Depends(require_role_management)],
)
async def assign_player_role(
    player_id: str,
    role_data: PlayerRoleAssign,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Assign a role to a player"""
    try:
        return await admin_service.assign_role(
            player_id=player_id,
            role_data=role_data,
            actor=current_admin,
            session=session,
        )
    except AdminServiceError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.patch(
    "/tournaments/id/{tournament_id}/rounds/{round_number}/extend",
    response_model=Round,
    dependencies=[Depends(require_tournament_manage)],
)
async def extend_round_deadline(
    tournament_id: uuid.UUID,
    round_number: int,
    extension: ExtendRoundRequest,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Extend a round's deadline"""
    try:
        # Get the round
        round = await tournament_service._get_round_by_number(
            tournament_id, round_number, session
        )
        if not round:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
            )

        return await round_service.extend_round_deadline(
            round=round,
            new_end_date=extension.new_end_date,
            reason=extension.reason,
            actor=current_admin,
            session=session,
        )
    except RoundServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.post(
    "/tournaments/id/{tournament_id}/rounds/{round_number}/forfeit-unplayed",
    response_model=list[Fixture],
    dependencies=[Depends(require_tournament_manage)],
)
async def forfeit_unplayed_matches(
    tournament_id: uuid.UUID,
    round_number: int,
    forfeit_data: RoundForfeitRequest,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Forfeit all unplayed matches in a round"""
    try:
        round = await tournament_service._get_round_by_number(
            tournament_id, round_number, session
        )
        if not round:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
            )

        return await round_service.forfeit_unplayed_fixtures(
            round=round,
            forfeit_notes=forfeit_data.forfeit_notes,
            actor=current_admin,
            session=session,
        )
    except RoundServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.post(
    "/tournaments/id/{tournament_id}/rounds/{round_number}/reopen",
    response_model=Round,
    dependencies=[Depends(require_tournament_manage)],
)
async def reopen_round(
    tournament_id: uuid.UUID,
    round_number: int,
    extension: ExtendRoundRequest,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Reopen a completed round"""
    try:
        round = await tournament_service._get_round_by_number(
            tournament_id, round_number, session
        )
        if not round:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
            )

        return await round_service.reopen_round(
            round=round,
            new_end_date=extension.new_end_date,
            reason=extension.reason,
            actor=current_admin,
            session=session,
        )
    except RoundServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.post(
    "/tournaments/id/{tournament_id}/fixtures/{fixture_id}/undo-forfeit",
    response_model=Fixture,
    dependencies=[Depends(require_tournament_manage)],
)
async def undo_fixture_forfeit(
    tournament_id: uuid.UUID,
    fixture_id: uuid.UUID,
    undo_data: UndoForfeitRequest,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Undo a fixture forfeit"""
    try:
        fixture = await tournament_service._get_fixture(fixture_id, session)
        if not fixture or fixture.tournament_id != tournament_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found"
            )

        return await round_service.undo_fixture_forfeit(
            fixture=fixture,
            reason=undo_data.reason,
            actor=current_admin,
            session=session,
        )
    except RoundServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.post(
    "/matches/results/{result_id}/override",
    response_model=Result,
    dependencies=[Depends(require_tournament_manage)],
)
async def override_match_result(
    result_id: uuid.UUID,
    override_data: AdminResultOverride,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Override a match result as admin"""
    try:
        return await admin_service.override_match_result(
            result_id=result_id,
            override_data=override_data,
            actor=current_admin,
            session=session,
        )
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.post(
    "/matches/disputes/{dispute_id}/resolve",
    response_model=Result,
    dependencies=[Depends(require_tournament_manage)],
)
async def resolve_match_dispute(
    dispute_id: uuid.UUID,
    resolution: DisputeResolution,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Resolve a match result dispute"""
    try:
        return await admin_service.resolve_dispute(
            dispute_id=dispute_id,
            resolution=resolution,
            actor=current_admin,
            session=session,
        )
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.patch(
    "/fixtures/{fixture_id}/reschedule",
    response_model=Fixture,
    dependencies=[Depends(require_tournament_manage)],
)
async def reschedule_fixture(
    fixture_id: uuid.UUID,
    reschedule_data: FixtureReschedule,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Reschedule a fixture"""
    try:
        fixture = await fixture_service.get_fixture(fixture_id, session)
        if not fixture:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found"
            )
            
        return await fixture_service.reschedule_fixture(
            fixture=fixture,
            new_date=reschedule_data.new_scheduled_at,
            reason=reschedule_data.reason,
            actor=current_admin,
            session=session,
        )
    except FixtureServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.post(
    "/fixtures/{fixture_id}/forfeit",
    response_model=Fixture,
    dependencies=[Depends(require_tournament_manage)],
)
async def forfeit_fixture(
    fixture_id: uuid.UUID,
    forfeit_data: FixtureForfeit,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Forfeit a fixture"""
    try:
        fixture = await fixture_service.get_fixture(fixture_id, session)
        if not fixture:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found"
            )
            
        return await fixture_service.forfeit_fixture(
            fixture=fixture,
            forfeit_winner=forfeit_data.forfeit_winner,
            forfeit_notes=forfeit_data.forfeit_notes,
            actor=current_admin,
            session=session,
        )
    except FixtureServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# Tournament Management Endpoints
@admin_router.patch(
    "/tournaments/{tournament_id}/config",
    response_model=Tournament,
    dependencies=[Depends(require_tournament_manage)],
)
async def update_tournament_config(
    tournament_id: uuid.UUID,
    update_data: TournamentConfigUpdate,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Update tournament configuration"""
    try:
        return await admin_service.update_tournament_config(
            tournament_id=tournament_id,
            update_data=update_data,
            actor=current_admin,
            session=session,
        )
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.patch(
    "/tournaments/{tournament_id}/status",
    response_model=Tournament,
    dependencies=[Depends(require_tournament_manage)],
)
async def force_tournament_status(
    tournament_id: uuid.UUID,
    status_data: TournamentStatusForce,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Force tournament status change"""
    try:
        return await admin_service.force_tournament_status(
            tournament_id=tournament_id,
            new_status=status_data.new_status,
            reason=status_data.reason,
            skip_validations=status_data.skip_validations,
            actor=current_admin,
            session=session,
        )
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.post(
    "/tournaments/{tournament_id}/generate-round",
    response_model=Round,
    dependencies=[Depends(require_tournament_manage)],
)
async def generate_tournament_round(
    tournament_id: uuid.UUID,
    round_data: RoundGeneration,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Manually generate a tournament round"""
    try:
        return await admin_service.generate_tournament_round(
            tournament_id=tournament_id,
            round_number=round_data.round_number,
            round_type=round_data.round_type,
            force_pairings=round_data.force_pairings,
            actor=current_admin,
            session=session,
        )
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# Team Management Endpoints
@admin_router.post(
    "/teams/{team_id}/disband",
    response_model=dict,
    dependencies=[Depends(require_tournament_manage)],
)
async def disband_team(
    team_id: uuid.UUID,
    disband_data: TeamDisbandRequest,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Disband a team"""
    try:
        result = await admin_service.disband_team(
            team_id=team_id,
            disband_data=disband_data,
            actor=current_admin,
            session=session,
        )
        return {"message": "Team disbanded successfully", "team_id": str(team_id)}
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.patch(
    "/teams/{team_id}/roster",
    response_model=dict,
    dependencies=[Depends(require_tournament_manage)],
)
async def modify_team_roster(
    team_id: uuid.UUID,
    roster_change: RosterChangeRequest,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Modify team roster (add/remove players, change captains)"""
    try:
        result = await admin_service.modify_team_roster(
            team_id=team_id,
            roster_change=roster_change,
            actor=current_admin,
            session=session,
        )
        return {"message": f"Roster {roster_change.action} completed", "team_id": str(team_id)}
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# Player Management Endpoints
@admin_router.patch(
    "/players/{player_id}/elo",
    response_model=PlayerPrivate,
    dependencies=[Depends(require_user_management)],
)
async def adjust_player_elo(
    player_id: uuid.UUID,
    elo_adjustment: PlayerEloAdjustment,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Adjust player ELO rating"""
    try:
        return await admin_service.adjust_player_elo(
            player_id=player_id,
            elo_adjustment=elo_adjustment,
            actor=current_admin,
            session=session,
        )
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@admin_router.post(
    "/players/{player_id}/force-remove-team",
    response_model=dict,
    dependencies=[Depends(require_user_management)],
)
async def force_remove_from_team(
    player_id: uuid.UUID,
    reason: str,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Force remove player from all teams"""
    try:
        await admin_service.force_remove_from_teams(
            player_id=player_id,
            reason=reason,
            actor=current_admin,
            session=session,
        )
        return {"message": "Player removed from all teams", "player_id": str(player_id)}
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# Moderation Endpoints
@admin_router.post(
    "/moderation/action",
    response_model=dict,
    dependencies=[Depends(require_ban_management)],
)
async def apply_moderation_action(
    player_id: uuid.UUID,
    action: ModerationActionRequest,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Apply moderation action (warning, suspension, ban)"""
    try:
        result = await admin_service.apply_moderation_action(
            player_id=player_id,
            action=action,
            actor=current_admin,
            session=session,
        )
        return {
            "message": f"Moderation action '{action.action_type}' applied",
            "player_id": str(player_id),
            "action_id": str(result.id),
        }
    except AdminServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e