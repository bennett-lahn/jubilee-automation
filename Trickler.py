import json
import os
import time
import warnings
from typing import Tuple, Union, List, Dict

import numpy as np

# Remove Tool and toolhead-specific imports
# from science_jubilee.labware.Labware import Labware, Location, Well
# from science_jubilee.tools.Tool import (
#     Tool,
#     ToolConfigurationError,
#     ToolStateError,
#     requires_active_tool,
# )
from trickler_labware import WeightWell
from Scale import Scale

class TricklerConfigurationError(Exception):
    pass

class TricklerStateError(Exception):
    pass

class Trickler:
    """A class representation of a powder trickler device, bed-mounted.

    Supports both GPIO and Duet stepper control.
    """
    def __init__(self, config, scale: Scale, control_mode: str = "duet", duet_machine=None, gpio_controller=None):
        """Constructor method
        :param config: Name of the config file for the trickler. Expects the file to be in /configs
        :param scale: Scale object for weighing
        :param control_mode: 'duet' or 'gpio'
        :param duet_machine: Duet machine object if using Duet
        :param gpio_controller: GPIO controller object if using GPIO
        """
        self.min_range = 0
        self.max_range = None
        self.mm_to_g = None  # Conversion factor from mm movement to grams of powder
        self.scale = scale
        self.control_mode = control_mode
        self.duet_machine = duet_machine
        self.gpio_controller = gpio_controller
        self.e_drive = "E"  # Only used for duet
        self.load_config(config)

    def load_config(self, config):
        config_directory = os.path.join(os.path.dirname(__file__), "configs")
        config_path = os.path.join(config_directory, f"{config}.json")
        if not os.path.isfile(config_path):
            raise TricklerConfigurationError(
                f"Error: Config file {config_path} does not exist!"
            )
        with open(config_path, "r") as f:
            config = json.load(f)
        self.min_range = config["min_range"]
        self.max_range = config["max_range"]
        self.mm_to_g = config["mm_to_g"]
        if None in [self.min_range, self.max_range, self.mm_to_g]:
            raise TricklerConfigurationError(
                "Error: Not enough information provided in configuration file."
            )

    def check_bounds(self, pos):
        """Disallow commands outside of the trickler's configured range

        :param pos: The E position to check
        :type pos: float
        """

        if pos > self.max_range or pos < self.min_range:
            raise TricklerStateError(f"Error: {pos} is out of bounds for the trickler!")

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
            raise TricklerStateError(f"Error: Target weight {target_weight}g exceeds maximum weight {max_weight}g!")
        if target_weight < current_weight:
            raise TricklerStateError(f"Error: Target weight {target_weight}g is less than current weight {current_weight}g!")

    def initialize_scale(self):
        """Initialize the scale for weighing by re-zeroing and taring the container.
        """
        if not self.scale or not self.scale.is_connected:
            raise TricklerStateError("Scale is not connected or provided.")
        try:
            self.scale.re_zero()
            time.sleep(0.5)
            self.tare_container()
            print("Scale initialized and tared.")
        except Exception as e:
            raise TricklerStateError(f"Failed to initialize scale: {e}")

    def tare_container(self):
        # Placeholder for future container movement logic
        pass

    def _move_trickler(self, de: float, speed: int = 2000):
        """Move the trickler mechanism by de mm, using the selected control mode."""
        if self.control_mode == "duet":
            if not self.duet_machine:
                raise TricklerStateError("Duet machine not provided for duet control mode.")
            pos = self.duet_machine.get_position()
            end_pos = float(pos[self.e_drive]) + de
            self.check_bounds(end_pos)
            self.duet_machine.move(de=de, wait=True)
        elif self.control_mode == "gpio":
            if not self.gpio_controller:
                raise TricklerStateError("GPIO controller not provided for gpio control mode.")
            # Implement GPIO stepper control logic here
            # Example: self.gpio_controller.move_stepper(de, speed)
            pass
        else:
            raise TricklerStateError(f"Unknown control mode: {self.control_mode}")

    def dispense_powder(self, amount_mm: float, speed: int = 2000):
        """Dispense powder by moving the trickler mechanism a specified amount."""
        self._move_trickler(amount_mm, speed)

    def retract_powder(self, amount_mm: float, speed: int = 2000):
        self._move_trickler(-amount_mm, speed)

    def estimate_dispense_amount(self, target_weight_g: float) -> float:
        return target_weight_g / self.mm_to_g

    def get_current_position(self) -> float:
        if self.control_mode == "duet":
            if not self.duet_machine:
                raise TricklerStateError("Duet machine not provided for duet control mode.")
            pos = self.duet_machine.get_position()
            return float(pos[self.e_drive])
        elif self.control_mode == "gpio":
            # Implement GPIO position tracking if available
            return 0.0  # Placeholder
        else:
            raise TricklerStateError(f"Unknown control mode: {self.control_mode}")
