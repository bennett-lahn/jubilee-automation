from science_jubilee.labware.Labware import Labware, Location, Well
from science_jubilee.tools.Tool import (
    Tool,
    ToolConfigurationError,
    ToolStateError,
)
from trickler_labware import WeightWell
import PistonDispenser
import time
from typing import List, Optional, Dict, Any
import json
import os

# Fixed tamp, claw moves mold up into tamp
# Cap silo/hopper
# Claw moves vertically within toolhead
# Big and small port for trickler using rotary tube
# rotate tamper to remove powder
# no rotary toolhead / ignore for now ; fixed tamper
    # For now focus on figuring out how to detect stop using motor torque/current

class Manipulator(Tool):
    """
    Jubilee toolhead for mold handling and tamping operations.
    Tracks a WeightWell object representing the current mold being carried.
    
    State tracking:
    - current_well: WeightWell object representing the current mold (None if not carrying one)
    - The WeightWell object tracks has_top_piston, valid, weight, and other mold properties
    
    Operations:
    - Tamping: Only allowed when carrying a mold without a top piston
    - Top piston placement: Only allowed when carrying a mold without a top piston
    - Mold handling: Pick up and place WeightWell objects

    Tamping is primarily controlled using sensorless homing/stall detection, which is configured
    using the M915 command in config.g and homet.g, not this file. driver-stall.g is used to 
    control tamping after contact with the material.
    """

    # TODO: This is the default position of the tamper axis when moving around the platform
    # TODO: Move global variables to different header file or something
    # The tamper axis should be returned to this position after any functions that move the tamper complete
    TAMP_AXIS_TRAVEL_POS = 30 # mm
    SAFE_Z = 195 # mm

    def __init__(self, index, name, config=None):
        super().__init__(index, name)
        self.current_well = None  # WeightWell object representing the current mold
        self.config = config
        self.placed_well_on_scale = False # Do not do anything except pick up well from scale if True
        
        # Tamper-specific attributes
        self.tamper_axis = 'T'  # Default axis for tamper movement
        self.tamper_driver = 0  # Default driver number for tamper motor
        self.tamper_board_address = 0  # Default board address
        self.stall_detection_configured = False
        self.sensorless_homing_configured = False
        self.tamper_motor_specs = {
            'full_steps_per_rev': 200,  # 1.8 degree stepper
            'rated_current': 1.5,  # Amps
            'actual_current': 1.0,  # Amps (reduced for stall detection)
            'rated_holding_torque': 0.4,  # Nm
            'driver_type': 'TMC2209'  # Driver type for configuration
        }
        
        # Event handling
        self.tamper_position = 0.0  # Current tamper position in mm
        self.tamper_speed = 1000  # mm/min for tamper movement
        self.tamper_acceleration = 500  # mm/s² for tamper movement

        # Load configuration if provided
        if config:
            self._load_tamper_config(config)

    def _load_tamper_config(self, config: Dict[str, Any]):
        """Load tamper-specific configuration from config dict."""
        tamper_config = config.get('tamper', {})
        
        # Load motor specifications
        motor_specs = tamper_config.get('motor_specs', {})
        for key, value in motor_specs.items():
            if key in self.tamper_motor_specs:
                self.tamper_motor_specs[key] = value
        
        # Load movement parameters
        movement_config = tamper_config.get('movement', {})
        self.tamper_axis = movement_config.get('axis', self.tamper_axis)
        self.tamper_driver = movement_config.get('driver', self.tamper_driver)
        self.tamper_board_address = movement_config.get('board_address', self.tamper_board_address)
        self.tamper_speed = movement_config.get('speed', self.tamper_speed)
        self.tamper_acceleration = movement_config.get('acceleration', self.tamper_acceleration)

    def home_tamper(self, machine_connection=None):
        """
        Perform sensorless homing for the tamper axis.
        
        Args:
            machine_connection: Connection to the Jubilee machine for sending commands
        """
        if machine_connection:
            # Check if X, Y, and Z axes are homed before homing tamper
            # axes_homed: [X, Y, Z, U] (all booleans)
            axes_homed = getattr(machine_connection, 'axes_homed', [False, False, False, False])
            axis_names = ['X', 'Y', 'Z', 'U']
            not_homed = [axis_names[i] for i in range(4) if not axes_homed[i]]  # Only check X, Y, Z
            if not_homed:
                print(f"Axes not homed: {', '.join(not_homed)}")
                raise RuntimeError("X, Y, Z, and U axes must be homed before homing the tamper (T) axis.")
            # Perform homing for tamper axis
            machine_connection.send_command('M98 P"homet.g"')
            
            # Wait for homing to complete
            time.sleep(5.0)  # Adjust based on homing time
            
            # Reset position to 0 after homing
            self.tamper_position = 0.0
            print("Homing complete. Tamper position reset to 0.0mm")

    def tamp(self, target_depth: float = None, machine_connection=None):
        """
        Perform tamping action. Only allowed if carrying a mold without a cap.
        Enhanced version with stall detection.
        
        Args:
            target_depth: Target depth to tamp to (mm). If None, uses default depth.
            machine_connection: Connection to the Jubilee machine for sending commands
        """
        if self.current_well is None:
            raise ToolStateError("Must be carrying a mold to perform tamping.")
        
        if self.current_well.has_top_piston:
            raise ToolStateError("Cannot tamp mold that already has a top piston.")
        
        # Use default depth if not specified
        if target_depth is None:
            target_depth = self.tamper_position + 50.0  # Default 50mm tamp
        
        if not machine_connection:
            raise RuntimeError("Jubilee not connected for tamping operation.")

        print(f"Tamping mold: {self.current_well.name if hasattr(self.current_well, 'name') else 'unnamed'}")
        machine_connection.send_command('G91')  # Set relative mode
        for _ in range(target_depth // 5):
            machine_connection.send_command('G1 T-5 F600')  # Move tamper axis down 5mm at 600mm/min
        self.vibrate_tamper(machine_connection)
        for _ in range(target_depth // 5):
            machine_connection.send_command('G1 T5 F600')  # Move tamper axis up 5mm at 600mm/min
        machine_connection.send_command('G90')  # Set absolute mode

    def vibrate_tamper(self, machine_connection=None):
        # TODO: Update when Adafruit PWM I/O arrives
        pass

    def get_status(self) -> Dict[str, Any]:
        """
        Get current manipulator status and configuration.
        
        Returns:
            Dictionary containing manipulator status information
        """
        status = {
            'has_mold': self.current_well is not None,
            'tamper_position': self.tamper_position,
            'stall_detection_configured': self.stall_detection_configured,
            'sensorless_homing_configured': self.sensorless_homing_configured,
            'motor_specs': self.tamper_motor_specs.copy(),
            'movement_parameters': {
                'axis': self.tamper_axis,
                'driver': self.tamper_driver,
                'board_address': self.tamper_board_address,
                'speed': self.tamper_speed,
                'acceleration': self.tamper_acceleration
            }
        }
        
        if self.current_well is not None:
            status['current_well'] = {
                'name': getattr(self.current_well, 'name', 'unnamed'),
                'has_top_piston': self.current_well.has_top_piston,
                'valid': self.current_well.valid,
                'current_weight': self.current_well.current_weight,
                'target_weight': self.current_well.target_weight,
                'max_weight': self.current_well.max_weight
            }
        else:
            status['current_well'] = None
            
        return status

    def get_current_well(self) -> Optional[WeightWell]:
        """
        Get the current mold being carried.
        
        Returns:
            WeightWell object if carrying a mold, None otherwise
        """
        return self.current_well

    def is_carrying_well(self) -> bool:
        """
        Check if the manipulator is currently carrying a mold.
        
        Returns:
            True if carrying a mold, False otherwise
        """
        return self.current_well is not None

    # Assumes toolhead is directly above the chosen well at safe_z height with tamper axis in travel position
    def pick_from_well(self, mold: WeightWell):
        """Pick up mold from well. """
        if self.current_well is not None:
            raise ToolStateError("Already carrying a mold. Place current mold before picking up another.")
        if mold.has_top_piston:
            raise ToolStateError("Mold to be picked up already has a top piston.")
        if not mold.valid:
            raise ToolStateError("Cannot pick up an invalid mold.")
        if self.placed_well_on_scale:
            raise ToolStateError("Cannot pick up mold, mold currently on scale.")
        position = machine.get_position()
        if not (position["X"] == mold.x or position["Y"] == mold.y or position["Z"] == SAFE_Z):
            raise ToolStateError("Toolhead is not correctly positioned over mold. Cannot pickup")
        if not position["T"] == self.TAMPER_AXIS_TRAVEL_POS:
            raise ToolStateError("Tamper axis did not start in travel position")
        # TODO: Decide feedrates for movement
        print(f"Picking up mold: {mold.name if hasattr(mold, 'name') else 'unnamed'}")
        machine._set_absolute_positioning()
        # current x: 210 current y: 111.5
        machine.move(z=148 s=) # Move until tamper leadscrew almost grounded
        machine._set_relative_positioning()
        machine.move(y=-25.5, s=) # Move to the side of the mold
        machine._set_absolute_positioning()
        machine.gcode("G1 T50 FXXX") # Move mold holder down
        machine._set_relative_positioning()
        machine.move(y=25.5, s=) # Move back under mold
        machine._set_absolute_positioning()
        machine.gcode("G1 T30 FXXX") # Pick up mold and move into tamper travel position
        machine.safe_z_movement() # Move back to safe z
        # TODO: Verify accuracy of actual vs expected mold location
        self.current_well = mold

    def place_in_well(self) -> WeightWell:
        """Place down the current mold and return it."""
        if self.current_well is None:
            raise ToolStateError("No mold to place.")
        if not mold.valid:
            raise ToolStateError("Cannot pick up an invalid mold.")
        if self.placed_well_on_scale:
            raise ToolStateError("Cannot pick up mold, mold currently on scale.")
        position = machine.get_position()
        if not (position["X"] == mold.x or position["Y"] == mold.y or position["Z"] == SAFE_Z):
            raise ToolStateError("Toolhead is not correctly positioned over mold. Cannot pickup")
        if not position["T"] == self.TAMPER_AXIS_TRAVEL_POS:
            raise ToolStateError("Tamper axis did not start in travel position")
        # TODO: Decide feedrates for movement
        # TODO: Verify accuracy of actual vs expected mold location
        mold_to_place = self.current_well
        self.current_well = None
        print(f"Placing mold: {mold_to_place.name if hasattr(mold_to_place, 'name') else 'unnamed'}")
        machine._set_absolute_positioning()
        machine.move(z=148 s=) # Move until tamper leadscrew almost grounded
        machine.gcode("G1 T50 FXXX") # Put down mold holder
        machine._set_relative_positioning()
        machine.move(y=-25.5, s=) # Move out from under mold
        machine._set_absolute_positioning()
        machine.gcode("G1 T30 FXXX") # Move into tamper travel position
        machine.safe_z_movement() # Move back to safe z
        return mold_to_place

    def place_top_piston(self, machine: Machine, piston_dispenser: PistonDispenser):
        """
        Place the top piston on the current mold. Only allowed if carrying a mold without a top piston.
        """
        if self.current_well is None:
            raise ToolStateError("Must be carrying a mold to place a top piston.")
        
        if self.current_well.has_top_piston:
            raise ToolStateError("Mold already has a top piston.")

        if piston_dispenser.num_pistons == 0:
            raise ToolStateError("No pistons in dispenser.")
        if self.placed_well_on_scale:
            raise ToolStateError("Cannot add top piston, mold on scale.")

        position = machine.get_position()
        x = position['X']
        if not x == piston_dispenser.x:
            raise ToolStateError("X position does not match piston dispenser location.")
        y = position['Y']
        if not y == piston_dispenser.y:
            raise ToolStateError("Y position does not match piston dispenser location.")
        t = position['T']
        if not t == TAMPER_AXIS_TRAVEL_POS:
            raise ToolStateError("Tamper axis did not start in travel position.")
        if not z == SAFE_Z:
            raise ToolStateError("Z position did not start at safe z.")
        
        
        # TODO: Implement top piston placer hardware action
        self.current_well.has_top_piston = True
        print(f"Placing top piston on mold: {self.current_well.name if hasattr(self.current_well, 'name') else 'unnamed'}")
        return True
    

    # This macro assumes that the gantry has been moved to a known location in front of and above the trickler dispenser
    def place_mold_on_scale(self, machine: Machine, scale: Scale):
        """
        Place the current mold on the scale. Only allowed if carrying a mold without a top piston.
        """
        if self.current_well is None:
            raise ToolStateError("Must be carrying a mold to place on the scale.")
        
        if self.current_well.has_top_piston:
            raise ToolStateError("Mold already has a top piston.")
        position = machine.get_position()
        x = position['X']
        if not x == scale.x:
            raise ToolStateError("X position does not match scale location.")
        y = position['Y']
        if not y == scale.y:
            raise ToolStateError("Y position does not match scale location.")
        z = position['Z']
        if not z == scale.z:
            raise ToolStateError("Z position does not match scale location.")
        t = position['T']
        if not t == TAMPER_AXIS_TRAVEL_POS:
            raise ToolStateError("T axis was not in travel position")
        print(f"Placing mold on scale: {self.current_well.name if hasattr(self.current_well, 'name') else 'unnamed'}")
        self.placed_well_on_scale = True
        # TODO: Decide feedrate for moves
        machine._set_absolute_positioning() # Set absolute mode
        machine.move_to(z=134, s=) # Move to 5mm above scale
        machine.gcode("G1 T38.5 FXXX") # Move well so it fits under trickler
        machine.move(y=184, s=) # Move well under trickler
        machine.gcode("G1 T45 FXXX") # Place well on scale
        return True

    # Macro can/should only be called if a mold has been placed under the trickler 
    def pick_mold_from_scale(self, machine: Machine, scale: Scale):
        """
        Pick up the current mold from the scale. Only allowed if carrying a mold without a top piston.
        """
        if self.current_well is None:
            raise ToolStateError("Must be carrying a mold to pick from the scale.")
        
        if self.current_well.has_top_piston:
            raise ToolStateError("Mold already has a top piston.")
        if not self.placed_well_on_scale:
            raise ToolStateError("Well is not on scale, cannot pick up")
        print(f"Picking mold from scale: {self.current_well.name if hasattr(self.current_well, 'name') else 'unnamed'}")
        # TODO: Decide feedrate for moves
        machine._set_absolute_positioning()
        machine.gcode("G1 T38.5 FXXX") # Pick up mold
        machine.move(y=scale.y, s=) # Move from under trickler
        machine.safe_z_movement() # Move to safe z
        machine.gcode("G1 T{TAMP_AXIS_TRAVEL_POS} FXXX") # Move tamper back to travel position
        return True
