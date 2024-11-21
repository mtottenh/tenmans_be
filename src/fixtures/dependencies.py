from fastapi import Request, HTTPException, WebSocket, status, Depends
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlmodel.ext.asyncio.session import AsyncSession

from src.db.main import get_session
from src.fixtures.MapPicker.commands import ConnectionManagerMode, Map
from src.fixtures.MapPicker.state_machine import MapPickerModel, WebSocketStateMachine
from src.fixtures.service import FixtureService
from src.players.dependencies import get_current_player, get_current_season
from src.players.models import Player
from src.seasons.models import Season


FIXTURE_ORCHESTRATORS={}
class GetWSFixtureOrchestrator:
    async def __call__(self, request: Request, current_player: Player = Depends(get_current_player), current_season: Season = Depends(get_current_season), session=Depends(get_session)) -> WebSocketStateMachine:
        if not 'fixture_id' in request.path_params and not 'pug_id' in request.path_params:
                    return False
  
        if not request.path_params['fixture_id'] in FIXTURE_ORCHESTRATORS:
            map_pool=['de_nuke', 'de_inferno', 'de_train', 'de_ancient', 'de_cbble']
            team_1="Team A"
            team_2="Team B"
            FIXTURE_ORCHESTRATORS[request.path_params['fixture_id']] = WebSocketStateMachine(MapPickerModel(map_pool, team_1, team_2), ConnectionManagerMode.BO3)

        return  FIXTURE_ORCHESTRATORS[request.path_params['fixture_id']] 

fixture_service = FixtureService()

PUG_ORCHESTRATORS={}
class GetWSPugOrchestrator:
    async def __call__(self, request: WebSocket, session=Depends(get_session)) -> WebSocketStateMachine:
        print(f'req: {request.path_params}')
        if  not 'pug_id' in request.path_params:
            return False
        pug_id = request.path_params['pug_id']
        if not pug_id  in PUG_ORCHESTRATORS:
            map_pool=['de_nuke', 'de_inferno', 'de_train', 'de_ancient', 'de_cbble']
            map_pool=[Map(name=x) for x in map_pool]
            (team_1, team_2) = await fixture_service.get_pug_team_names(pug_id, session)
            print(f"Creating new PUG for {team_1} and {team_2} map_pool{map_pool}")
            machine = WebSocketStateMachine(MapPickerModel(map_pool, team_1, team_2), ConnectionManagerMode.BO3)
            PUG_ORCHESTRATORS[pug_id] = machine
        return PUG_ORCHESTRATORS[pug_id]
