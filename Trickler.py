import json
import os
import time
import warnings
from typing import Tuple, Union, List, Dict

import numpy as np

from science_jubilee.labware.Labware import Labware, Location, Well
from science_jubilee.tools.Tool import (
    Tool,
    ToolConfigurationError,
    ToolStateError,
    requires_active_tool,
)
from trickler_labware import WeightWell
from Scale import Scale


class Trickler(Tool):
    """A class representation of a powder trickler tool.

    :param Tool: The base tool class
    :type Tool: :class:`Tool`
    """

    def __init__(self, index, name, config, scale: Scale):
        """Constructor method"""
        super().__init__(index, name)
        self.min_range = 0
        self.max_range = None
        self.mm_to_g = None  # Conversion factor from mm movement to grams of powder
        self.e_drive = "E"
        self.scale = scale
        self.load_config(config)

    def load_config(self, config):
        """Loads the configuration file for the trickler tool

        :param config: Name of the config file for the trickler. Expects the file to be in /tools/configs
        :type config: str
        """

        config_directory = os.path.join(os.path.dirname(__file__), "configs")
        config_path = os.path.join(config_directory, f"{config}.json")
        if not os.path.isfile(config_path):
            raise ToolConfigurationError(
                f"Error: Config file {config_path} does not exist!"
            )

        with open(config_path, "r") as f:
            config = json.load(f)
        self.min_range = config["min_range"]
        self.max_range = config["max_range"]
        self.mm_to_g = config["mm_to_g"]  # mm movement to grams conversion

        # Check that all information was provided
        if None in [self.min_range, self.max_range, self.mm_to_g]:
            raise ToolConfigurationError(
                "Error: Not enough information provided in configuration file."
            )

    def post_load(self):
        """
        Query the object model after loading the tool to find the extruder number of this trickler.
        The extruder is used to move the trickler mechanism.
        """

        # To read the position of an extruder, we need to know which extruder number to look at
        # Query the object model to find this
        tool_info = json.loads(self._machine.gcode('M409 K"tools[]"'))["result"]
        for tool in tool_info:
            if tool["number"] == self.index:
                self.e_drive = (
                    f"E{tool['extruders'][0]}"
                )
            else:
                continue

    def check_bounds(self, pos):
        """Disallow commands outside of the trickler's configured range

        :param pos: The E position to check
        :type pos: float
        """

        if pos > self.max_range or pos < self.min_range:
            raise ToolStateError(f"Error: {pos} is out of bounds for the trickler!")

    def check_weight_limit(self, current_weight: float, target_weight: float, max_weight: float = None):
        """Check that the target weight does not exceed the maximum weight limit.
        
        :param current_weight: Current weight in grams
        :type current_weight: float
        :param target_weight: Target weight in grams
        :type target_weight: float
        :param max_weight: Maximum allowed weight in grams, defaults to None
        :type max_weight: float, optional
        """
        if max_weight is not None and target_weight > max_weight:
            raise ToolStateError(f"Error: Target weight {target_weight}g exceeds maximum weight {max_weight}g!")
        
        if target_weight < current_weight:
            raise ToolStateError(f"Error: Target weight {target_weight}g is less than current weight {current_weight}g!")

    @requires_active_tool
    def dispense_powder(self, amount_mm: float, s: int = 2000):
        """Dispense powder by moving the trickler mechanism a specified amount.
        This is a "dumb" function that just moves the mechanism - weight measurement
        is handled externally.

        :param amount_mm: Amount to move the trickler mechanism in mm
        :type amount_mm: float
        :param s: Speed to move in mm/min, defaults to 2000
        :type s: int, optional
        """
        de = amount_mm
        pos = self._machine.get_position()
        end_pos = float(pos[self.e_drive]) + de
        self.check_bounds(end_pos)
        self._machine.move(de=de, wait=True)

    @requires_active_tool
    def retract_powder(self, amount_mm: float, s: int = 2000):
        """Retract the trickler mechanism by a specified amount.

        :param amount_mm: Amount to retract the trickler mechanism in mm
        :type amount_mm: float
        :param s: Speed to move in mm/min, defaults to 2000
        :type s: int, optional
        """
        de = -1 * amount_mm
        pos = self._machine.get_position()
        end_pos = float(pos[self.e_drive]) + de
        self.check_bounds(end_pos)
        self._machine.move(de=de, wait=True)

    @requires_active_tool
    def dispense_to_well(
        self,
        location: Union[WeightWell, Tuple, Location],
        target_weight: float,
        coarse_speed: int = 1000,
        fine_speed: int = 200,
        coarse_step_mm: float = 0.1,
        fine_step_mm: float = 0.02,
        settling_time_s: float = 1.0
    ):
        """
        Dispense powder into a well until a target weight is reached.

        This method uses a coarse and fine dispensing strategy to accurately
        reach the target weight.

        :param location: The location (e.g., a `WeightWell` object) to dispense powder into.
        :type location: Union[WeightWell, Tuple, Location]
        :param target_weight: The target weight in grams.
        :type target_weight: float
        :param coarse_speed: The speed for coarse dispensing in mm/min.
        :type coarse_speed: int
        :param fine_speed: The speed for fine dispensing in mm/min.
        :type fine_speed: int
        :param coarse_step_mm: The motor movement amount for each coarse dispensing step.
        :type coarse_step_mm: float
        :param fine_step_mm: The motor movement amount for each fine dispensing step.
        :type fine_step_mm: float
        :param settling_time_s: Time to wait for the scale to settle after dispensing.
        :type settling_time_s: float
        """
        if not self.scale or not self.scale.is_connected:
            raise ToolStateError("Scale is not connected or provided.")

        x, y, z = Labware._getxyz(location)

        self._machine.safe_z_movement()
        self._machine.move_to(x=x, y=y)
        self._machine.move_to(z=z)

        if isinstance(location, WeightWell):
            self.current_well = location
            self.check_weight_limit(0, target_weight, location.max_weight) # Check against max_weight of well
        elif isinstance(location, Location) and isinstance(location.labware, WeightWell):
            self.current_well = location.labware
            self.check_weight_limit(0, target_weight, location.labware.max_weight)
        
        # Start dispensing loop
        current_weight = self.scale.get_weight()
        
        # Coarse dispensing threshold (e.g., 80% of target for small amounts)
        coarse_threshold = target_weight * 0.8

        # Coarse dispensing
        while current_weight < coarse_threshold:
            self.dispense_powder(coarse_step_mm, s=coarse_speed)
            # This is for simulation
            if hasattr(self.scale, '_add_to_simulation_weight'):
                # use mm_to_g to simulate weight change
                dispensed_g = coarse_step_mm * self.mm_to_g
                self.scale._add_to_simulation_weight(dispensed_g)

            time.sleep(settling_time_s)
            current_weight = self.scale.get_weight()
            if current_weight >= target_weight:
                break

        # Fine dispensing
        while current_weight < target_weight:
            self.dispense_powder(fine_step_mm, s=fine_speed)
             # This is for simulation
            if hasattr(self.scale, '_add_to_simulation_weight'):
                dispensed_g = fine_step_mm * self.mm_to_g
                self.scale._add_to_simulation_weight(dispensed_g)
                
            time.sleep(settling_time_s)
            current_weight = self.scale.get_weight()

        print(f"Dispensing complete. Final weight: {current_weight:.4f} g (target: {target_weight:.4f} g)")

        if isinstance(self.current_well, WeightWell):
            self.current_well.set_weight(current_weight)
            
    @requires_active_tool
    def batch_dispense(
        self,
        locations: List[Union[WeightWell, Tuple, Location]],
        target_weights: List[float],
    ):
        """
        Dispense powder to multiple locations to reach their respective target weights.

        :param locations: List of locations to dispense powder into.
        :type locations: List[Union[WeightWell, Tuple, Location]]
        :param target_weights: List of target weights in grams for each location.
        :type target_weights: List[float]
        """
        if len(locations) != len(target_weights):
            raise ValueError("Number of locations and target weights must match.")
        
        for i, location in enumerate(locations):
            target_weight = target_weights[i]
            
            print(f"Dispensing to location {i+1}...")
            if self.scale:
                self.scale.zero() # Zero the scale for each new well.

            self.dispense_to_well(location, target_weight)

            print("-" * 20)

    def estimate_dispense_amount(self, target_weight_g: float) -> float:
        """Estimate the amount of movement needed to dispense a target weight.
        This is a helper function for external control systems.

        :param target_weight_g: Target weight in grams
        :type target_weight_g: float
        :return: Estimated movement amount in mm
        :rtype: float
        """
        return target_weight_g / self.mm_to_g

    def get_current_position(self) -> float:
        """Get the current position of the trickler mechanism.

        :return: Current position in mm
        :rtype: float
        """
        pos = self._machine.get_position()
        return float(pos[self.e_drive])
