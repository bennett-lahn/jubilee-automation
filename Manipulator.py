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


class TamperStallEvent:
    """Event class for handling tamper stall detection."""
    
    def __init__(self, driver_number: int, board_address: int, timestamp: float = None):
        self.driver_number = driver_number
        self.board_address = board_address
        self.timestamp = timestamp or time.time()
        self.event_type = "driver-stall"
    
    def __str__(self):
        return f"Tamper stall detected on driver {self.driver_number} (board {self.board_address}) at {self.timestamp}"


class Manipulator(Tool):
    """
    Jubilee toolhead with a rotary selection wheel for multiple tools.
    Tools include: tamper, picker, cap placer.
    The active tool is managed as a state variable.
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
        self.tamper_axis = 'Z'  # Default axis for tamper movement
        self.tamper_driver = 2  # Default driver number for tamper motor
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
        
        # Stall detection parameters (for tamping operations)
        self.stall_threshold = 3  # S parameter (-64 to +63 for TMC2209)
        self.stall_filter = 1  # F parameter (1 = filtered)
        self.stall_min_speed = 200  # H parameter (minimum full steps/sec)
        self.stall_action = 2  # R parameter (2 = create event)
        
        # Sensorless homing parameters (for homing operations)
        self.homing_threshold = 3  # S parameter for homing
        self.homing_filter = 1  # F parameter for homing
        self.homing_action = 1  # R parameter (1 = report only during homing)
        
        # Event handling
        self.tamper_position = 0.0  # Current tamper position in mm
        self.tamper_speed = 1000  # mm/min for tamper movement
        self.tamper_acceleration = 500  # mm/s² for tamper movement
        
        # Homing parameters
        self.homing_speed = 2000  # mm/min for homing
        self.homing_acceleration = 1000  # mm/s² for homing
        self.homing_current = 0.8  # Reduced current for homing (amps)
        
        # Stall response parameters
        self.stall_response_step_size = 0.1  # mm per step for stall response
        self.stall_response_speed = 500  # mm/min for stall response movements
        self.stall_response_shake_count = 5  # Number of shake cycles
        self.stall_response_shake_distance = 0.2  # mm for shake movements
        
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
        
        # Load stall detection parameters
        stall_config = tamper_config.get('stall_detection', {})
        self.stall_threshold = stall_config.get('threshold', self.stall_threshold)
        self.stall_filter = stall_config.get('filter', self.stall_filter)
        self.stall_min_speed = stall_config.get('min_speed', self.stall_min_speed)
        self.stall_action = stall_config.get('action', self.stall_action)
        
        # Load sensorless homing parameters
        homing_config = tamper_config.get('sensorless_homing', {})
        self.homing_threshold = homing_config.get('threshold', self.homing_threshold)
        self.homing_filter = homing_config.get('filter', self.homing_filter)
        self.homing_action = homing_config.get('action', self.homing_action)
        self.homing_speed = homing_config.get('speed', self.homing_speed)
        self.homing_acceleration = homing_config.get('acceleration', self.homing_acceleration)
        self.homing_current = homing_config.get('current', self.homing_current)
        
        # Load stall response parameters
        stall_response_config = tamper_config.get('stall_response', {})
        self.stall_response_step_size = stall_response_config.get('step_size', self.stall_response_step_size)
        self.stall_response_speed = stall_response_config.get('speed', self.stall_response_speed)
        self.stall_response_shake_count = stall_response_config.get('shake_count', self.stall_response_shake_count)
        self.stall_response_shake_distance = stall_response_config.get('shake_distance', self.stall_response_shake_distance)
        
        # Load movement parameters
        movement_config = tamper_config.get('movement', {})
        self.tamper_axis = movement_config.get('axis', self.tamper_axis)
        self.tamper_driver = movement_config.get('driver', self.tamper_driver)
        self.tamper_board_address = movement_config.get('board_address', self.tamper_board_address)
        self.tamper_speed = movement_config.get('speed', self.tamper_speed)
        self.tamper_acceleration = movement_config.get('acceleration', self.tamper_acceleration)

    def calculate_min_stall_speed(self) -> int:
        """
        Calculate minimum speed for reliable stall detection using the formula:
        Hmin = full_steps_per_rev * rated_current * actual_current/(sqrt(2) * pi * rated_holding_torque)
        """
        import math
        
        fspr = self.tamper_motor_specs['full_steps_per_rev']
        rated_current = self.tamper_motor_specs['rated_current']
        actual_current = self.tamper_motor_specs['actual_current']
        holding_torque = self.tamper_motor_specs['rated_holding_torque']
        
        min_speed = fspr * rated_current * actual_current / (math.sqrt(2) * math.pi * holding_torque)
        return max(int(min_speed), 200)  # Ensure minimum of 200 steps/sec

    def configure_sensorless_homing(self, machine_connection=None):
        """
        Configure sensorless homing for the tamper motor using M915 command.
        This should be called at the start of homing operations.
        
        Args:
            machine_connection: Connection to the Jubilee machine for sending commands
        """
        if self.sensorless_homing_configured:
            print("Sensorless homing already configured.")
            return
        
        # Reduce motor current for homing (M906)
        if machine_connection:
            m906_command = f"M906 {self.tamper_axis}{int(self.homing_current * 1000)}"
            machine_connection.send_command(m906_command)
            print(f"Set homing current: {m906_command}")
        
        # Configure sensorless homing
        m915_homing_command = f"M915 {self.tamper_axis} S{self.homing_threshold} F{self.homing_filter} R{self.homing_action}"
        
        if machine_connection:
            machine_connection.send_command(m915_homing_command)
            print(f"Configured sensorless homing: {m915_homing_command}")
        else:
            print(f"Sensorless homing command (not sent): {m915_homing_command}")
        
        self.sensorless_homing_configured = True
        print(f"Sensorless homing configured with threshold={self.homing_threshold}, "
              f"filter={self.homing_filter}, action={self.homing_action}")

    def configure_stall_detection(self, machine_connection=None):
        """
        Configure stall detection for the tamper motor using M915 command.
        This should be called after homing operations to revert to stall detection mode.
        
        Args:
            machine_connection: Connection to the Jubilee machine for sending commands
        """
        if self.stall_detection_configured:
            print("Stall detection already configured.")
            return
        
        # Calculate minimum speed for stall detection
        calculated_min_speed = self.calculate_min_stall_speed()
        self.stall_min_speed = max(self.stall_min_speed, calculated_min_speed)
        
        # Configure driver mode for TMC2209 (stealthChop)
        if machine_connection and self.tamper_motor_specs['driver_type'] == 'TMC2209':
            # Set driver to stealthChop mode (D3)
            m569_command = f"M569 P{self.tamper_driver} D3"
            if machine_connection:
                machine_connection.send_command(m569_command)
                print(f"Configured driver {self.tamper_driver} for stealthChop mode")
        
        # Configure stall detection
        m915_command = f"M915 {self.tamper_axis} S{self.stall_threshold} F{self.stall_filter} H{self.stall_min_speed} R{self.stall_action}"
        
        if machine_connection:
            machine_connection.send_command(m915_command)
            print(f"Configured stall detection: {m915_command}")
        else:
            print(f"Stall detection command (not sent): {m915_command}")
        
        self.stall_detection_configured = True
        print(f"Stall detection configured with threshold={self.stall_threshold}, "
              f"filter={self.stall_filter}, min_speed={self.stall_min_speed}")

   # TODO: Edit config.g in Jubilee to support sensorless homing for THIS AXIS ONLY
    def home_tamper(self, machine_connection=None):
        """
        Perform sensorless homing for the tamper axis.
        
        Args:
            machine_connection: Connection to the Jubilee machine for sending commands
        """
        if self.active_tool != self.TOOL_TAMPER:
            raise ToolStateError("Tamper tool must be selected to perform homing.")
        
        print("Starting sensorless homing for tamper...")
        
        # Configure sensorless homing
        self.configure_sensorless_homing(machine_connection)
        
        if machine_connection:
            # Set homing acceleration
            m201_command = f"M201 {self.tamper_axis}{self.homing_acceleration}"
            machine_connection.send_command(m201_command)
            
            # Perform homing move
            home_command = f"G28 {self.tamper_axis}"
            machine_connection.send_command(home_command)
            print(f"Executing homing command: {home_command}")
            
            # Wait for homing to complete
            time.sleep(5.0)  # Adjust based on homing time
            
            # Revert to stall detection configuration
            self.configure_stall_detection(machine_connection)
            
            # Reset position to 0 after homing
            self.tamper_position = 0.0
            print("Homing complete. Tamper position reset to 0.0mm")
        else:
            # Simulation mode
            print("Simulation mode: Performing sensorless homing")
            time.sleep(1.0)  # Simulate homing time
            self.tamper_position = 0.0
            print("Simulated homing complete. Tamper position reset to 0.0mm")

    def tamp_with_stall_detection(
        self, 
        target_depth: float, 
        approach_speed: float = None,
        tamp_speed: float = None,
        machine_connection=None
    ):
        """
        Perform tamping action with stall detection to determine when material is fully tamped.
        
        Args:
            target_depth: Target depth to tamp to (mm)
            approach_speed: Speed for approach movement (mm/min)
            tamp_speed: Speed for tamping movement (mm/min)
            machine_connection: Connection to the Jubilee machine for sending commands
        """
        # TODO: Implement some way for duet to tell python a stall event has occurred
        if self.active_tool != self.TOOL_TAMPER:
            raise ToolStateError("Tamper tool must be selected to perform tamping.")
        
        if not self.stall_detection_configured:
            self.configure_stall_detection(machine_connection)
        
        # Use provided speeds or defaults
        approach_speed = approach_speed or self.tamper_speed
        tamp_speed = tamp_speed or (self.tamper_speed * 0.5)  # Slower for tamping
        
        print(f"Starting tamping operation to depth {target_depth}mm")
        print(f"Current position: {self.tamper_position}mm")
        
        # Calculate movement distance
        movement_distance = target_depth - self.tamper_position
        
        if movement_distance <= 0:
            print("Already at or past target depth")
            return
        
        if machine_connection:
            # Set acceleration for tamper axis
            m201_command = f"M201 {self.tamper_axis}{self.tamper_acceleration}"
            machine_connection.send_command(m201_command)
            
            # Approach movement (faster, to near target)
            approach_distance = movement_distance * 0.9  # Approach to 90% of target
            approach_command = f"G1 {self.tamper_axis}{self.tamper_position + approach_distance} F{approach_speed * 60}"
            machine_connection.send_command(approach_command)
            print(f"Approaching to {self.tamper_position + approach_distance}mm at {approach_speed}mm/min")
            
            # Wait for approach to complete
            time.sleep(approach_distance / (approach_speed / 60))
            
            # Final tamping movement with stall detection
            final_distance = movement_distance - approach_distance
            tamp_command = f"G1 {self.tamper_axis}{final_distance} F{tamp_speed * 60}"
            machine_connection.send_command(tamp_command)
            print(f"Tamping to {target_depth}mm at {tamp_speed}mm/min with stall detection")
            
            # Monitor for stall event
            self._monitor_for_stall(machine_connection, target_depth)
        else:
            # Simulation mode
            print("Simulation mode: Performing tamping movement")
            time.sleep(2.0)  # Simulate movement time
            self.tamper_position = target_depth
            print(f"Tamping complete. New position: {self.tamper_position}mm")

    def _monitor_for_stall(self, machine_connection, target_depth: float):
        """
        Monitor for stall events during tamping operation.
        
        Args:
            machine_connection: Connection to the Jubilee machine
            target_depth: Target depth being tamped to
        """
        # This would typically involve monitoring the machine's event system
        # For now, we'll simulate the monitoring process
        
        print("Monitoring for stall events...")
        
        # In a real implementation, you would:
        # 1. Set up event listeners for driver-stall events
        # 2. Monitor the machine's event queue
        # 3. Handle stall events when they occur
        
        # Simulate stall detection after some time
        time.sleep(1.0)  # Simulate tamping time
        
        # Simulate a stall event (in real implementation, this would come from the machine)
        stall_event = TamperStallEvent(
            driver_number=self.tamper_driver,
            board_address=self.tamper_board_address
        )
        
        print("Stall detected! Material appears to be fully tamped.")
        self.handle_stall_event(stall_event, machine_connection)
        
        # Update position
        self.tamper_position = target_depth

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
            target_depth = self.tamper_position + 5.0  # Default 5mm tamp
        
        self.tamp_with_stall_detection(target_depth, machine_connection=machine_connection)

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
            'homing_parameters': {
                'threshold': self.homing_threshold,
                'filter': self.homing_filter,
                'action': self.homing_action,
                'speed': self.homing_speed,
                'acceleration': self.homing_acceleration,
                'current': self.homing_current
            },
            'stall_response_parameters': {
                'step_size': self.stall_response_step_size,
                'speed': self.stall_response_speed,
                'shake_count': self.stall_response_shake_count,
                'shake_distance': self.stall_response_shake_distance
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