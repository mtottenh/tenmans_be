from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
from src.db.main import get_session
from src.players.dependencies import AccessTokenBearer, RoleChecker
from .models import Team
from .schemas import TeamCreateModel, SeasonCreateModel, RosterUpdateModel
from .service import TeamService, SeasonService, RosterService
from src.players.service import PlayerService

team_router = APIRouter()
season_router = APIRouter()
access_token_bearer = AccessTokenBearer()
player_service = PlayerService()
team_service = TeamService()
season_service = SeasonService()
roster_service = RosterService()
admin_checker = Depends(RoleChecker(["admin", "user"]))


@team_router.get("/", response_model=List[Team])
async def get_all_teams(
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    return await team_service.get_all_teams(session)


@team_router.post("/", dependencies=[admin_checker])
async def create_team(
    team_data: TeamCreateModel,
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
    return new_team


@team_router.get("/{name}")
async def get_team_by_name(
    name: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    team = await team_service.get_team_by_name(name)
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team with name '{name}' not found",
        )
    return team

# TODO:  Make a 'team captain' checker.
@team_router.patch("/{name}/roster", dependencies=[admin_checker])
async def update_team_roster(
    name: str,
    roster: RosterUpdateModel,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    current_season = await season_service.get_active_season(session)
    team = await team_service.get_team_by_name(name, session)
    skipped =[]
    validated_players=[]
    for p in roster.players:
        player = await player_service.get_player_by_name(p, session)
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

@team_router.get("/{name}/roster")
async def get_team_roster(
    name: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    current_season = await season_service.get_active_season(session)
    team = await team_service.get_team_by_name(name, session)
    # print(f"Team : {team}")
    # links =  team.player_links
    # for link in links:
    #     print(link)
    # return links
    current_roster = await roster_service.get_roster(team,current_season,session)
    return current_roster




@season_router.post("/", dependencies=[admin_checker])
async def create_new_season(
    season: SeasonCreateModel,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    season_name = season.name
    season_exists = await season_service.season_exists(season_name, session)
    if season_exists:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Season with name '{season_name}' already exists",
        )
    new_season = await season_service.create_new_season(season, session)
    return new_season

@season_router.get("/")
async def get_seasons(
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    seasons = await season_service.get_all_seasons(session)
    if not seasons:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No seasons defined",
        )
    return seasons

@season_router.get("/active")
async def get_active_season(
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    season = await season_service.get_active_season(session)
    if season is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active season set in database",
        )
    return season

@season_router.patch("/active/{season_name}", dependencies=[admin_checker])
async def set_active_season(
    season_name: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    season = await season_service.get_season_by_name(season_name, session)
    if season is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Season with name '{season_name}' not found in DB.",
        )
    setting = await season_service.set_active_season(season, session)
    if setting is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Error setting active season in database",
        )
    return setting
    