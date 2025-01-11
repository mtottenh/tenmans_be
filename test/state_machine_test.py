from sys import stderr
import pytest
from src.fixtures.MapPicker.state_machine import MapPickerModel, WebSocketStateMachine
from src.fixtures.MapPicker.commands import *
import logging
logging.basicConfig(encoding='utf-8', level=logging.DEBUG)
pytest_plugins = ('pytest_asyncio',)

@pytest.fixture
def setup_machine():
    """Fixture to set up the WebSocketStateMachine for tests."""
    map_pool = ["map1", "map2", "map3", "map4", "map5"]
    map_pool = [Map(name=m, id="", img="") for m in map_pool]
    team_1 = "Team A"
    team_2 = "Team B"
    machine = WebSocketStateMachine(MapPickerModel(map_pool, team_1, team_2), ConnectionManagerMode.BO3)
    return machine


def test_initial_state(setup_machine):
    """Test that the initial state is 'ready'."""
    machine = setup_machine
    assert machine.state == "ready"

@pytest.mark.asyncio
async def test_valid_transition_to_map_picker(setup_machine):
    """Test a valid transition to start the map picker."""
    machine = setup_machine
    await machine.process_event(StartMapPickerCmd(seq_no=1), None)
    assert machine.state.startswith("pick_phase")
    assert machine.machine is not None

@pytest.mark.asyncio
async def test_invalid_transition_from_ready(setup_machine):
    """Test invalid transitions from the 'ready' state."""
    machine = setup_machine
    with pytest.raises(Exception):  # Replace with specific exception if possible
        await machine.process_event(PickMapCmd(map_name="map1", seq_no=1), None)
    assert machine.state == "ready"

@pytest.mark.asyncio
async def test_process_general_command_in_ready(setup_machine):
    """Test that general commands are processed in the 'ready' state."""
    machine = setup_machine
    await machine.process_event(AllChatCmd(message="Hello, world!", seq_no=1), None)
    # Ensure no state change and the command was processed
    assert machine.state == "ready"

@pytest.mark.asyncio
async def test_process_general_command_in_map_picker(setup_machine):
    """Test that general commands are processed in the 'map_picker_active' state."""
    machine = setup_machine
    seq_no=1
    await machine.process_event(StartMapPickerCmd(seq_no=seq_no), None)
    seq_no+=1
    await machine.process_event(AllChatCmd(message="Good luck!", seq_no=seq_no), None)
    assert machine.state.startswith("pick_phase")

@pytest.mark.asyncio
async def test_map_picker_valid_transitions(setup_machine):
    """Test valid transitions in the map picker hierarchical state."""
    machine = setup_machine
    seq_no=1
    cmd = StartMapPickerCmd(seq_no=seq_no)
    await machine.process_event(cmd,None)
    seq_no+=1

    cmd = Team1PickMapCmd(map_name="map1", seq_no=seq_no)
    await machine.process_event(cmd)
    seq_no+=1
    cmd = Team2PickSideCmd(side=Side.T, seq_no=seq_no)
    await machine.process_event(cmd, None)

    assert "map1" in [ x[0] for x in machine.model.picked_maps ]
    assert machine.model.current_team == "Team B"  # Assuming alternation after a pick

@pytest.mark.asyncio
async def test_map_picker_invalid_transitions(setup_machine):
    """Test invalid transitions in the map picker hierarchical state."""
    machine = setup_machine
    await machine.process_event(StartMapPickerCmd(seq_no=1))
    map_picker = machine.machine
    with pytest.raises(Exception):  # Replace with specific exception
        await map_picker.process_event(Team1BanMapCmd("invalid_map",seq_no=2))
    assert "invalid_map" not in machine.model.map_pool

@pytest.mark.asyncio
async def test_map_picker_full(setup_machine):

    orignal_pool = setup_machine.model.map_pool
    machine = setup_machine
    await machine.process_event(StartMapPickerCmd(seq_no=1))
    print(f"{machine.state}")
    await machine.process_event(PickMapCmd(map_name='map1'))
    print(f"{machine.state}")
    await machine.process_event(PickSideCmd(side=Side.T))
    print(f"{machine.state}")
    await machine.process_event(PickMapCmd(map_name='map2'))
    print(f"{machine.state}")
    await machine.process_event(PickSideCmd(side=Side.CT))
    print(f"{machine.state}")
    await machine.process_event(BanMapCmd(map_name='map3'))
    print(f"{machine.state}")
    await machine.process_event(BanMapCmd(map_name='map4'))
    print(f"{machine.state}")
    # machine.process_event(BanMapCmd(map_name='map5'))
    print(f"{machine.model}")
    assert [ 'map1', 'map2', 'map5'] == [ x[0] for x in machine.model.picked_maps ]
    assert machine.state == "done"
