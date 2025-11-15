"""
JubileeManager - Centralized management of Jubilee machine and related components.

This module provides the JubileeManager class for coordinating complex tasks
that require interacting with the instantiated Jubilee machine as well as other
components like trickler or toolhead to perform complex tasks like weighing containers.
"""

from typing import Optional, List

# Import Jubilee components
from science_jubilee.Machine import Machine
from science_jubilee.decks.Deck import Deck
from Trickler import Trickler
from Scale import Scale
from trickler_labware import WeightWell
from PistonDispenser import PistonDispenser
from Manipulator import Manipulator, ToolStateError
from ConfigLoader import config
from functools import wraps


def requires_safe_z_machine(func):
    """
    Decorator for JubileeManager methods that require safe Z height.
    Assumes the decorated method belongs to a class with:
    - self.machine (Machine object)
    - self.deck (Deck object)
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.machine or not self.connected:
            raise RuntimeError("Machine not connected")
        
        # Get current Z position
        current_z = float(self.machine.get_position()["Z"])
        
        # Get safe Z height
        if self.deck:
            safe_z = self.deck.safe_z
        else:
            safe_z = config.get_safe_z()
        
        # Move to safe height if needed
        if current_z < safe_z:
            safe_height = safe_z + config.get_safe_z_offset()
            self.machine.move_to(z=safe_height)
        
        return func(self, *args, **kwargs)
    
    return wrapper

def requires_well_validation(func):
    """
    Decorator for methods that require a valid well.
    Assumes the decorated method has a 'well' parameter or 'well_id' parameter.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # Check if well_id is in kwargs or args
        well_id = kwargs.get('well_id')
        if not well_id and args:
            # Assume first argument after self is well_id
            well_id = args[0]
        
        if well_id:
            # For JubileeManager, validate well exists in deck
            if hasattr(self, 'deck') and self.deck:
                well = self._get_well_from_deck(well_id)
                if not well or not well.valid:
                    raise ValueError(f"Well {well_id} is not valid or not found")
        
        return func(self, *args, **kwargs)
    
    return wrapper

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
        # TODO: Move these numbers to a config file
        num = 0
        for dispenser in self.piston_dispensers:
            dispenser.x = 320 + num*42.5
            dispenser.y = 337
            num = num + 1
            
        # Initialize deck with weight well configuration
        self.deck: Optional[Deck] = None
        self._initialize_deck()
    
    def _initialize_deck(self):
        """Initialize the deck with weight wells in each slot"""
        try:
            # Load the deck configuration
            # Override deck safe_z from centralized config
            self.deck = Deck("weight_well_deck", path="./jubilee_api_config")
            
            # Load weight well labware into each slot
            for i in range(16):
                # Load the weight well labware into each slot
                labware = self.deck.load_labware("weight_well_labware", i, path="./jubilee_api_config")
                
                # Convert the labware wells to WeightWell objects
                for well_name, well in labware.wells.items():
                    # Create a WeightWell with only required fields and defaults for custom parameters
                    weight_well = WeightWell(
                        name=well_name,  # name
                        x=well.x + labware.offset[0],  # x
                        y=well.y + labware.offset[1],  # y
                        z=well.z + labware.offset[2] if len(labware.offset) > 2 else well.z,  # z
                        offset=well.offset,  # offset
                        slot=well.slot,  # slot
                        labware_name=well.labware_name,  # labware_name
                        # WeightWell custom parameters with defaults
                        valid=True,
                        has_top_piston=False,
                        current_weight=0.0,
                        target_weight=0.0,
                        max_weight=None
                    )
                    
                    # Replace the regular well with our WeightWell
                    labware.wells[well_name] = weight_well
                
        except Exception as e:
            print(f"Error initializing deck: {e}")
            self.deck = None
    
    def _get_well_from_deck(self, well_id: str) -> Optional[WeightWell]:
        """Get a weight well from the deck by well ID"""
        if not self.deck:
            return None
        
        # Convert well_id to slot index
        # Layout: Row A has 7 molds (0-6), Row B has 7 molds (7-13), Row C has 4 molds (14-17)
        row = ord(well_id[0].upper()) - ord('A')
        col = int(well_id[1:]) - 1
        
        # Calculate slot index based on row
        if row == 0:  # Row A: slots 0-6
            slot_index = col
        elif row == 1:  # Row B: slots 7-13
            slot_index = 7 + col
        elif row == 2:  # Row C: slots 14-17
            slot_index = 14 + col
        else:
            return None
        
        if str(slot_index) in self.deck.slots:
            slot = self.deck.slots[str(slot_index)]
            if slot.has_labware and hasattr(slot.labware, 'wells'):
                # Get the first (and only) well from the labware
                for well in slot.labware.wells.values():
                    if isinstance(well, WeightWell):
                        return well
        return None
        
    def connect(self, machine_address: str = None, scale_port: str = "/dev/ttyUSB0"):
        """Connect to Jubilee machine and scale"""
        try:
            # Use config IP if no address provided
            if machine_address is None:
                machine_address = config.get_duet_ip()
            
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
    
    @requires_safe_z_machine
    @requires_well_validation
    def dispense_to_well(self, well_id: str, target_weight: float) -> bool:
        """Dispense powder to a specific well"""
        if not self.connected or not self.trickler:
            return False
        
        try:

            if not self.manipulator:
                raise ToolStateError("Manipulator is not connected or provided.")
            
            if not self.scale or not self.scale.is_connected:
                raise ToolStateError("Scale is not connected or provided.")
            
            # Get the well from the deck
            well = self._get_well_from_deck(well_id)
            if not well:
                raise ToolStateError(f"Well {well_id} not found in deck.")
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
            self.get_piston_from_dispenser(dispenser_index, well_id)
            self._move_to_well(well_id)
            self.manipulator.place_well()
            return True
        except Exception as e:
            print(f"Dispensing error: {e}")
            return False

    @requires_safe_z_machine
    def get_piston_from_dispenser(self, dispenser_index: int, well_id: str):
        """Get the top piston from a specific dispenser"""
        if not self.connected or not self.piston_dispensers:
            return False
        if self.manipulator.current_well is None:
            raise ToolStateError("No mold to place piston into.")
        
        try:
            x = self.piston_dispensers[dispenser_index].x
            y = self.piston_dispensers[dispenser_index].y

            self.machine.move(z=config.get_safe_z())  # Use safe Z height from config
            self.machine.move_to(x=x, y=y)
            self.manipulator.place_top_piston(self.machine, self.piston_dispensers[dispenser_index])
            self.piston_dispensers[dispenser_index].remove_piston()
            # Get the well from deck and set piston
            well = self._get_well_from_deck(well_id)
            if well:
                well.set_piston(True)
            return True
        except Exception as e:
            print(f"Getting piston from dispenser error: {e}")
            return False

    @requires_safe_z_machine
    @requires_well_validation
    def _move_to_well(self, well_id: str):
        """Move to a specific well"""
        if not self.connected or not self.deck:
            return False
        
        try:
            well = self._get_well_from_deck(well_id)
            if not well or not well.valid:
                raise ToolStateError("Well is not valid.")
            self.machine.safe_z_movement()
            self.machine.move_to(x=well.x, y=well.y)
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
