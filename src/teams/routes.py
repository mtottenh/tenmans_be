from fastapi import APIRouter, Depends, Form, HTTPException,  status
from fastapi.responses import FileResponse

from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
import os

from auth.schemas import PlayerPublic

from competitions.models.seasons import Season
from competitions.season.dependencies import get_active_season
from db.main import get_session
from auth.dependencies import get_current_player
from auth.models import Player

from teams.schemas import (
    PlayerRosterHistory,
    TeamDetailed,
)
from teams.base_schemas import TeamCreateRequest, TeamUpdate
from teams.service.team import TeamServiceError
from .dependencies import require_team_captain_by_name, require_team_captain_by_id
from config import Config
from services.team import team_service
from services.upload import upload_service
from services.auth import auth_service

team_router = APIRouter(prefix="/teams")

@team_router.get("/", response_model=List[TeamDetailed])
async def get_all_teams(
    
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get all teams with detailed information."""
    return await team_service.get_all_teams_with_details(session)

@team_router.get("/player/{player_id}", response_model=PlayerRosterHistory)
async def get_all_teams(
    player_id: str,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    return await team_service.get_teams_for_player_by_player_id(player_id, session)

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
        new_team = await team_service.get_team_by_id(team_id=new_team.id, session=session)
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
        new_captain = await auth_service.get_player_by_id(player_id, session)
        
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
        player = await auth_service.get_player_by_id(player_id, session)
        
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
        captain = await team_service.get_captain(team, player, session)
        await team_service.remove_captain(
            captain,
            actor=current_player,
            session=session
        )
        
        return {"status": "success"}

    except TeamServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@team_router.delete(
    '/id/{team_id}/roster/{player_id}',
    dependencies=[Depends(require_team_captain_by_id)]
)
async def remove_player_from_team(
    team_id: str,
    player_id: str,
    current_season: Season = Depends(get_active_season),
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    '''Remove a player from a team roster by player ID'''
    roster_member = await team_service.remove_player_from_team_roster(team_id, 
                                                                   player_id,
                                                                   current_season.id,
                                                                   actor=current_player,
                                                                   session=session)
    


@team_router.patch('/id/{team_id}',
        dependencies=[Depends(require_team_captain_by_id)]                   
)
async def update_team_settings(
    team_id: str,
    team_update_details: TeamUpdate = Form(...),
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    pass