"""
JubileeManager - Centralized management of Jubilee machine and related components.

This module provides the JubileeManager class for coordinating complex tasks
that require interacting with the instantiated Jubilee machine as well as other
components like trickler or toolhead to perform complex tasks like weighing containers.
"""

import time
from typing import Optional

# Import Jubilee components
from science_jubilee.Machine import Machine
from Trickler import Trickler
from Scale import Scale
from trickler_labware import WeightWell, WeightWellSet
from PistonDispenser import PistonDispenser
from Manipulator import Manipulator

DUET_IP = "192.168.1.2"

class JubileeManager:
    """Manages the Jubilee machine and related components"""
    
    # TODO: make dispensers configurable from UI
    def __init__(self, num_piston_dispensers: int = 0, num_pistons_per_dispenser: int = 0):
        self.machine: Optional[Machine] = None
        self.scale: Optional[Scale] = None
        self.scale.x = ... # TODO: Set these to known good location to start manipulator macros
        self.scale.y = ...
        self.scale.z = ...
        self.trickler: Optional[Trickler] = None
        self.manipulator: Optional[Manipulator] = None
        self.connected = False
        self.piston_dispensers: List[PistonDispenser] = [PistonDispenser(i, num_pistons_per_dispenser) for i in range(num_piston_dispensers)]

        # Dispenser 0 is always at x=320, y=337 and future dispensers are each offset by 42.5 mm in the x-axis
        # The stored x/y is the "ready point" 35mm in front of the dispenser
        num = 0
        for dispenser in piston_dispensers:
            dispenser.x = 320 + num*42.5
            dispenser.y = 337
            num = num + 1
            
        self.well_set: WeightWellSet = WeightWellSet()
        self.well_set['A1'] = WeightWell(name='A1', x=0, y=0, z=0, target_weight=0)
        self.well_set['A2'] = WeightWell(name='A2', x=0, y=0, z=0, target_weight=0)
        self.well_set['A3'] = WeightWell(name='A3', x=0, y=0, z=0, target_weight=0)
        self.well_set['A4'] = WeightWell(name='A4', x=0, y=0, z=0, target_weight=0)
        self.well_set['B1'] = WeightWell(name='B1', x=0, y=0, z=0, target_weight=0)
        self.well_set['B2'] = WeightWell(name='B2', x=0, y=0, z=0, target_weight=0)
        self.well_set['B3'] = WeightWell(name='B3', x=0, y=0, z=0, target_weight=0)
        self.well_set['B4'] = WeightWell(name='B4', x=0, y=0, z=0, target_weight=0)
        self.well_set['C1'] = WeightWell(name='C1', x=0, y=0, z=0, target_weight=0)
        self.well_set['C2'] = WeightWell(name='C2', x=0, y=0, z=0, target_weight=0)
        self.well_set['C3'] = WeightWell(name='C3', x=0, y=0, z=0, target_weight=0)
        self.well_set['C4'] = WeightWell(name='C4', x=0, y=0, z=0, target_weight=0)
        self.well_set['D1'] = WeightWell(name='D1', x=0, y=0, z=0, target_weight=0)
        self.well_set['D2'] = WeightWell(name='D2', x=0, y=0, z=0, target_weight=0)
        self.well_set['D3'] = WeightWell(name='D3', x=0, y=0, z=0, target_weight=0)
        self.well_set['D4'] = WeightWell(name='D4', x=0, y=0, z=0, target_weight=0)
        
    def connect(self, machine_address: str = DUET_IP, scale_port: str = "/dev/ttyUSB0"):
        """Connect to Jubilee machine and scale"""
        try:
            # Connect to machine
            self.machine = Machine(address=machine_address)
            self.machine.connect()
            
            # Connect to scale
            self.scale = Scale(port=scale_port)
            self.scale.connect()

            self.manipulator = Manipulator(index=0, name="manipulator", config="manipulator_config", scale=self.scale)

            # Initialize trickler (assuming it's already loaded)
            # This would need to be configured based on your setup
            # self.trickler = Trickler(index=0, name="trickler", config="trickler_config", scale=self.scale)
            
            self.connected = True

            # Now get ready for dispensing by homing all axes, picking up tool, etc.

            self.machine.load(self.manipulator)

            self.machine.home_xyu()
            self.machine.home_z()
            # TODO: Update this to control machine moves to/from a safe location so that dispenser or trickler collisions don't occur
            self.machine.pickup_tool(self.manipulator)
            self.manipulator.home_tamper(self.machine)

            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from all components"""
        if self.machine:
            self.machine.disconnect()
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
            well = self.well_set[well_id]
            if not well.valid:
                raise ToolStateError("Well is not valid.")
            if well.has_top_piston:
                raise ToolStateError("Well already has a top piston. Cannot dispense.")
            
            # TODO: Implement movement to well location
            self._move_to_well(well_id)
            self.manipulator.pick_mold(well)
            self._move_to_scale()
            self.manipulator.place_well_on_scale(self.machine, self.scale)
            self._dispense_powder(target_weight)
            self.manipulator.pick_well_from_scale(self.machine, self.scale)
            dispenser_index = -1
            for dispenser in self.piston_dispensers:
                if dispenser.num_pistons > 0:
                    dispenser_index = dispenser.index
                    break
            if dispenser_index == -1:
                raise ToolStateError("No dispenser with pistons found.")
            self.get_piston_from_dispenser(dispenser_index)
            self.move_to_well(well_id)
            self.manipulator.place_well()
            return True
        except Exception as e:
            print(f"Dispensing error: {e}")
            return False

    def get_piston_from_dispenser(self, dispenser_index: int):
        """Get the top piston from a specific dispenser"""
        if not self.connected or not self.piston_dispensers:
            return False
        if self.manipulator.current_well is None:
            raise ToolStateError("No mold to place piston into.")
        
        try:
            x = piston_dispensers[dispenser_index].x
            y = piston_dispensers[dispenser_index].y

            self.machine.move(z=DISPENSER_SAFE_Z)
            self.machine.move_to(x=x, y=y)
            self.manipulator.place_top_piston(self.machine, self.piston_dispensers[dispenser_index])
            self.piston_dispensers[dispenser_index].remove_piston()
            self.well_set[well_id].set_piston(True)
            return True
        except Exception as e:
            print(f"Getting piston from dispenser error: {e}")
            return False

    def _move_to_well(self, well_id: str):
        """Move to a specific well"""
        if not self.connected or not self.well_set:
            return False
        
        try:
            well = self.well_set[well_id]
            if not well.valid:
                raise ToolStateError("Well is not valid.")
            self.machine.safe_z_movement()
            self.machine.move_to(x=well.x, y=well.y)
            # TODO: Figure out appropriate z offset from well location to move to
            return True
        except Exception as e:
            print(f"Error moving to well: {e}")
            return False

    def _move_to_scale(self):
        """Move to the scale"""
        if not self.connected or not self.scale:
            return False
        
        try:
            self.machine.safe_z_movement()
            self.machine.move_to(x=self.scale.x, y=self.scale.y)
            # TODO: Figure out appropriate z offset from scale location to move to
            return True
        except Exception as e:
            print(f"Error moving to scale: {e}")
            return False

    def _dispense_powder(self, target_weight: float):
        """Dispense powder to the scale"""
        if not self.connected or not self.scale:
            return False
        
        try:
            # ...
            return True
        except Exception as e:
            print(f"Error dispensing powder: {e}")
            return False
