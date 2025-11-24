"""
JubileeManager - Centralized management of Jubilee machine and related components.

This module provides the JubileeManager class for coordinating complex tasks
that require interacting with the instantiated Jubilee machine as well as other
components like trickler or toolhead to perform complex tasks like weighing containers.

The JubileeManager uses a MotionPlatformStateMachine to validate and execute all
movements, ensuring that operations cannot bypass safety checks.
"""

from typing import Optional, List
from pathlib import Path

# Import Jubilee components
from science_jubilee.Machine import Machine
from Trickler import Trickler
from Scale import Scale
from PistonDispenser import PistonDispenser
from Manipulator import Manipulator, ToolStateError
from MotionPlatformStateMachine import MotionPlatformStateMachine
from ConfigLoader import config

class JubileeManager:
    """
    Manages the Jubilee machine and related components.
    
    All movements are validated through the MotionPlatformStateMachine, which is owned
    by this manager and cannot be bypassed.
    """
    
    # TODO: make dispensers configurable from UI
    def __init__(self, num_piston_dispensers: int = 0, num_pistons_per_dispenser: int = 0):
        self.scale: Optional[Scale] = None
        self.trickler: Optional[Trickler] = None
        self.manipulator: Optional[Manipulator] = None
        self.state_machine: Optional[MotionPlatformStateMachine] = None
        self.connected = False
        self._num_piston_dispensers = num_piston_dispensers
        self._num_pistons_per_dispenser = num_pistons_per_dispenser
    
    @property
    def machine_read_only(self) -> Optional[Machine]:
        """
        Access to machine through state machine.
        This should ONLY be used for actions that do not change the Jubilee's state,
        even though it is possible to do so (IT IS UNSAFE).
        """
        if self.state_machine:
            return self.state_machine.machine
        return None
    
    @property
    def deck(self) -> Optional[Deck]:
        """Access to deck through state machine."""
        if self.state_machine:
            return self.state_machine.context.deck
        return None
    
    @property
    def piston_dispensers(self) -> List[PistonDispenser]:
        """Access to piston dispensers through state machine."""
        if self.state_machine:
            return self.state_machine.context.piston_dispensers
        return []
        
    def connect(
        self,
        machine_address: str = None,
        scale_port: str = "/dev/ttyUSB0",
        state_machine_config: str = "./jubilee_api_config/motion_platform_positions.json"
    ):
        """
        Connect to Jubilee machine, scale, and initialize the state machine.
        
        Args:
            machine_address: IP address of the Jubilee machine (uses config if None)
            scale_port: Serial port for the scale connection
            state_machine_config: Path to state machine configuration file
        """
        try:
            # Use config IP if no address provided
            if machine_address is None:
                machine_address = config.get_duet_ip()
            
            # Connect to machine
            real_machine = Machine(address=machine_address)
            real_machine.connect()
            
            # Initialize the state machine with the real machine
            # The state machine owns the machine and controls all access to it
            config_path = Path(state_machine_config)
            if not config_path.exists():
                raise FileNotFoundError(f"State machine config not found: {state_machine_config}")
            
            self.state_machine = MotionPlatformStateMachine.from_config_file(
                config_path,
                real_machine
            )
            
            # Initialize deck and dispensers in state machine
            self.state_machine.initialize_deck()
            self.state_machine.initialize_dispensers(
                num_piston_dispensers=self._num_piston_dispensers,
                num_pistons_per_dispenser=self._num_pistons_per_dispenser
            )
            
            # Connect to scale
            self.scale = Scale(port=scale_port)
            self.scale.connect()

            # Create manipulator with state machine reference
            self.manipulator = Manipulator(
                index=0,
                name="manipulator",
                state_machine=self.state_machine,
                config="manipulator_config"
            )

            # Initialize trickler (assuming it's already loaded)
            # This would need to be configured based on your setup
            # self.trickler = Trickler(index=0, name="trickler", config="trickler_config", scale=self.scale)
            
            # Ensure state machine context is set correctly for homing
            self.state_machine.update_context(
                active_tool_id=None,
                payload_state="empty"
            )
            
            # Home all axes (X, Y, Z, U) through state machine
            # This requires no tool picked up and no mold
            # Returns to global_ready position
            result = self.state_machine.validated_home_all()
            if not result.valid:
                raise RuntimeError(f"Failed to home all axes: {result.reason}")
            
            # Load the manipulator tool (this registers it but doesn't pick it up)
            self.machine_read_only.load(self.manipulator)
            
            # Pick up the tool through state machine
            # This validates we're at a valid position, picks up the tool, and moves to global_ready
            result = self.state_machine.validated_pickup_tool(self.manipulator)
            if not result.valid:
                raise RuntimeError(f"Failed to pick up tool: {result.reason}")
            
            # Home the manipulator axis (V) through state machine
            # This requires no mold picked up
            result = self.state_machine.validated_home_manipulator(manipulator_axis='V')
            if not result.valid:
                raise RuntimeError(f"Failed to home manipulator: {result.reason}")
            
            self.connected = True
            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from all components"""
        if self.machine_read_only:
            self.machine_read_only.disconnect()
        if self.scale:
            self.scale.disconnect()
        self.connected = False
    
    def get_current_weight(self) -> float:
        """Get current weight from scale"""
        if self.scale and self.scale.is_connected:
            try:
                return self.scale.get_weight()
            except:
                return 0.0
        return 0.0
    
    def dispense_to_well(self, well_id: str, target_weight: float) -> bool:
        """Dispense powder to a specific well"""
        if not self.connected or not self.trickler:
            return False
        
        try:

            if not self.manipulator:
                raise ToolStateError("Manipulator is not connected or provided.")
            
            if not self.scale or not self.scale.is_connected:
                raise ToolStateError("Scale is not connected or provided.")
            
            if not self.state_machine:
                raise RuntimeError("State machine not configured")
            
            well = self.state_machine.get_well_from_deck(well_id)
            if not well:
                raise ToolStateError(f"Well {well_id} not found in deck.")
            if not well.valid:
                raise ToolStateError("Well is not valid.")
            if well.has_top_piston:
                raise ToolStateError("Well already has a top piston. Cannot dispense.")
            
            # TODO: Move this logic to state machine / movement executor
            self._move_to_well(well_id)
            self.manipulator.pick_mold(well)
            self._move_to_scale()
            self.manipulator.place_well_on_scale(self.scale)
            self._dispense_powder(target_weight)
            self.manipulator.pick_well_from_scale(self.scale)
            dispenser_index = -1
            for dispenser in self.piston_dispensers:
                if dispenser.num_pistons > 0:
                    dispenser_index = dispenser.index
                    break
            if dispenser_index == -1:
                raise ToolStateError("No dispenser with pistons found.")
            self.get_piston_from_dispenser(dispenser_index, well_id)
            self._move_to_well(well_id)
            self.manipulator.place_well()
            return True
        except Exception as e:
            print(f"Dispensing error: {e}")
            return False

    def get_piston_from_dispenser(self, dispenser_index: int, well_id: str):
        """
        Get the top piston from a specific dispenser.
        
        Validates and executes through MotionPlatformStateMachine.
        Requires being at the dispenser ready position for that dispenser.
        """
        if not self.connected or not self.piston_dispensers:
            return False
        
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        if self.manipulator.current_well is None:
            raise ToolStateError("No mold to place piston into.")
        
        try:
            piston_dispenser = self.piston_dispensers[dispenser_index]
            
            # Move to dispenser ready position if not already there
            target_position = f"dispenser_ready_{dispenser_index}"
            if self.state_machine.context.position_id != target_position:
                # Move to dispenser position through state machine
                result = self.state_machine.validated_move_to_dispenser(
                    dispenser_index=dispenser_index,
                    dispenser_x=piston_dispenser.x,
                    dispenser_y=piston_dispenser.y
                )
                if not result.valid:
                    raise RuntimeError(f"Failed to move to dispenser position: {result.reason}")
            
            # Retrieve piston through state machine
            result = self.state_machine.validated_retrieve_piston(
                piston_dispenser=piston_dispenser,
                manipulator_config=self.manipulator._get_config_dict()
            )
            
            if not result.valid:
                raise RuntimeError(f"Failed to retrieve piston: {result.reason}")
            
            
            return True
        except Exception as e:
            print(f"Getting piston from dispenser error: {e}")
            return False

    def _move_to_well(self, well_id: str):
        """
        Move to a specific well.
        
        Validates and executes through MotionPlatformStateMachine.
        Uses the well's ready_pos field to determine the state machine position.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        well = self.state_machine.get_well_from_deck(well_id)
        
        result = self.state_machine.validated_move_to_well(
            well_id=well_id,
            scale=self.scale,
            well=well  # Pass well object so validated_move_to_well can use ready_pos
        )
        
        if not result.valid:
            raise RuntimeError(f"Move to well failed: {result.reason}")
        
        return True

    def _move_to_scale(self):
        """
        Move to the scale.
        
        Validates and executes through MotionPlatformStateMachine.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        if not self.scale:
            return False
        
        result = self.state_machine.validated_move_to_scale(
            scale=self.scale
        )
        
        if not result.valid:
            raise RuntimeError(f"Move to scale failed: {result.reason}")
        
        return True

    def _dispense_powder(self, target_weight: float):
        """
        Dispense powder to the scale.
        
        Validates and executes through MotionPlatformStateMachine.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        if not self.scale:
            return False
        
        result = self.state_machine.validated_dispense_powder(
            target_weight=target_weight
        )
        
        if not result.valid:
            raise RuntimeError(f"Dispense powder failed: {result.reason}")
        
        return True
