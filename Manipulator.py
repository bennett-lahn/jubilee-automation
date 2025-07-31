from science_jubilee.labware.Labware import Labware, Location, Well
from science_jubilee.tools.Tool import (
    Tool,
    ToolConfigurationError,
    ToolStateError,
    requires_active_tool,
)
from trickler_labware import WeightWell
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
    Jubilee toolhead with a rotary selection wheel for multiple tools.
    Tools include: tamper, picker, cap placer.
    The active tool is managed as a state variable.

    Tamping is primarily controlled using sensorless homing/stall detection, which is configured
    using the M915 command in config.g and homet.g, not this file. driver-stall.g is used to 
    control tamping after contact with the material.
    """
    TOOL_TAMPER = 'tamper'
    TOOL_PICKER = 'picker'
    TOOL_CAP_PLACER = 'cap_placer'
    TOOL_LIST = [TOOL_TAMPER, TOOL_PICKER, TOOL_CAP_PLACER]

    def __init__(self, index, name, config=None):
        super().__init__(index, name)
        self.active_tool = self.TOOL_PICKER  # Default tool
        self.rotary_position = 0  # Index of the tool currently selected
        self.config = config
        
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

    @requires_active_tool
    def home_tamper(self, machine_connection=None):
        """
        Perform sensorless homing for the tamper axis.
        
        Args:
            machine_connection: Connection to the Jubilee machine for sending commands
        """
        if self.active_tool != self.TOOL_TAMPER:
            raise ToolStateError("Tamper tool must be selected to perform homing.")
        
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

    @requires_active_tool
    def tamp(self, target_depth: float = None, machine_connection=None):
        """
        Perform tamping action. Only allowed if tamper is active.
        Enhanced version with stall detection.
        
        Args:
            target_depth: Target depth to tamp to (mm). If None, uses default depth.
            machine_connection: Connection to the Jubilee machine for sending commands
        """
        if self.active_tool != self.TOOL_TAMPER:
            raise ToolStateError("Tamper tool must be selected to perform tamping.")
        
        # Use default depth if not specified
        if target_depth is None:
            target_depth = self.tamper_position + 50.0  # Default 50mm tamp
        
        if machine_connection:
            if not machine_connection:
                raise RuntimeError("Jubilee not connected for tamping operation.")
            machine_connection.send_command('G91')  # Set relative mode
            for _ in range(10):
                machine_connection.send_command('G1 T-5 F600')  # Move tamper axis down 5mm at 600mm/min
            machine_connection.send_command('G90')  # Set absolute mode

    def get_tamper_status(self) -> Dict[str, Any]:
        """
        Get current tamper status and configuration.
        
        Returns:
            Dictionary containing tamper status information
        """
        return {
            'active_tool': self.active_tool,
            'tamper_position': self.tamper_position,
            'stall_detection_configured': self.stall_detection_configured,
            'sensorless_homing_configured': self.sensorless_homing_configured,
            'motor_specs': self.tamper_motor_specs.copy(),
            'stall_parameters': {
                'threshold': self.stall_threshold,
                'filter': self.stall_filter,
                'min_speed': self.stall_min_speed,
                'action': self.stall_action
            },
            'movement_parameters': {
                'axis': self.tamper_axis,
                'driver': self.tamper_driver,
                'board_address': self.tamper_board_address,
                'speed': self.tamper_speed,
                'acceleration': self.tamper_acceleration
            }
        }

    @requires_active_tool
    def pick(self):
        """Pick up a container. Only allowed if picker is active."""
        if self.active_tool != self.TOOL_PICKER:
            raise ToolStateError("Picker tool must be selected to pick up a container.")
        # TODO: Implement picker hardware action
        print("Picking up container...")

    @requires_active_tool
    def place(self):
        """Place down a container. Only allowed if picker is active."""
        if self.active_tool != self.TOOL_PICKER:
            raise ToolStateError("Picker tool must be selected to place a container.")
        # TODO: Implement picker hardware action
        print("Placing container...")

    @requires_active_tool
    def place_cap(self):
        """Place a cap on a mold. Only allowed if cap placer is active."""
        if self.active_tool != self.TOOL_CAP_PLACER:
            raise ToolStateError("Cap placer tool must be selected to place a cap.")
        # TODO: Implement cap placer hardware action
        print("Placing cap on mold...")

    def dispense_to_well(
        self,
        trickler,
        location,
        target_weight: float,
        coarse_speed: int = 1000,
        fine_speed: int = 200,
        coarse_step_mm: float = 0.1,
        fine_step_mm: float = 0.02,
        settling_time_s: float = 1.0
    ):
        """
        Dispense powder into a well until a target weight is reached.
        The manipulator handles movement to the well, while the trickler handles dispensing.
        """
        if not trickler.scale or not trickler.scale.is_connected:
            raise ToolStateError("Scale is not connected or provided.")
        # TODO: Implement movement to well location using picker
        # Example: self.pick(), move to location, self.place()
        if hasattr(location, 'max_weight'):
            trickler.check_weight_limit(0, target_weight, location.max_weight)
        trickler.initialize_scale()
        current_weight = trickler.scale.get_weight(stable=True)
        coarse_threshold = target_weight * 0.8
        print(f"Starting coarse dispensing to {coarse_threshold:.4f} g...")
        while current_weight < coarse_threshold:
            trickler.dispense_powder(coarse_step_mm, speed=coarse_speed)
            current_weight = trickler.scale.get_weight(stable=False)
            if current_weight >= target_weight:
                break
        print(f"Coarse dispensing complete. Current weight: {current_weight:.4f} g")
        print(f"Starting fine dispensing to target {target_weight:.4f} g...")
        while current_weight < target_weight:
            trickler.dispense_powder(fine_step_mm, speed=fine_speed)
            time.sleep(settling_time_s)
            current_weight = trickler.scale.get_weight(stable=True)
        print(f"Dispensing complete. Final weight: {current_weight:.4f} g (target: {target_weight:.4f} g)")
        if hasattr(location, 'set_weight'):
            location.set_weight(current_weight)

    def batch_dispense(
        self,
        trickler,
        locations: List,
        target_weights: List[float],
    ):
        """
        Dispense powder to multiple locations to reach their respective target weights.
        """
        if len(locations) != len(target_weights):
            raise ToolStateError("Number of locations and target weights must match.")
        for i, location in enumerate(locations):
            target_weight = target_weights[i]
            print(f"Dispensing to location {i+1}...")
            self.dispense_to_well(trickler, location, target_weight)
            print("-" * 20) 
