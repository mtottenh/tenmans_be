from typing import List, Literal, Optional, Union
from fastapi import WebSocket
from typing_extensions import Annotated
from pydantic import BaseModel, Field, TypeAdapter
from enum import StrEnum

class Side(StrEnum):
    CT="Counter Terrorists"
    T="Terrorists"
    KN="Knife for Sides"

class MapState(StrEnum):
    NONE = "none"
    TEAM_1_BANNED = "team1_ban"
    TEAM_2_BANNED = "team2_ban"
    TEAM_1_PICK = "team1_pick"
    TEAM_2_PICK = "team2_pick"

class Map(BaseModel):
    name: str
    state: MapState = MapState.NONE
    oppo_side: Optional[Side] = None
    # TODO - add validation that if state == *_pick then 'side' must == CT/T
    # If we changed it to a regular integer Enum then  we could just use int(not Side) to get the opposing side?

class CmdType(StrEnum):
    chat = "chat"
    team_chat = "team_chat"
    switch_teams = "switch_teams"
    leave = "leave"
    join_team = "join_team"
    kick_player = "kick_player"
    set_team_name = "set_team_name"
    start_map_picker = "start_map_picker"
    ban_map = "ban_map"
    pick_map = "pick_map"
    pick_side = "pick_side"
    identify_client = "identify_client"

class RespType(StrEnum):
    ack = "ack"
    chat = "chat"
    team_chat = "team_chat"
    team_roster = "team_roster"
    error = "error"
    map_picks = "map_picks"

class BaseResp(BaseModel):
    resp: RespType

class ErrResp(BaseResp):
    resp: Literal[RespType.error] = RespType.error

class InvalidAckResp(ErrResp):
    message: str = "Invalid seq no on last msg."
    got: int
    expected: int 

class ServerErrResp(ErrResp):
    message: str

class AckResp(BaseModel):
    resp: Literal[RespType.ack] = RespType.ack
    seq_no: int

class ChatCmdResp(BaseResp):
    resp: Literal[RespType.chat] = RespType.chat
    player: str
    message: str

class TeamChatCmdResp(BaseResp):
    resp: Literal[RespType.team_chat] = RespType.team_chat
    player: str
    team: str
    message: str

class TeamRosterResp(BaseResp):
    resp: Literal[RespType.team_roster] = RespType.team_roster
    team: str
    players: List[str]

# Represents the state of the picker
class MapPicksResp(BaseResp):
    resp: Literal[RespType.map_picks] = RespType.map_picks
    map_pool: List[Map]

class BaseCmd(BaseModel):
    cmd: CmdType
    seq_no: int

class IdentifyClientCmd(BaseCmd):
    cmd:  Literal[CmdType.identify_client] = CmdType.identify_client
    client_id: str

class AllChatCmd(BaseCmd):
    cmd:  Literal[CmdType.chat] = CmdType.chat
    message: str

class TeamChatCmd(BaseCmd):
    cmd:  Literal[CmdType.team_chat] = CmdType.team_chat
    message: str

class SwitchTeamCmd(BaseCmd):
    cmd:  Literal[CmdType.switch_teams] = CmdType.switch_teams

class LeaveCmd(BaseCmd):
    cmd:  Literal[CmdType.leave] = CmdType.leave

class JoinTeamCmd(BaseCmd):
    cmd:  Literal[CmdType.join_team] = CmdType.join_team
    name: str

class KickPlayerCmd(BaseCmd):
    cmd:  Literal[CmdType.kick_player] = CmdType.kick_player
    id: str

class SetTeamNameCmd(BaseCmd):
    cmd:  Literal[CmdType.set_team_name] = CmdType.set_team_name
    name: str
    team_id: str

class StartMapPickerCmd(BaseCmd):
    cmd:  Literal[CmdType.start_map_picker] = CmdType.start_map_picker

class BanMapCmd(BaseCmd):
    cmd:  Literal[CmdType.ban_map] = CmdType.ban_map
    map_name: str

class PickMapCmd(BaseCmd):
    cmd:  Literal[CmdType.pick_map] = CmdType.pick_map
    map_name: str


class PickSideCmd(BaseCmd):
    cmd:  Literal[CmdType.pick_side] = CmdType.pick_side 
    side: Side

class ConnectionManagerMode(StrEnum):
    BO1 = 'best of one'
    BO3 = 'best of three'

WSSCommand = TypeAdapter(Annotated[Union[AllChatCmd, TeamChatCmd, SwitchTeamCmd, LeaveCmd, JoinTeamCmd, KickPlayerCmd, SetTeamNameCmd, StartMapPickerCmd, BanMapCmd, PickMapCmd,  IdentifyClientCmd], Field(discriminator='cmd')])
