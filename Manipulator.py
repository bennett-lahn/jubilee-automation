from science_jubilee.tools.Tool import (
    Tool,
    ToolConfigurationError,
    ToolStateError,
)
from trickler_labware import WeightWell
from Scale import Scale
import PistonDispenser
import time
from typing import List, Optional, Dict, Any
import json
import os
from ConfigLoader import config
from functools import wraps

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

    # ============================================================================
    # CONFIGURATION PARAMETERS
    # ============================================================================
    # NOTE: The tamper axis letter is configured via self.tamper_axis (default 'V')
    # in __init__. Changing self.tamper_axis will update all axis references 
    # throughout this class, including gcode commands.
    # ============================================================================
    
    # The tamper axis should be returned to this position after any functions that move the tamper complete
    TAMP_AXIS_TRAVEL_POS = 30 # mm
    DISPENSER_SAFE_Z = 254 # mm, z should be set to this height before moving to cap dispenser ready point or gantry will hit trickler
    SAFE_Z = 195 # mm

    def __init__(self, index, name, state_machine=None, config=None):
        super().__init__(index, name)
        self.state_machine = state_machine  # Reference to MotionPlatformStateMachine
        self.config = config
        
        # Tamper-specific attributes
        self.tamper_axis = 'V'  # Default axis for tamper movement
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
    
    def _get_config_dict(self) -> Dict[str, Any]:
        """Helper to package manipulator configuration for state machine calls."""
        return {
            'tamper_axis': self.tamper_axis,
            'tamper_travel_pos': self.TAMP_AXIS_TRAVEL_POS,
            'safe_z': self.SAFE_Z,
            'dispenser_safe_z': self.DISPENSER_SAFE_Z,
        }
    
    @property
    def machine(self):
        """Access to machine through state machine for read-only queries."""
        if self.state_machine:
            return self.state_machine.machine
        return None
    
    @property
    def current_well(self):
        """Access to current well through state machine."""
        if self.state_machine:
            return self.state_machine.context.current_well
        return None
    
    @property
    def placed_well_on_scale(self):
        """Access to mold_on_scale state through state machine."""
        if self.state_machine:
            return self.state_machine.context.mold_on_scale
        return False

    def home_tamper(self, machine_connection=None):
        """
        Perform sensorless homing for the tamper axis.
        
        Validates and executes through MotionPlatformStateMachine.
        
        Args:
            machine_connection: Deprecated parameter (for backward compatibility)
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        # Validate and execute through state machine
        result = self.state_machine.validated_home_tamper(
            tamper_axis=self.tamper_axis
        )
        
        if not result.valid:
            raise RuntimeError(f"Tamper homing failed: {result.reason}")

    # TODO: Figure out how to merge stall detection with this function so that we can handle stall detection gracefully
    @requires_carrying_mold
    @requires_mold_without_piston
    def tamp(self, scale: Scale, target_depth: float = None):
        """
        Perform tamping action. Only allowed if carrying a mold without a cap.
        
        Args:
            scale: The Scale instance with position information
            target_depth: Target depth to tamp to (mm). If None, uses default depth.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        if not self.placed_well_on_scale:
            raise ToolStateError("Cannot tamp, no mold on scale.")
        
        # Call state machine method which validates and executes
        result = self.state_machine.validated_tamp(
            scale=scale,
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot tamp: {result.reason}")
        
        return True

    def vibrate_tamper(self, machine_connection=None):
        # TODO: Update when vibration functionality added
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

    def pick_mold(self, mold: WeightWell):
        """
        Pick up mold from well.
        
        Assumes toolhead is directly above the well at safe_z height with tamper axis in travel position.
        Validates move through state machine before execution.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        result = self.state_machine.validated_pick_mold_from_well(
            mold=mold,
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot pick mold: {result.reason}")

    def place_well(self) -> WeightWell:
        """
        Place down the current mold and return it.
        
        Assumes toolhead is directly above the well at safe_z height with tamper axis in travel position.
        Validates move through state machine before execution.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        mold_to_place = self.current_well
        result = self.state_machine.validated_place_mold_in_well(
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot place mold: {result.reason}")
        
        return mold_to_place

    def place_top_piston(self, piston_dispenser: PistonDispenser):
        """
        Place the top piston on the current mold. Only allowed if carrying a mold without a top piston.
        
        Assumes toolhead is at dispenser position.
        Validates move through state machine before execution.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        # Call state machine method which validates and executes
        result = self.state_machine.validated_place_top_piston(
            piston_dispenser=piston_dispenser,
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot place top piston: {result.reason}")
        
        return True

    def place_well_on_scale(self, scale: Scale):
        """
        Place the current mold on the scale. Only allowed if carrying a mold without a top piston.
        
        Validates move through state machine before execution.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        # Call state machine method which validates and executes
        result = self.state_machine.validated_place_mold_on_scale(
            scale=scale,
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot place mold on scale: {result.reason}")
        
        return True

    def pick_well_from_scale(self, scale: Scale):
        """
        Pick up the current mold from the scale. Only allowed if carrying a mold without a top piston.
        
        Validates move through state machine before execution.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        # Call state machine method which validates and executes
        result = self.state_machine.validated_pick_mold_from_scale(
            scale=scale,
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot pick mold from scale: {result.reason}")
        
        return True
