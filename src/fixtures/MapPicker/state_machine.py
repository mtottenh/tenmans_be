
from copy import deepcopy
from typing import Dict, List, NamedTuple, NewType, Optional, AsyncGenerator
from fastapi import WebSocket, WebSocketDisconnect
from transitions import Machine, State
from transitions.extensions import HierarchicalAsyncMachine, AsyncMachine
from .commands import *
from transitions.extensions.nesting import NestedState
from asyncio import Event, Task, create_task, CancelledError
from asyncio import timeout as async_timeout
from pydantic import BaseModel, ConfigDict

NestedState.separator = '↦'
import logging
logging.basicConfig(encoding='utf-8', level=logging.DEBUG)
logger = logging.getLogger('WSSM')
class MapPickerModel():
    def __init__(self, map_pool: List[Map], team_1, team_2):
        self.map_pool: List[Map] = map_pool
        self.original_map_pool: List[Map] = deepcopy(map_pool)
        self.team_1 = team_1
        self.team_2 = team_2
        self.current_team = self.team_1
        self.picked_maps:  List[Map] = []
        self.banned_maps:  List[Map] = []
        self.finalized = False

    def reset_picks_bans(self):
        self.map_pool = deepcopy(self.original_map_pool)
        self.current_team = self.team_1
        self.picked_maps = []
        self.banned_maps = []
        self.finalized = False

    def get_map_by_name(self, map_name) -> Optional[Map]:
        map = [ x for x in self.map_pool if x.name == map_name ]
        if len(map != 1):
            logger.error(f"Couldn't find map in current map pool {map_name}")
            return None
        return map[0]

    def ban_map(self, map_name: str, banning_team: MapState):
        banned_map = self.get_map_by_name(map_name)
        banned_map.state = banning_team
        self.map_pool.remove(banned_map)
        self.banned_maps.append(banned_map)

    def get_picker_state(self) -> List[Map]:
        maps = []
        # Maps yet to be picked/banned
        for m in self.map_pool:
            maps.append(m)
        for m in self.picked_maps:
            maps.append(m)
        for m in self.banned_maps:
            maps.append(m)
        return maps

    def __repr__(self):
        return f"MapPickerModel(map_pool={self.map_pool}, team_1={self.team_1}, team_2={self.team_2}, picked_maps={self.picked_maps})"

BO1_CONF={
    "name" : "banning_phase",
    "states" : [  "team_1_ban",
                  "team_2_ban",
                  "final_map"
            ],
    "transitions" : [
        {"trigger":"team_1_ban_map", "source": 'team_1_ban', 'dest':'team_2_ban', 'conditions': ['is_valid_map', 'has_maps_remaining'], 'after' : 'process_ban' },
        {"trigger":"team_2_ban_map", "source": 'team_2_ban', 'dest':'team_1_ban', 'conditions': ['is_valid_map', 'has_maps_remaining'], 'after' : 'process_ban' },
        {"trigger":"determine_final_map", 'source': ['team_1_ban', 'team_2_ban'], 'dest':'final_map', 'conditions': ['only_one_map_remaining'], 'after' : 'finalize_map' },

    ],
    "initial": "team_1_ban"
}
# Define hierarchical states
BO3_CONF={
    "name" : "pick_phase",
    "states" : [
            "team_1_map",
            "team_2_side",
            "team_2_map",
            "team_1_side",
            { "name" : "final_maps", "on_enter" : 'finalize_maps' },
            deepcopy(BO1_CONF),
        ],
    "transitions" : [
        {"trigger": "team_1_pick_map", "source": "team_1_map", "dest" : "team_2_side", "conditions" : ["is_valid_map"], "after" : "process_pick_t1"},
        {"trigger": "team_2_pick_map", "source": "team_2_map", "dest" : "team_1_side", "conditions" : ["is_valid_map"], "after" : "process_pick_t2"},
        {"trigger": "team_2_pick_side", "source": "team_2_side", "dest" : "team_2_map", "after" : "record_side"},
        {"trigger": "team_1_pick_side", "source": "team_1_side", "dest" : "banning_phase", "after" : "record_side"},

    ],
    "initial" : "team_1_map"
}
BO3_CONF['states'][-1]['remap'] = { 'final_map' : 'final_maps'}


class BestOfOneStateMachine:
    """State machine for banning maps."""
    def __init__(self, model: MapPickerModel):
        self.model = model

    def is_valid_map(self, event: BanMapCmd):
        """Check if the map is valid."""
        print(f"Checking if {event.map_name} in {self.model.map_pool}")
        return event.map_name in [ x.name for x in self.model.map_pool ]

    def has_maps_remaining(self, event: BanMapCmd):
        """Check if more than one map remains."""
        return len(self.model.map_pool) > 1

    def only_one_map_remaining(self, event: BanMapCmd):
        """Check if only one map remains."""
        return len(self.model.map_pool) == 1

    def finalize_map(self, event):
        print("Finalizing decider map")
        self.model.finalized=True
        final_map = self.model.map_pool.pop()
        final_map.oppo_side = Side.KN
        self.model.picked_maps.append(final_map)

    async def process_ban(self, event: BanMapCmd):
        """Handle the banning of a map."""
        banning_team = MapState.TEAM_1_BANNED if self.model.current_team == self.model.team_1 else MapState.TEAM_2_BANNED
        self.model.ban_map(event.map_name, banning_team)
        print(f"{self.model.current_team} banned {event.map_name}. Remaining maps: {self.model.map_pool}")
        self.model.current_team = self.model.team_2 if self.model.current_team == self.model.team_1 else self.model.team_1
        if self.only_one_map_remaining(event):
            print(f"Triggering determine_final_map")
            await self.trigger('determine_final_map', event)


class BestOfThreeStateMachine(BestOfOneStateMachine):
    """State machine for a 'Best of Three' map selection process with side selection."""
    def __init__(self, model: MapPickerModel):
        self.model = model

    def process_pick_t1(self, event):
        self._process_pick(event, MapState.TEAM_1_PICK)

    def process_pick_t2(self, event):
        self._process_pick(event, MapState.TEAM_2_PICK)

    async def process_pick(self, event: PickMapCmd, team_pick: MapState):
        """Handle the picking of a map."""
        map = self.model.get_map_by_name(event.map_name)
        map.state = team_pick
        self.model.map_pool.remove(map)
        self.model.picked_maps.append(map)  # Side to be chosen later
        logger.info(f"Map {event.map_name} has been picked. Remaining maps: {self.model.map_pool}")

    def record_side(self, event: PickSideCmd):
        """Record the side chosen for the last picked map."""
        self.model.picked_maps[-1].side = event.side
        map_name = self.model.picked_maps[-1].name
        print(f"Side '{event.side}' has been chosen for map {map_name}.")

    def finalize_maps(self, event = None):
        """Finalize the maps for the Best of Three series."""
        print("Final Best of Three Maps:")
        for i, map in enumerate(self.model.picked_maps):
            if map.state != None:
                print(f"Game {i + 1}: Map - {map.name} Team - {map.state} Side - {map.oppo_side}")
            else:
                print(f"Game {i + 1}: Map - {map.name} Side - {map.oppo_side}")


ESTABLISHMENT_TIMEOUT=30

class WSConnInvalidAckException(Exception):
    pass

class WSConnMgr:
    def __init__(self):
        states = [ 'listen', 'accepted', 'established', 'close' ]
        transtions=[ {'trigger' : 'accept', 'source' : 'listen', 'dest' : 'accepted', 'after' : 'handle_accept'},
                     {'trigger' : 'identify_client', 'source' : 'accepted', 'dest': 'established', 'after' : 'handle_identify_client' },
                     {'trigger' : 'new_msg', 'source' : ['accepted', 'established'], 'dest' : None, 'after' : 'handle_msg' },
                     {'trigger' : 'connection_error', 'source' : ['accepted', 'established'], 'dest' : 'close', 'after' :'handle_connection_error'},
                     {'trigger' : 'disconnect', 'source' : ['accepted', 'established'], 'dest' : 'close', 'after' : 'handle_disconnect' }
                    ]
        self.machine = AsyncMachine(model=self, states=states, transitions=transtions, initial='listen')
        self.ws: Optional[WebSocket] = None
        self.last_seq_no: int = 0
        self.client_id: Optional[str] = None
        self.name: Optional[str] = None
        self._establishment_event = Event()
        self._timeout_task: Optional[Task] = None

    async def handle_accept(self, ws: WebSocket): #TODO - pass Player in here so we have more than just client ID (which is really connection ID.)
        await ws.accept()
        self.ws = ws

    async def handle_identify_client(self, cmd: IdentifyClientCmd):
        self.last_seq_no = cmd.seq_no
        self.client_id = cmd.client_id
        self.name = cmd.name
        self._establishment_event.set()

    async def handle_connection_error(self, errmsg):
        if self.ws:
            await self.ws.send_json(ServerErrResp(message=f"{errmsg}").model_dump())
            await self.ws.close()
            self.ws = None

    async def handle_disconnect(self):
        if self.ws:
            logger.info(f"Disconnecting client: {self.ws.client}")
            await self.ws.close()
            self.ws = None

    async def identification_timeout(self) -> None:
        """Watch for identification timeout"""
        try:
            async with async_timeout(ESTABLISHMENT_TIMEOUT):
                await self._establishment_event.wait()
        except TimeoutError:
            logger.error("Client identification timeout")
            if self.ws:
                await self.ws.close(code=4000, reason="Identification timeout")

            raise

    async def ack_last_cmd(self):
        await self.ws.send_json(AckResp(seq_no=self.last_seq_no).model_dump())

    async def handle_msg(self, cmd: BaseCmd):
        if cmd.seq_no != (self.last_seq_no + 1):
            await self.ws.send_json(InvalidAckResp(got=cmd.seq_no, expected=self.last_seq_no + 1).model_dump())
            raise  WSConnInvalidAckException("Invalid Ack!")
        else:
            self.last_seq_no = cmd.seq_no

    def __repr__(self):
        return f"WSConnMgr(name={self.name},id={self.client_id},seq_no={self.last_seq_no},sock={self.ws})"


    async def start(self) -> AsyncGenerator:
        """Start both message processing and identification timeout"""
        # Create the timeout task
        self._timeout_task = create_task(self.identification_timeout())

        try:
            async for cmd in self.process_messages():
                yield cmd
        finally:
            # Clean up timeout task if it's still running
            if self._timeout_task and not self._timeout_task.done():
                self._timeout_task.cancel()
                try:
                    await self._timeout_task
                except CancelledError:
                    pass


    async def process_messages(self) -> AsyncGenerator:
        """Process incoming messages"""
        try:
            async for data in self.ws.iter_json():
                cmd: WSSCommand = WSSCommand.validate_python(data)
                logger.debug(f"Valid Cmd packet received {cmd}")

                if cmd.cmd == 'identify_client':
                    await self.identify_client(cmd)
                else:
                    await self.new_msg(cmd)

                yield cmd

                if self.ws is not None:
                    await self.ack_last_cmd()

        except CancelledError:
            logger.info("Message processing cancelled")
            raise


class TeamType(BaseModel):
    name: str
    players: List[WSConnMgr]
    model_config = ConfigDict(arbitrary_types_allowed=True)

class WebSocketStateMachine(BestOfThreeStateMachine):
    """Parent state machine with hierarchical map picker integration."""
    def __init__(self, model: MapPickerModel, picker_type: ConnectionManagerMode):
        self.model = model
        self.map_picker_conf = None
        self.active_connections: List[WSConnMgr] = []
        self.teams:  tuple[TeamType, TeamType]= (TeamType( name=model.team_1, players=[]), TeamType(name=model.team_2, players=[]))
        logger.info(f"Picker Type: {picker_type}")
        if picker_type == ConnectionManagerMode.BO1:
            self.map_picker = BO1_CONF
        elif picker_type == ConnectionManagerMode.BO3:
            self.map_picker = BO3_CONF
        else:
            raise ValueError(f"Invalid ConnectionManagerMode {picker_type}")
        self.map_picker['remap'] = { "final_maps" : "done" }
        # Define states
        logger.debug(f"PType: {picker_type} States: {self.map_picker}")
        states = [
            "ready",
            self.map_picker,
            "done"
        ]

        # Initialize the state machine
        self.machine = HierarchicalAsyncMachine(model=self, states=states, initial="ready")

        # Add transitions
        if picker_type == ConnectionManagerMode.BO1:
            self.machine.add_transition(
                trigger="start_map_picker",
                source="ready",
                dest="banning_phase",
                after=self.update_game_state
            )
        elif picker_type == ConnectionManagerMode.BO3:
            self.machine.add_transition(
                trigger="start_map_picker",
                source="ready",
                dest="pick_phase",
                after=self.update_game_state
            )
        self.machine.add_transition(
            trigger="identify_client",
            source="*",
            dest=None
        )
        # Dynamically add general command transitions
        general_commands = [
            CmdType.chat,
            CmdType.team_chat,
        ]
        for cmd in general_commands:
            self.machine.add_transition(
                trigger=cmd,  # Dynamically use the command name as the trigger
                source="*",
                dest=None,  # Stay in the current state
                after=self.process_chat_cmd
            )

        # In case we need to abort on user DC.
        self.machine.add_transition(
            trigger="abort",
            source="*",
            dest="ready",
            after=self.reset_picks_and_bans
        )
        self.machine.add_transition(
            trigger=CmdType.set_team_name,
            source='ready',
            dest=None,
            after=self.process_set_team_name
        )

        self.machine.add_transition(
            trigger=CmdType.switch_teams,
            source='ready',
            dest=None,
            after=self.process_switch_teams
        )

        self.machine.add_transition(
            trigger=CmdType.join_team,
            source='ready',
            dest=None,
            after=self.process_join_team
        )

    async def process_ban(self, event: BanMapCmd, mgr: WSConnMgr):
        await super().process_ban(event)
        await self.update_game_state(event, None)

    async def process_pick(self, event: PickMapCmd, team_pick: MapState):
        await super().process_pick(event, team_pick)
        await self.update_game_state(event, None)

    async def record_side(self, event: PickSideCmd):
        await super().record_side(event)
        await self.update_game_state(event, None)

    async def update_game_state(self, cmd: BaseCmd, mgr : WSConnMgr):
        await self._broadcast(MapPicksResp(map_pool=self.model.get_picker_state()))
        state = self.state.split(NestedState.separator)[-1] if NestedState.separator in self.state else self.state
        await self._broadcast(PhaseResp(state=state))

    async def process_event(self, event: BaseCmd , ws: WSConnMgr):
        """Process an external event."""
        logger.debug(f"Trigger {event.cmd} Current State: {self.state}")
        await self.trigger(event.cmd, event, ws)

    def get_team_idx_by_team(self, team_name: str) -> Optional[int]:
        for i in range(2):
            if self.teams[i].name == team_name:
                return i
        return None

    def get_team_for_ws(self, ws: WSConnMgr) -> Optional[TeamType]:
        for team in self.teams:
            if ws in team.players:
                return team
        return None

    async def reset_picks_and_bans(self):
        self.model.reset_picks_bans()
        await self._broadcast(MapPicksResp(map_pool=self.model.get_picker_state()))

    async def process_set_team_name(self, event: SetTeamNameCmd, ws):
        self.teams[event.team_id - 1].name = event.name
        i = 0
        for team in self.teams:
            await self._broadcast(TeamRosterResp(team_idx=i,team_name=team.name, players=[PlayerObj(isCaptain=True, id=x.client_id,  name=x.name) for x in team.players]))
            i += 1

    async def process_chat_cmd(self, event: AllChatCmd | TeamChatCmd, ws: WSConnMgr):
        if event.cmd == CmdType.chat:
            await self._broadcast(ChatCmdResp(message=event.message, player=ws.name))
        elif event.cmd == CmdType.team_chat:
            # Do some validation here that the connection from ws is actually on
            # the right team?
            logger.debug(f"Team Chat CMD from{ws.client_id} ")
            team = self.get_team_for_ws(ws)

            if team:
                await self._team_broadcast(team, TeamChatCmdResp(team=team.name, message=event.message, player=ws.name))
            else:
                logger.error(f"Inavlid Team Chat CMD from{ws.client_id}. Could not find team for this client")
                # TODO - raise an error!

    def finalize_map_picker(self, event, ws):
        """Clean up the map picker process."""
        print("Map Picker process completed.")

    async def add_conn(self, mgr: WSConnMgr):
        logger.debug(f"Adding new connection {mgr}")
        self.active_connections.append(mgr)
        await mgr.ws.send_json(MapPicksResp(map_pool=self.model.get_picker_state()).model_dump())
        i = 0
        for team in self.teams:
            await mgr.ws.send_json(TeamRosterResp(team_idx=i,team_name=team.name, players=[PlayerObj(isCaptain=True, id=x.client_id,  name=x.name) for x in team.players]).model_dump())
            i += 1

    async def remove_conn(self, mgr: WSConnMgr):
        self.active_connections.remove(mgr)

    async def _disconnect(self, websocket: WSConnMgr):
        self.active_connections.remove(websocket)
        for team in self.teams:
            if websocket in team.players:
                team.remove(websocket)
                await websocket.disconnect()

    # TODO  - Figure out how to get a player name from the WSConnMgr? Perhaps part of the client identification?
    # Ideally - we'd just pull the player right out of the auth-token on the WebSocket?
    # But that does make running with a test client a little tricky.
    async def _broadcast(self, cmd: BaseResp):
        for connection in self.active_connections:
            logger.debug(f"Active conns: {self.active_connections}")
            logger.debug(f"Sending {cmd} to {connection.client_id}")
            await connection.ws.send_json(cmd.model_dump())

    async def _team_broadcast(self, team: TeamType, cmd: BaseResp):
        for connection in team.players:
            logger.debug(f"Sending response to {connection.client_id}")
            await connection.ws.send_json(cmd.model_dump())

    async def _send(self, ws: WSConnMgr, cmd: BaseResp):
        await ws.ws.send_json(cmd.model_dump())

    async def process_join_team(self, event: JoinTeamCmd, ws: WSConnMgr ):
        existing_team = self.get_team_for_ws(ws)
        if existing_team:
            logger.error("Bad request - player already on a team")
            return
        team_idx = self.get_team_idx_by_team(event.name)
        if team_idx != None:
            logger.debug(f"client[{ws.client_id}] joining Team[{event.name}]")
            self.teams[team_idx].players.append(ws)
            await self._broadcast(TeamRosterResp(team_idx=team_idx, team_name=event.name, players=[PlayerObj(isCaptain=True, id=x.client_id,  name=x.name) for x in self.teams[team_idx].players]))
        else:
            logger.debug(f"Couldn't find team with name '{event.name}' in team list {self.teams}")

    async def process_switch_teams(self, event: SwitchTeamCmd, ws: WSConnMgr):
        team = self.get_team_for_ws(ws)
        if not team:
            logger.error(f"Player not on a team, can't switch!")
            return
        team.players.remove(ws)

        team_idx = self.get_team_idx_by_team(team.name)
        await self._broadcast(TeamRosterResp(team_idx=team_idx, team_name=team.name, players=[PlayerObj(isCaptain=True, id=x.client_id,  name=x.name) for x in team.players]))
        new_team_idx = int(not team_idx)
        new_team = self.teams[new_team_idx]
        new_team.players.append(ws)
        await self._broadcast(TeamRosterResp(team_idx=new_team_idx, team_name=new_team.name, players=[PlayerObj(isCaptain=True, id=x.client_id,  name=x.name) for x in new_team.players]))

    def _kick_player(self, websocket: WebSocket):
        self._disconnect(websocket)
