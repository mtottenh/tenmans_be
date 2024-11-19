from sys import stderr
import pytest
from src.fixtures.MapPicker.state_machine import MapPickerModel, WebSocketStateMachine
from src.fixtures.MapPicker.commands import *
import logging
logging.basicConfig(encoding='utf-8', level=logging.DEBUG)

@pytest.fixture
def setup_machine():
    """Fixture to set up the WebSocketStateMachine for tests."""
    map_pool = ["map1", "map2", "map3", "map4", "map5"]
    team_1 = "Team A"
    team_2 = "Team B"
    machine = WebSocketStateMachine(MapPickerModel(map_pool, team_1, team_2), ConnectionManagerMode.BO3)
    return machine

def test_initial_state(setup_machine):
    """Test that the initial state is 'ready'."""
    machine = setup_machine
    assert machine.state == "ready"

def test_valid_transition_to_map_picker(setup_machine):
    """Test a valid transition to start the map picker."""
    machine = setup_machine
    machine.process_event(StartMapPickerCmd())
    assert machine.state.startswith("pick_phase")
    assert machine.machine is not None

def test_invalid_transition_from_ready(setup_machine):
    """Test invalid transitions from the 'ready' state."""
    machine = setup_machine
    with pytest.raises(Exception):  # Replace with specific exception if possible
        machine.process_event(PickMapCmd(map_name="map1"))
    assert machine.state == "ready"

def test_process_general_command_in_ready(setup_machine):
    """Test that general commands are processed in the 'ready' state."""
    machine = setup_machine
    machine.process_event(AllChatCmd(message="Hello, world!"))
    # Ensure no state change and the command was processed
    assert machine.state == "ready"

def test_process_general_command_in_map_picker(setup_machine):
    """Test that general commands are processed in the 'map_picker_active' state."""
    machine = setup_machine
    machine.process_event(StartMapPickerCmd())
    machine.process_event(AllChatCmd(message="Good luck!"))
    assert machine.state.startswith("pick_phase")

def test_map_picker_valid_transitions(setup_machine):
    """Test valid transitions in the map picker hierarchical state."""
    machine = setup_machine
    cmd = StartMapPickerCmd()
    machine.process_event(cmd)

    cmd = PickMapCmd(map_name="map1")
    machine.process_event(cmd)

    cmd = PickSideCmd(side=Side.T)
    machine.process_event(cmd)

    assert "map1" in [ x[0] for x in machine.model.picked_maps ]
    assert machine.model.current_team == "Team B"  # Assuming alternation after a pick

def test_map_picker_invalid_transitions(setup_machine):
    """Test invalid transitions in the map picker hierarchical state."""
    machine = setup_machine
    machine.process_event(StartMapPickerCmd())
    map_picker = machine.machine
    with pytest.raises(Exception):  # Replace with specific exception
        map_picker.process_event(BanMapCmd("invalid_map"))
    assert "invalid_map" not in machine.model.map_pool

def test_map_picker_full(setup_machine):

    orignal_pool = setup_machine.model.map_pool
    machine = setup_machine
    machine.process_event(StartMapPickerCmd())
    print(f"{machine.state}")
    machine.process_event(PickMapCmd(map_name='map1'))
    print(f"{machine.state}")
    machine.process_event(PickSideCmd(side=Side.T))
    print(f"{machine.state}")
    machine.process_event(PickMapCmd(map_name='map2'))
    print(f"{machine.state}")
    machine.process_event(PickSideCmd(side=Side.CT))
    print(f"{machine.state}")
    machine.process_event(BanMapCmd(map_name='map3'))
    print(f"{machine.state}")
    machine.process_event(BanMapCmd(map_name='map4'))
    print(f"{machine.state}")
    # machine.process_event(BanMapCmd(map_name='map5'))
    print(f"{machine.model}")
    assert [ 'map1', 'map2', 'map5'] == [ x[0] for x in machine.model.picked_maps ]
    assert machine.state == "done"

