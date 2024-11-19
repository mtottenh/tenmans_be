from typing import Literal, Union
from fastapi import WebSocket
from typing_extensions import Annotated
from pydantic import BaseModel, Field, TypeAdapter
from enum import StrEnum

class Side(StrEnum):
    CT="Counter Terrorists"
    T="Terrorists"

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
    error = "error"

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
