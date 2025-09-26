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
from config_loader import config
from functools import wraps

# Fixed tamp, claw moves mold up into tamp
# Cap silo/hopper
# Claw moves vertically within toolhead
# Big and small port for trickler using rotary tube
# rotate tamper to remove powder
# no rotary toolhead / ignore for now ; fixed tamper
    # For now focus on figuring out how to detect stop using motor torque/current

def requires_safe_z_manipulator(func):
    """
    Decorator for Manipulator methods that require safe Z height.
    Assumes the decorated method belongs to a class with:
    - self.machine_connection (Machine object)
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.machine_connection:
            raise RuntimeError("Machine connection not available")
        
        # Get current Z position
        current_z = float(self.machine_connection.get_position()["Z"])
        
        # Get safe Z height from config
        safe_z = config.get_safe_z()
        
        # Move to safe height if needed
        if current_z < safe_z:
            safe_height = safe_z + config.get_safe_z_offset()
            self.machine_connection.move_to(z=safe_height)
        
        return func(self, *args, **kwargs)
    
    return wrapper

def requires_carrying_mold(func):
    """
    Decorator for methods that require carrying a mold.
    Checks that self.current_well is not None.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.current_well is None:
            raise ToolStateError("Must be carrying a mold to perform this operation.")
        return func(self, *args, **kwargs)
    
    return wrapper

def requires_not_carrying_mold(func):
    """
    Decorator for methods that require NOT carrying a mold.
    Checks that self.current_well is None.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.current_well is not None:
            raise ToolStateError("Already carrying a mold. Place current mold before performing this operation.")
        return func(self, *args, **kwargs)
    
    return wrapper

def requires_mold_without_piston(func):
    """
    Decorator for methods that require the current mold to not have a top piston.
    Checks that self.current_well.has_top_piston is False.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.current_well is None:
            raise ToolStateError("Must be carrying a mold to perform this operation.")
        if self.current_well.has_top_piston:
            raise ToolStateError("Cannot perform operation on mold that already has a top piston.")
        return func(self, *args, **kwargs)
    
    return wrapper

def requires_valid_mold(func):
    """
    Decorator for methods that require a valid mold parameter.
    Checks that the first argument (mold) is valid.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if args and hasattr(args[0], 'valid'):
            mold = args[0]
            if not mold.valid:
                raise ToolStateError("Cannot perform operation on an invalid mold.")
        return func(self, *args, **kwargs)
    
    return wrapper

def requires_machine_connection(func):
    """
    Decorator for methods that require a machine connection.
    Checks that self.machine_connection is available.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.machine_connection:
            raise RuntimeError("Machine connection not available for this operation.")
        return func(self, *args, **kwargs)
    
    return wrapper

# Error checks have been moved into decorators above

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
    DISPENSER_SAFE_Z = 254 # mm, z should be set to this height before moving to cap dispenser ready point or gantry will hit trickler
    SAFE_Z = 195 # mm

    def __init__(self, index, name, machine=None, config=None):
        super().__init__(index, name)
        self.current_well = None  # WeightWell object representing the current mold
        self.machine = machine # Attached jubilee machine object
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
        if not self.machine_connection:
            raise RuntimeError("Machine connection not available for tamper homing.")
            
        axes_homed = getattr(machine_connection, 'axes_homed', [False, False, False, False])
        axis_names = ['X', 'Y', 'Z', 'U']
        not_homed = [axis_names[i] for i in range(4) if not axes_homed[i]]  # Only check X, Y, Z
        if not_homed:
            print(f"Axes not homed: {', '.join(not_homed)}")
            raise RuntimeError("X, Y, Z, and U axes must be homed before homing the tamper (T) axis.")
        # Perform homing for tamper axis
        machine_connection.send_command('M98 P"homet.g"')
        
        print("Homing complete. Tamper position reset to 0.0mm")

    # TODO: Figure out how to merge stall detection with this function so that we can handle stall detection gracefully
    @requires_carrying_mold
    @requires_mold_without_piston
    @requires_machine_connection
    def tamp(self, target_depth: float = None, machine_connection=None):
        """
        Perform tamping action. Only allowed if carrying a mold without a cap.
        Enhanced version with stall detection.
        
        Args:
            target_depth: Target depth to tamp to (mm). If None, uses default depth.
            machine_connection: Connection to the Jubilee machine for sending commands
        """
        if not self.current_well.placed_well_on_scale:
            raise ToolStateError("Cannot tamp, no mold on scale.")
        print(f"Tamping mold: {self.current_well.name if hasattr(self.current_well, 'name') else 'unnamed'}")
        
        machine._set_absolute_positioning();
        machine.gcode("G1 T38.5 FXXX") # Pick up mold
        machine.move(y=scale.y, s=) # Move from under trickler
        machine.gcode("G1 T0 FXXX") # Move tamper until stall detection stops movement
        
        


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
    @requires_safe_z_manipulator
    @requires_not_carrying_mold
    @requires_valid_mold
    def pick_from_well(self, mold: WeightWell):
        """Pick up mold from well. """
        if mold.has_top_piston:
            raise ToolStateError("Mold to be picked up already has a top piston.")
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

    @requires_carrying_mold
    def place_in_well(self) -> WeightWell:
        """Place down the current mold and return it."""
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

    @requires_carrying_mold
    @requires_mold_without_piston
    def place_top_piston(self, machine: Machine, piston_dispenser: PistonDispenser):
        """
        Place the top piston on the current mold. Only allowed if carrying a mold without a top piston.
        """

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
        if not z == DISPENSER_SAFE_Z:
            raise ToolStateError("Z position did not start at dispenser safe z.")
        print(f"Placing top piston on mold: {self.current_well.name if hasattr(self.current_well, 'name') else 'unnamed'}")

        # TODO: Decide on movement feed rates
        machine._set_absolute_positioning()
        machine.gcode("G1 T52 FXXX") # Fully lower mold
        machine.move(z=189 s=...) # Move so mold will fit just under cap
        machie._set_relative_positioning()
        machine.move(y=35 s=...) # Move under cap dispenser so that cap drops; each piston_dispenser x/y is 35mm away from the middle point
        machine._set_absolute_positioning()
        machine.gcode("G1 T37.3 FXXX") # Move tamper to pick up cap # TODO: Not sure the tolerances line up here to actually pick up the cap
        machine.move(x=piston_dispenser.x, y=piston_dispenser.y, s=...) # Return to start point
        machine.gcode("G1 T{TAMPER_AXIS_TRAVEL_POS} FXXX") # Move tamper back to travel position
        self.current_well.has_top_position = True
        self.current_well.has_top_piston = True
        return True

    # This macro assumes that the gantry has been moved to a known location in front of and above the trickler dispenser
    @requires_safe_z_manipulator
    @requires_carrying_mold
    @requires_mold_without_piston
    def place_mold_on_scale(self, machine: Machine, scale: Scale):
        """
        Place the current mold on the scale. Only allowed if carrying a mold without a top piston.
        """
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
    @requires_safe_z_manipulator
    @requires_carrying_mold
    @requires_mold_without_piston
    def pick_mold_from_scale(self, machine: Machine, scale: Scale):
        """
        Pick up the current mold from the scale. Only allowed if carrying a mold without a top piston.
        """
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
