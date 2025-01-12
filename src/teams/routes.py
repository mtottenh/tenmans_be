from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
import os

from src.db.main import get_session
from src.auth.dependencies import get_current_player
from src.auth.models import Player
from src.auth.service import AuthService
from src.competitions.season.service import SeasonService
from src.teams.models import Team
from src.teams.schemas import (
    TeamCreate,
    TeamUpdate,
)
from src.teams.service import TeamService, TeamServiceError
from src.state.service import StateService
from src.upload.service import UploadService
from .dependencies import require_team_captain
from src.config import Config

team_router = APIRouter(prefix="/teams")
team_service = TeamService()
season_service = SeasonService()
state_service = StateService(Config.REDIS_URL)
upload_service = UploadService(state_service)
auth_service = AuthService()


@team_router.get("/", response_model=List[Team])
async def get_all_teams(
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get all teams."""
    return await team_service.get_all_teams(session)

@team_router.post("/", status_code=status.HTTP_201_CREATED)
async def create_team(
    name: str = Form(...),
    logo: UploadFile = File(...),
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Create a new team with the current player as captain."""
    try:
        # Check if team exists
        team_exists = await team_service.team_exists(name, session)
        if team_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Team with name '{name}' already exists"
            )

        # Handle logo upload
        upload_path = None
        if logo:
            upload_request = await upload_service.validate_team_logo(logo)
            upload_path = await upload_service.store_uploaded_file(
                logo,
                upload_request,
                session
            )

        # Create team
        new_team = await team_service.create_team(
            team_data=TeamCreate(name=name),
            captain=current_player,
            actor=current_player,
            logo_path=upload_path,
            session=session
        )

        return new_team

    except TeamServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@team_router.get("/id/{id}", response_model=Team)
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

@team_router.get('/id/{id}/logo')
async def get_team_logo_by_id(id: str, session: AsyncSession = Depends(get_session)):
    """Get team logo by team ID."""
    team = await team_service.get_team_by_id(id, session)
    if not team or not team.logo or not os.path.exists(team.logo):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Logo not found"
        )
    return FileResponse(team.logo)

@team_router.get("/name/{name}", response_model=Team)
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

@team_router.get(
    "/name/{team_name}/captains",
    response_model=List[Player]
)
async def get_team_captains(
    team_name: str,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get team captains."""
    return await team_service.get_team_captains(team_name, session)

@team_router.post(
    "/name/{team_name}/captains/{player_id}",
    dependencies=[Depends(require_team_captain)]
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
    dependencies=[Depends(require_team_captain)]
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