from datetime import datetime
import logging
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse

from sqlalchemy import Null

from src.fixtures.MapPicker.state_machine import WSConnMgr, WebSocketStateMachine
from src.fixtures.dependencies import GetWSFixtureOrchestrator, GetWSPugOrchestrator
from src.fixtures.MapPicker.commands import WSSCommand
from src.players.models import Player, PlayerRoles
from .service import FixtureService, CreateFixtureError, ResultsService
from .schemas import FixtureCreateModel, FixtureDate, PugCreateModel, ResultConfirmModel, ResultCreateModel
from .models import Fixture, Pug,  Result, Round
from src.db.main import get_session
from sqlmodel.ext.asyncio.session import AsyncSession
from src.players.dependencies import AccessTokenBearer, get_current_player
from src.teams.service import TeamService
from src.seasons.models import Season
from src.seasons.service import SeasonService
from src.seasons.dependencies import get_active_season
from typing import List, Tuple
from src.config import Config
logger = logging.getLogger('uvicorn.error')
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
    player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    
    fixture = await fixture_service.get_fixture_by_id(result_data.fixture_id, session)
    if fixture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invalid fixture ID {result_data.fixture_id}")
    if player.role == PlayerRoles.ADMIN:
        pass # TODO - Allow Admin's to submit pre-confirmed results.
        new_result = await results_service.add_result(result_data, Null, session, confirmed=True)
        if new_result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No fixture with id {result_data.fixture_id}")
        return new_result
    else:
        team_1 = await team_service.get_team_by_id(fixture.team_1, session)
        team_2 = await team_service.get_team_by_id(fixture.team_2, session)
        player_is_team_1_captain = await team_service.player_is_team_captain(player, team_1, session)
        player_is_team_2_captain = await team_service.player_is_team_captain(player, team_2, session)
        submitted_by=''
        if player_is_team_1_captain:
            submitted_by=team_1.id
        elif player_is_team_2_captain:
            submitted_by=team_2.id
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Result must be submitted by a team captain")
        new_result = await results_service.add_result(result_data, submitted_by, session)
        if new_result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No fixture with id {result_data.fixture_id}")
        return new_result

@fixture_router.patch("/{fixture_id}/result/confirm", response_model=Result)
async def confirm_result(
    fixture_id: str,
    player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    fixture = await fixture_service.get_fixture_by_id(fixture_id, session)
    if fixture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invalid fixture ID {fixture_id}")
    team_1 = await team_service.get_team_by_id(fixture.team_1, session)
    team_2 = await team_service.get_team_by_id(fixture.team_2, session)
    if team_1 is None or team_2 is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid fixture team IDs")
    player_is_team_1_captain = await team_service.player_is_team_captain(player, team_1, session)
    player_is_team_2_captain = await team_service.player_is_team_captain(player, team_2, session)
    if not (player_is_team_1_captain or player_is_team_2_captain):
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Player {player.name} is not a team captain!")
    print("Player *is* a team Captain ")
    if (fixture.result.submitted_by == team_1.id and player_is_team_2_captain) or (fixture.result.submitted_by == team_2.id and player_is_team_1_captain):
        result = await results_service.confirm_result(ResultConfirmModel(fixture_id=str(fixture.id)), session)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Result must be confirmed by opposing team captain")
    return result
    
    
@fixture_router.patch("/{fixture_id}", response_model=Fixture)
async def update_fixture_date(
    fixture_id: str,
    body: FixtureDate,
    session: AsyncSession = Depends(get_session)
):
    scheduled_date = datetime.now()
    try:
        scheduled_date = datetime.strptime(body.scheduled_at, "%Y-%m-%dT%H:%M")
    except ValueError as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid date, please use format YYYY-MM-DDTHH:MM")
    result = await fixture_service.update_fixture_date(fixture_id, scheduled_date, session)
    if result is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid fixture ID {fixture_id}")
    return result


@fixture_router.get("/current_season", response_model=List[Fixture])
async def get_all_fixtures_for_active_season(
    season: Season = Depends(get_active_season),
    session: AsyncSession = Depends(get_session)
):
    if season is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active season currently set in DB.")
    return RedirectResponse(url=API_VERSION_SLUG + fixture_router.url_path_for("get_all_fixtures_for_season",season_id=season.id))

@fixture_router.get("/{fixture_id}",   status_code=status.HTTP_200_OK, response_model=Fixture)
async def get_fixture(
    fixture_id: str,
    session: AsyncSession = Depends(get_session)
):
    fixture = await fixture_service.get_fixture_by_id(fixture_id,session)
    if fixture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No fixture with id {fixture_id}")
    return fixture

@fixture_router.get("/{fixture_id}/result",   status_code=status.HTTP_201_CREATED, response_model=Result)
async def add_fixture_result(
    fixture_id: str,
    session: AsyncSession = Depends(get_session)
):
    new_result = await results_service.get_result_for_fixture(fixture_id,session)
    if new_result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No result for fixture with id {fixture_id}")
    return new_result

@fixture_router.get("/season/{season_id}", response_model=List[Tuple[Fixture, Round]])
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

@fixture_router.post('/new_pug', response_model=Pug)
async def create_new_pug(pug_data: PugCreateModel, session: AsyncSession = Depends(get_session)):
    # Insert a pug into the pugs table
    # Should at-least contain team_names - can be updated later
    # Via the websocket
    # Return a response with the fixture ID to connect the websocket to. 
    return await fixture_service.create_pug(pug_data, session)


ws_fixture_orchestrator_manager = GetWSFixtureOrchestrator()
ws_pug_orchestrator_manager = GetWSPugOrchestrator()

@fixture_router.websocket('/pug/id/{pug_id}/ws')
async def fixture_websocket_handler(
    pug_id: str,
    websocket: WebSocket,
    ws_manager: WebSocketStateMachine = Depends(ws_pug_orchestrator_manager)
):
    mgr = WSConnMgr()
    await mgr.accept(websocket)
    await ws_manager.add_conn(mgr)
    try:

        async for cmd in mgr.start():
            await ws_manager.process_event(cmd, mgr)

    except WebSocketDisconnect:
        ws_manager.remove_conn(mgr)
    except Exception as e:
        pass


@fixture_router.websocket('/id/{fixture_id}/ws')
async def fixture_websocket_handler(
    fixture_id: str,

):
    pass