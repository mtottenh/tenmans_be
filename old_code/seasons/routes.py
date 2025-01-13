from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.main import get_session
from src.seasons.models import Season, SeasonState
from .service import SeasonService
from src.players.dependencies import AccessTokenBearer, RoleChecker, get_current_player
from .schemas import  SeasonCreateModel
from src.fixtures.service import FixtureGenerationError, FixtureService

access_token_bearer = AccessTokenBearer()
season_service = SeasonService()
fixture_service = FixtureService()
season_router = APIRouter(prefix="/seasons")
admin_checker = Depends(RoleChecker(["admin", "user"]))

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
    print("Looking up active season")
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

@season_router.post("/id/{season_id}/group_stage/generate",dependencies=[admin_checker])
async def generate_group_stage(
    season_id: str,
    session: AsyncSession = Depends(get_session),

):
    # Check that the group stage was generated for this season?
    season = await season_service.get_season(season_id, session)
    if season.state != SeasonState.NOT_STARTED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Season {season_id} has already stared, will not regenerate group stage")
    try:
        await fixture_service.create_round_robin_fixtures_with_rounds(season.id,session)
        season.state = SeasonState.GROUP_STAGE
        session.add(season)
        await session.commit()
        await session.refresh(season)
    except FixtureGenerationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{e.args[0]}")
    return season



@season_router.get("/id/{season_id}", dependencies=[admin_checker], response_model=Season)
async def get_season_with_id(
    season_id: str,
    session: AsyncSession = Depends(get_session)
):
    season = await season_service.get_season(season_id, session)
    return season

@season_router.post("/id/{season_id}/knockout_tournament/start",dependencies=[admin_checker])
async def start_knockout_tournament(
    season_id: str,
    session: AsyncSession = Depends(get_session),

):
    season = await season_service.get_season(season_id, session)
    if season.state != SeasonState.GROUP_STAGE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Season {season_id} is currently in {season.state} will not initiate knockout tournament")
    group_stage_finished = await season_service.group_stage_played_for_season(season, session)
    if not group_stage_finished:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Season {season_id} hasn't finished the group stage")  
    try:
        # TODO - add validation that all group stage rounds have been played.
        await fixture_service.initiate_knockout_tournament(season_id, session)
        season.state = SeasonState.KNOCKOUT_STAGE
        await session.commit()
        await session.refresh(season)
    except FixtureGenerationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{e.args[0]}")
    return season

@season_router.post("/id/{season_id}/knockout_tournament/create_next_round",dependencies=[admin_checker])
async def start_knockout_tournament(
    season_id: str,
    session: AsyncSession = Depends(get_session),

):
    season = await season_service.get_season(season_id, session)
    if season.state != SeasonState.KNOCKOUT_STAGE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Season {season_id} is currently in {season.state} can't generate the next stage of a knockout tournament")
    try:
        # TODO - add validation that all group stage rounds have been played.
        knockout_fixtures = await fixture_service.schedule_next_knockout_round(season_id, session)
        session.add_all(knockout_fixtures)
        await session.commit()
    except FixtureGenerationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{e.args[0]}")
    return season