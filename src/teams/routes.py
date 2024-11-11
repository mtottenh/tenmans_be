from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
from src.db.main import get_session
from src.players.dependencies import AccessTokenBearer, CaptainChecker, RoleChecker, get_current_player

from .models import Team
from .schemas import TeamCreateModel,  RosterUpdateModel, PlayerId, PlayerName, RosterEntryModel,RosterPendingUpdateModel
from .service import TeamService, RosterService
from src.players.service import PlayerService
from src.seasons.service import SeasonService
from src.players.models import Player

team_router = APIRouter(prefix="/teams")

access_token_bearer = AccessTokenBearer()
player_service = PlayerService()
team_service = TeamService()
season_service = SeasonService()
roster_service = RosterService()
admin_checker = Depends(RoleChecker(["admin", "user"]))
captain_checker=  Depends(CaptainChecker)

@team_router.get("/", response_model=List[Team])
async def get_all_teams(
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    return await team_service.get_all_teams(session)

# TODO - Make the user who created the team a team captain?
# - How do we ensure that admins who create teams don't get added as captains?
# - Maybe just have an API parameter of team_captian: optional[str] and have the front-end supply it.
@team_router.post("/", dependencies=[admin_checker])
async def create_team(
    team_data: TeamCreateModel,
    player_details = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    name = team_data.name
    team_exists = await team_service.team_exists(name, session)
    if team_exists:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Team with name '{name}' already exists",
        )
    new_team = await team_service.create_team(team_data, session)
    captain = await team_service.create_captain(new_team, player_details, session)
    return new_team

@team_router.get("/id/{id}")
async def get_team_by_id(
    id: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    team = await team_service.get_team_by_id(id, session)
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team with name '{id}' not found",
        )
    return team

@team_router.get("/name/{name}")
async def get_team_by_name(
    name: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    team = await team_service.get_team_by_name(name, session)
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team with name '{name}' not found",
        )
    return team

@team_router.patch("/name/{team_name}/roster", dependencies=[captain_checker])
async def update_team_roster(
    team_name: str,
    roster: RosterUpdateModel,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    
    current_season = await season_service.get_active_season(session)
    if current_season is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No active season configured in DB")
    team = await team_service.get_team_by_name(team_name, session)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Team with name '{team_name}' not found")
    skipped =[]
    validated_players=[]
    for p in roster.players:
        player = None
        if isinstance(p, PlayerName):
            player = await player_service.get_player_by_name(p.name, session)
        if isinstance(p, PlayerId):
            player = await player_service.get_player(p.id, session)
        if player is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Player with name {p} not found")
        validated_players.append(player)
    for player in validated_players:
        player_already_on_roster = await roster_service.player_on_team(player, team, current_season, session)
        if player_already_on_roster:
            skipped.append(player.name)
        else:
            await roster_service.add_player_to_team_roster(player, team, current_season, session)
    if skipped:
        return JSONResponse(content={"players_already_team" : { "team" : team.name, "players" : skipped}})


@team_router.patch("/name/{team_name}/roster/active", dependencies=[captain_checker])
async def accept_team_join_request(
    team_name: str,
    roster_update:  RosterPendingUpdateModel,
    session: AsyncSession = Depends(get_session),
    player_details = Depends(get_current_player)
):
    current_season = await season_service.get_active_season(session)
    if current_season is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No active season configured in DB")
    team = await team_service.get_team_by_name(team_name, session)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Team with name '{team_name}' not found")

    player_is_captain = await team_service.player_is_team_captain(player_details, team, session)
    if not player_is_captain:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Only team captains can perform roster updates")

    player = await player_service.get_player(roster_update.player.id, session)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Player with uid {roster_update.player} not found")
    player_is_pending = await roster_service.player_is_pending(player,team,current_season,session)
    if not player_is_pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Player with uid {roster_update.player} not pending on the roster")
    roster_update = await roster_service.set_player_active(player, team, current_season, session)
    return roster_update


@team_router.get("/name/{team_name}/roster/active", response_model=List[Team])
async def accept_team_join_request(
    team_name: str,
    session: AsyncSession = Depends(get_session),
):
    current_season = await season_service.get_active_season(session)
    if current_season is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No active season configured in DB")
    teams = await roster_service.get_teams_with_min_players(current_season.id, 5, session)
    return teams
    


@team_router.get("/name/{team_name}/captains", response_model=List[Player])
async def get_team_captains(
    team_name: str,
    session: AsyncSession = Depends(get_session)
):
    captains = await team_service.get_team_captains(team_name, session)
    return captains

@team_router.patch("/name/{team_name}/captains", dependencies=[captain_checker])
async def add_team_captains(
    team_name: str,

    session: AsyncSession = Depends(get_session)
):
    #captains = await team_service.create_captain(team_name, player_name)
    pass

@team_router.get("/name/{team_name}/roster", response_model=List[RosterEntryModel])
async def get_team_roster(
    team_name: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    current_season = await season_service.get_active_season(session)
    if current_season == None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active season configured.")
    current_roster = await roster_service.get_roster(team_name,current_season,session)
    team_roster = []
    for (player, pending) in current_roster:
        team_roster.append(RosterEntryModel(player=player,pending=pending))
    return team_roster
