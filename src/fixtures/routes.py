from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from .service import FixtureService, CreateFixtureError, ResultsService
from .schemas import FixtureCreateModel, ResultCreateModel
from .models import Fixture,  Result
from src.db.main import get_session
from sqlmodel.ext.asyncio.session import AsyncSession
from src.players.dependencies import AccessTokenBearer
from src.teams.service import SeasonService, TeamService
from src.teams.models import Season
from src.teams.dependencies import get_active_season
from typing import List
from src.config import Config

API_VERSION_SLUG=f"/api/{Config.API_VERSION}"
fixture_router = APIRouter(prefix="/fixtures")
fixture_service = FixtureService()
team_service = TeamService()
season_service = SeasonService()
results_service = ResultsService()
access_token_bearer = AccessTokenBearer()


#Todo - Implement Auth on these endpoints.
# fixture post endpoint should only be accessible via admin
# fixture result endpoint should only be accessible via team captains for the fixture_id

@fixture_router.post("/", status_code=status.HTTP_201_CREATED, response_model=Fixture)
async def create_new_fixture(
    fixture_data: FixtureCreateModel,
    session: AsyncSession = Depends(get_session)
):
    new_fixture = await fixture_service.create_fixture_for_season(fixture_data, session)
    if isinstance(new_fixture, CreateFixtureError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{new_fixture}")
    return new_fixture


@fixture_router.post("/{fixture_id}/result",   status_code=status.HTTP_201_CREATED, response_model=Result)
async def add_fixture_result(
    result_data: ResultCreateModel,
    session: AsyncSession = Depends(get_session)
):
    new_result = await results_service.add_result(result_data,session)
    if new_result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No fixture with id {result_data.fixture_id}")
    return new_result

@fixture_router.get("/current_season", response_model=List[Fixture])
async def get_all_fixtures_for_active_season(
    season: Season = Depends(get_active_season),
    session: AsyncSession = Depends(get_session)
):
    if season is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active season currently set in DB.")
    return RedirectResponse(url=API_VERSION_SLUG + fixture_router.url_path_for("get_all_fixtures_for_season",season_id=season.id))


@fixture_router.get("/season/{season_id}", response_model=List[Fixture])
async def get_all_fixtures_for_season(
    season_id: str,
    session: AsyncSession = Depends(get_session)
):
    season = await season_service.get_season(season_id, session)
    if season is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Season with id {season_id} not found")
    fixtures = await fixture_service.get_fixtures_for_season(season, session)
    return fixtures

@fixture_router.get("/team/{team_name}/current_season", response_model=List[Fixture])
async def get_all_fixtures_for_team_in_active_season(
    team_name: str,
    season: Season = Depends(get_active_season),
    session: AsyncSession = Depends(get_session)
):
    
    if season is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active season currently set in DB.")
    team = await team_service.get_team_by_name(team_name, session)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Team with name '{team_name}' not found")
    return RedirectResponse(url=API_VERSION_SLUG+fixture_router.url_path_for("get_all_fixtures_for_team_in_season",team_name=team.name,season_id=season.id))


@fixture_router.get("/team/{team_name}/season/{season_id}",  response_model=List[Fixture])
async def get_all_fixtures_for_team_in_season(
    team_name: str,
    season_id: str,
    session: AsyncSession = Depends(get_session)
):
    season = await season_service.get_season(season_id, session)
    if season is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Season with id {season_id} not found")
    team = await team_service.get_team_by_name(team_name, session)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Team with name '{team_name}' not found")
    fixtures = await fixture_service.get_fixtures_for_team_in_season(team,season,session)
    return fixtures


@fixture_router.get("/team/{team_name}/season/{season_id}/results", response_model=List[Result])
async def get_results_for_team_in_season(
    team_name: str,
    season_id: str,
    session: AsyncSession = Depends(get_session)
):
    

    
    season = await season_service.get_season(season_id, session)
    if season is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Season with id {season_id} not found")
    
    team = await team_service.get_team_by_name(team_name, session)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Team with name '{team_name}' not found")

    results = await results_service.get_results_for_team_in_season(team, season, session)
    return results