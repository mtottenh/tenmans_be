
from copy import deepcopy
from typing import Dict, List, Optional
from fastapi import WebSocket
from transitions import Machine, State
from transitions.extensions import HierarchicalAsyncMachine, AsyncMachine
from .commands import *
from transitions.extensions.nesting import NestedState
NestedState.separator = '↦'
import logging
logging.basicConfig(encoding='utf-8', level=logging.DEBUG)

class MapPickerModel():
    def __init__(self, map_pool: List[str], team_1, team_2):
        self.map_pool = map_pool
        self.team_1 = team_1
        self.team_2 = team_2
        self.current_team = self.team_1
        self.picked_maps = []
        self.finalized = False

    def __repr__(self):
        return f"MapPickerModel(map_pool={self.map_pool}, team_1={self.team_1}, team_2={self.team_2}, picked_maps={self.picked_maps})"

BO1_CONF={
    "name" : "banning_phase",
    "states" : [  "waiting_for_team_1", 
                  "waiting_for_team_2",  
                  "final_map"
            ],
    "transitions" : [
        {"trigger":"ban_map", "source": 'waiting_for_team_1', 'dest':'waiting_for_team_2', 'conditions': ['is_valid_map', 'has_maps_remaining'], 'after' : 'process_ban' },
        {"trigger":"ban_map", "source": 'waiting_for_team_2', 'dest':'waiting_for_team_1', 'conditions': ['is_valid_map', 'has_maps_remaining'], 'after' : 'process_ban' },
        {"trigger":"determine_final_map", 'source': ['waiting_for_team_1', 'waiting_for_team_2'], 'dest':'final_map', 'conditions': ['only_one_map_remaining'], 'after' : 'finalize_map' },

    ],
    "initial": "waiting_for_team_1"
}
    # Initialize the state machine
    # return HierarchicalMachine(model=model, states=states, transitions=transitions, initial="waiting_for_team_1")
    

        # Define hierarchical states
BO3_CONF={
    "name" : "pick_phase",
    "states" : [
            "team_1_pick",
            "team_2_pick_side",
            "team_2_pick",
            "team_1_pick_side",
            { "name" : "final_maps", "on_enter" : 'finalize_maps' },
            deepcopy(BO1_CONF),
        ],
    "transitions" : [
        {"trigger": "pick_map", "source": "team_1_pick", "dest" : "team_2_pick_side", "conditions" : ["is_valid_map"], "after" : "process_pick"},
        {"trigger": "pick_map", "source": "team_2_pick", "dest" : "team_1_pick_side", "conditions" : ["is_valid_map"], "after" : "process_pick"},
        {"trigger": "pick_side", "source": "team_2_pick_side", "dest" : "team_2_pick", "after" : "record_side"},
        {"trigger": "pick_side", "source": "team_1_pick_side", "dest" : "banning_phase", "after" : "record_side"},

    ],
    "initial" : "team_1_pick"
}
BO3_CONF['states'][-1]['remap'] = { 'final_map' : 'final_maps'}

WS_CONF={

}
class BestOfOneStateMachine:
    """State machine for banning maps."""
    def __init__(self, model: MapPickerModel):
        self.model = model

    def is_valid_map(self, event: BanMapCmd):
        """Check if the map is valid."""
        print(f"Checking if {event.map_name} in {self.model.map_pool}")
        return event.map_name in self.model.map_pool

    def has_maps_remaining(self, event: BanMapCmd):
        """Check if more than one map remains."""
        return len(self.model.map_pool) > 1

    def only_one_map_remaining(self, event: BanMapCmd):
        """Check if only one map remains."""
        return len(self.model.map_pool) == 1

    def finalize_map(self, event):
        print("Finalizing decider map")
        self.model.finalized=True
        self.model.picked_maps.append((self.model.map_pool[0], None))

    async def process_ban(self, event: BanMapCmd):
        """Handle the banning of a map."""
        self.model.map_pool.remove(event.map_name)
        print(f"{self.model.current_team} banned {event.map_name}. Remaining maps: {self.model.map_pool}")
        self.model.current_team = self.model.team_2 if self.model.current_team == self.model.team_1 else self.model.team_1
        if self.only_one_map_remaining(event):
            print(f"Triggering determine_final_map")
            await self.trigger('determine_final_map', event)


class BestOfThreeStateMachine(BestOfOneStateMachine):
    """State machine for a 'Best of Three' map selection process with side selection."""
    def __init__(self, model: MapPickerModel):
        self.model = model

    def process_pick(self, event):
        """Handle the picking of a map."""
        self.model.map_pool.remove(event.map_name)
        self.model.picked_maps.append((event.map_name, None))  # Side to be chosen later
        print(f"Map {event.map_name} has been picked. Remaining maps: {self.model.map_pool}")

    def record_side(self, event):
        """Record the side chosen for the last picked map."""
        map_name, _ = self.model.picked_maps[-1]
        self.model.picked_maps[-1] = (map_name, event.side)
        print(f"Side '{event.side}' has been chosen for map {map_name}.")

    def finalize_maps(self, event = None):
        """Finalize the maps for the Best of Three series."""
        print("Final Best of Three Maps:")
        for i, (map_name, side) in enumerate(self.model.picked_maps):
            print(f"Game {i + 1}: Map - {map_name}, Side - {side}")

class WSConnInvalidAckException(Exception):
    pass

class WSConnMgr:
    def __init__(self):
        states = [ 'listen', 'accepted', 'established', 'close' ]
        transtions=[ {'trigger' : 'accept', 'source' : 'listen', 'dest' : 'accepted', 'after' : 'handle_accept'},
                     {'trigger' : 'identify_client', 'source' : 'accepted', 'dest': 'established', 'after' : 'handle_identify_client' },
                     {'trigger' : 'new_msg', 'source' : ['accepted', 'established'], 'dest' : None, 'after' : 'handle_msg' },
                     {'trigger' : 'connection_error', 'source' : ['accepted', 'established'], 'dest' : 'close', 'after' :'handle_connection_error'}
                    ]
        self.machine = AsyncMachine(model=self, states=states, transitions=transtions, initial='listen')
        self.ws: Optional[WebSocket] = None
        self.last_seq_no: int = 0
        self.client_id: Optional[str] = None

    async def handle_accept(self, ws: WebSocket):
        await ws.accept()
        self.ws = ws

    async def handle_identify_client(self, cmd: IdentifyClientCmd):
        self.last_seq_no = cmd.seq_no
        self.client_id = cmd.client_id
    
    async def handle_connection_error(self, errmsg):
        if self.ws:
            await self.ws.send_json(ServerErrResp(message=f"{errmsg}").model_dump())
            await self.ws.close()
            self.ws = None

    async def ack_last_cmd(self):
        await self.ws.send_json(AckResp(seq_no=self.last_seq_no).model_dump())

    async def handle_msg(self, cmd: BaseCmd):
        if cmd.cmd == CmdType.identify_client:
            await self.identify_client(cmd)
        elif cmd.seq_no != (self.last_seq_no + 1):
            await self.ws.send_json(InvalidAckResp(got=cmd.seq_no, expected=self.last_seq_no + 1).model_dump())
            raise  WSConnInvalidAckException("Invalid Ack!")
        else:
            self.last_seq_no = cmd.seq_no

    async def start(self):
        try:
            async for data in self.ws.iter_json():
                cmd = WSSCommand.validate_python(data)
                await self.new_msg(cmd)
                yield cmd
                await self.ack_last_cmd()
        except Exception as e:
            await self.handle_connection_error(f"{e}")
            raise e

class WebSocketStateMachine(BestOfThreeStateMachine):
    """Parent state machine with hierarchical map picker integration."""
    def __init__(self, model: MapPickerModel, picker_type: ConnectionManagerMode):
        self.model = model
        self.map_picker_conf = None
        self.active_connections: List[WSConnMgr] = []
        self.teams: Dict[str, List[WSConnMgr]] = {"team_1": [], "team2": []}

        if picker_type == ConnectionManagerMode.BO1:
            self.map_picker = BO1_CONF
        elif picker_type == ConnectionManagerMode.BO3:
            self.map_picker = BO3_CONF
        else:
            raise ValueError(f"Invalid ConnectionManagerMode {picker_type}")
        self.map_picker['remap'] = { "final_maps" : "done" }
        # Define states
        states = [
            "ready",
            self.map_picker,
            "done"
        ]
        
        # Initialize the state machine
        self.machine = HierarchicalAsyncMachine(model=self, states=states, initial="ready")

        # Add transitions
        self.machine.add_transition(
            trigger="start_map_picker",
            source="ready",
            dest="pick_phase",
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
            # CmdType.switch_teams,
            # CmdType.leave,
            # CmdType.join_team,
            # CmdType.set_team_name,
            # CmdType.kick_player,
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
            after=self.reset_model
        )
        self.machine.add_transition(
            trigger=CmdType.set_team_name,
            source='ready',
            dest=None,
            after=self.process_set_team_name
        )
        self.machine.add_transition(
            trigger=CmdType.join_team,
            source='ready',
            dest=None,
            after=self.join_team
        )

    async def process_event(self, event: BaseCmd , ws: WSConnMgr):
        """Process an external event."""
        await self.trigger(event.cmd, event, ws)

    def lookup_team_name(self, ws: WSConnMgr) -> Optional[str]:
        for team in self.teams.keys():
            if ws in self.teams[team]:
                return team
        return None
    
    def reset_model(self):
        pass

    async def process_set_team_name(self, event: SetTeamNameCmd, ws):
        pass

    async def process_chat_cmd(self, event: AllChatCmd | TeamChatCmd, ws):
        if event.cmd == CmdType.chat:
            await self._broadcast(event.message)
        elif event.cmd == CmdType.team_chat:
            # Do some validation here that the connection from ws is actually on
            # the right team?
            team = self.lookup_team_name(ws)
            if team:
                await self._team_broadcast(team, event.message)
            else:
                # TODO - raise an error!
                pass


    def finalize_map_picker(self, event, ws):
        """Clean up the map picker process."""
        print("Map Picker process completed.")

    async def add_conn(self, mgr: WSConnMgr):
        self.active_connections.append(mgr)

    def _disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        for team in self.teams.values():
            if websocket in team:
                team.remove(websocket)
    # TODO  - Figure out how to get a player name from the WSConnMgr? Perhaps part of the client identification?
    # Ideally - we'd just pull the player right out of the auth-token on the WebSocket?
    # But that does make running with a test client a little tricky.
    async def _broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.ws.send_json(ChatCmdResp(message=message, player='').model_dump())

    async def _team_broadcast(self, team: str, message: str):
        if team in self.teams:
            for connection in self.teams[team]:
                await connection.ws.send_json(TeamChatCmdResp(team=team, message=message, player=''))

    async def join_team(self, event: JoinTeamCmd, websocket: WSConnMgr ):
        if event.name in self.teams:
            self.teams[event.name].append(websocket)
            

    # def switch_teams(self, event: SwitchTeamCmd, websocket: WebSocket):
    #     for team in self.teams.values():
    #         if websocket in team:
    #             team.remove(websocket)
    #     self.join_team(JoinTeamCmd(name=event.team))

    def _kick_player(self, websocket: WebSocket):
        self._disconnect(websocket)
