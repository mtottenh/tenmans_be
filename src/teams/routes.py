from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
import httpx
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
import os

from auth.schemas import PlayerPublic
from db.main import get_session
from auth.dependencies import get_current_player
from auth.models import Player
from auth.service import AuthService
from competitions.season.service import SeasonService
from teams.models import Roster, Team, TeamCaptain
from teams.schemas import (
    RosterMember,
    TeamCaptainInfo,
    TeamCreate,
    TeamCreateRequest,
    TeamDetailed,
    TeamUpdate,
)
from teams.service import TeamService, TeamServiceError
from state.service import StateService
from upload.service import UploadService
from .dependencies import require_team_captain_by_name, require_team_captain_by_id
from config import Config

team_router = APIRouter(prefix="/teams")
team_service = TeamService()
season_service = SeasonService()
state_service = StateService(Config.REDIS_URL)
upload_service = UploadService(state_service)
auth_service = AuthService()


# async def to_team_response(t: Team):
#     async def get_roster_member(r: Roster):

#         player = await r.awaitable_attrs.player
#         return RosterMember(
#             player= await to_player_public(player),
#             pending=r.pending,
#             created_at=r.created_at,
#             updated_at=r.updated_at
#         )
#     roster_members = [ await get_roster_member(x) for x in await t.awaitable_attrs.rosters]
    
#     async def _get_captain(x: TeamCaptain):
#         player = await x.awaitable_attrs.player
#         return TeamCaptainInfo(
#             id=x.id,
#             player=player,
#             created_at=x.created_at
#         )

#     captains = [ await _get_captain(x) for x in await t.awaitable_attrs.captains ]


#     return TeamResponse(
#         id=t.id,
#         name=t.name,
#         logo=t.logo,
#         active_roster_count=len([ p for p in roster_members if not p.pending]),
#         created_at=t.created_at,
#         captains=captains,
#         roster=roster_members,
#     )


# TODO: Get a detailed team response including the roster.
@team_router.get("/", response_model=List[TeamDetailed])
async def get_all_teams(
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get all teams with detailed information."""
    return await team_service.get_all_teams_with_details(session)


@team_router.post("/", status_code=status.HTTP_201_CREATED, response_model=TeamDetailed)
async def create_team(
    team_create_model: TeamCreateRequest,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Create a new team with the current player as captain."""
    try:
        name = team_create_model.name
        logo_token_id = team_create_model.logo_token_id
        # Check if team exists
        team_exists = await team_service.team_exists(name, session)
        if team_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Team with name '{name}' already exists"
            )
        # Handle logo upload
        upload_result = await upload_service.get_upload_result(logo_token_id)
        if not upload_result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired logo upload token"
            )

        final_path = await upload_service.move_upload_if_temp(upload_result, name)

        # Create team
        new_team = await team_service.create_team(
            name=name,
            captain=current_player,
            actor=current_player,
            logo_path=final_path,
            session=session
        )
        new_team = await team_service.get_team_by_id(id=new_team.id, session=session)
        return new_team

    except TeamServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@team_router.get("/id/{id}", response_model=TeamDetailed)
async def get_team_by_id(
    id: str,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get team by ID."""
    team = await team_service.get_team_by_id(id, session)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team with ID '{id}' not found"
        )
    return team

@team_router.delete("/id/{team_id}", dependencies=[Depends(require_team_captain_by_id)])
async def delete_team(
    team_id: str,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    team = await team_service.get_team_by_id(team_id, session)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Team with id {team_id} not found")
    return await team_service.disband_team(team, "REASON", current_player, session)

@team_router.get('/id/{id}/logo')
async def get_team_logo_by_id(id: str, session: AsyncSession = Depends(get_session)):
    """Get team logo by team ID."""
    team = await team_service.get_team_by_id(id, session)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown team ID")
    if not team.logo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team has not yet uploaded a logo")
    if not os.path.exists(team.logo):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Logo not found on the server at {team.logo}"
        )
    return FileResponse(team.logo)

@team_router.get("/name/{name}", response_model=TeamDetailed)
async def get_team_by_name(
    name: str,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get team by name."""
    team = await team_service.get_team_by_name(name, session)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team with name '{name}' not found"
        )
    return team

@team_router.get('/name/{name}/logo')
async def get_team_logo_by_name(name: str, session: AsyncSession = Depends(get_session)):
    """Get team logo by team name."""
    team = await team_service.get_team_by_name(name, session)
    if not team or not team.logo or not os.path.exists(team.logo):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Logo not found"
        )
    return FileResponse(team.logo)

# @team_router.patch(
#     "/name/{team_name}/roster",
#     dependencies=[Depends(require_team_captain)]
# )
# async def update_team_roster(
#     team_name: str,
#     roster: RosterUpdateModel,
#     current_player: Player = Depends(get_current_player),
#     session: AsyncSession = Depends(get_session)
# ):
#     """Update team roster. Requires team captain permission."""
#     try:
#         season = await season_service.get_active_season(session)
#         if not season:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="No active season configured"
#             )

#         team = await team_service.get_team_by_name(team_name, session)
        
#         return await team_service.update_roster(
#             team=team,
#             roster=roster,
#             season=season,
#             actor=current_player,
#             session=session
#         )

#     except TeamServiceError as e:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=str(e)
#         )

# @team_router.get(
#     "/name/{team_name}/roster",
#     response_model=List[RosterEntryModel]
# )
# async def get_team_roster(
#     team_name: str,
#     session: AsyncSession = Depends(get_session),
#     current_player: Player = Depends(get_current_player)
# ):
#     """Get team roster."""
#     season = await season_service.get_active_season(session)
#     if not season:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="No active season configured"
#         )

#     return await team_service.get_roster(team_name, season, session)
# TODO - Need to ensure we handle awaitable attrs here
# 
@team_router.get(
    "/name/{team_name}/captains",
    response_model=List[PlayerPublic]
)
async def get_team_captains(
    team_name: str,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get team captains."""
    return await team_service.get_team_captains(team_name, session)

@team_router.get(
    "/id/{team_id}/captains",
    response_model=List[PlayerPublic]
)
async def get_team_captains(
    team_id: str,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get team captains."""
    return await team_service.get_team_captains_by_team_id(team_id, session)

@team_router.post(
    "/name/{team_name}/captains/{player_id}",
    dependencies=[Depends(require_team_captain_by_name)]
)
async def add_team_captain(
    team_name: str,
    player_id: str,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Add a team captain. Requires team captain permission."""
    try:
        team = await team_service.get_team_by_name(team_name, session)
        new_captain = await auth_service.get_player_by_uid(player_id, session)
        
        if not new_captain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Player with ID '{player_id}' not found"
            )

        return await team_service.create_captain(
            team=team,
            player=new_captain,
            actor=current_player,
            session=session
        )

    except TeamServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    

@team_router.delete(
    "/name/{team_name}/captains/{player_id}",
    dependencies=[Depends(require_team_captain_by_name)]
)
async def remove_team_captain(
    team_name: str,
    player_id: str,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Remove a team captain. Requires team captain permission."""
    try:
        team = await team_service.get_team_by_name(team_name, session)
        player = await auth_service.get_player_by_uid(player_id, session)
        
        if not player:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Player with ID '{player_id}' not found"
            )

        # Check this won't remove the last captain
        captains = await team_service.get_team_captains(team_name, session)
        if len(captains) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last team captain"
            )

        await team_service.remove_captain(
            team=team,
            player=player,
            actor=current_player,
            session=session
        )
        
        return {"status": "success"}

    except TeamServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )