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

class JubileeManager:
    """Manages the Jubilee machine and related components"""
    
    # TODO: make dispensers configurable from UI
    def __init__(self, num_piston_dispensers: int = 0, num_pistons_per_dispenser: int = 0):
        self.machine: Optional[Machine] = None
        self.scale: Optional[Scale] = None
        self.trickler: Optional[Trickler] = None
        self.connected = False
        self.piston_dispensers: List[PistonDispenser] = [PistonDispenser(i, num_pistons_per_dispenser) for i in range(num_piston_dispensers)]
        self.well_set: WeightWellSet = WeightWellSet()
        self.well_set.wells = # TODO: Instantiate each well in set when locations known
        
    def connect(self, machine_address: str = "192.168.1.2", scale_port: str = "/dev/ttyUSB0"):
        """Connect to Jubilee machine and scale"""
        try:
            # Connect to machine
            self.machine = Machine(address=machine_address)
            self.machine.connect()
            
            # Connect to scale
            self.scale = Scale(port=scale_port)
            self.scale.connect()
            
            # Initialize trickler (assuming it's already loaded)
            # This would need to be configured based on your setup
            # self.trickler = Trickler(index=0, name="trickler", config="trickler_config", scale=self.scale)
            
            self.connected = True
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
            # This would need to be implemented based on your specific setup
            # For now, we'll simulate the dispensing
            time.sleep(2)  # Simulate dispensing time
            return True
        except Exception as e:
            print(f"Dispensing error: {e}")
            return False
    
    def place_top_piston(self, well_id: str, dispenser_index: int):
        """Place the top piston from a specific dispenser into a specific well"""
        if not self.connected or not self.trickler:
            return False
        
        try:
            self.get_piston_from_dispenser(dispenser_index)
            # ...
            self.well_set[well_id].set_piston(True)
            return True
        except Exception as e:
            print(f"Placing top piston error: {e}")
            return False

    def get_piston_from_dispenser(self, dispenser_index: int):
        """Get the top piston from a specific dispenser"""
        if not self.connected or not self.piston_dispensers:
            return False
        
        try:
            self.piston_dispensers[dispenser_index].remove_piston()
            return True
        except Exception as e:
            print(f"Getting piston from dispenser error: {e}")
            return False

    def __move_to_well(self, well_id: str):
        """Move to a specific well"""
        if not self.connected or not self.well_set:
            return False
        
        try:
            # ...
            return True
        except Exception as e:
            print(f"Error moving to well: {e}")
            return False

    def __place_piston(self, well_id: str):
        """Place the piston into a specific well"""
        if not self.connected or not self.well_set:
            return False
        
        try:
            # ...
            return True
        except Exception as e:
            print(f"Error placing piston: {e}")
            return False

    def __pick_up_well(self, well_id: str):
        """Pick up a specific well"""
        if not self.connected or not self.well_set:
            return False
        
        try:
            # ...
            return True
        except Exception as e:
            print(f"Error picking up well: {e}")