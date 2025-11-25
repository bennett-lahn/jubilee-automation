"""
MotionPlatformExecutor - Low-level movement execution for validated state machine moves.

This module contains all the physical movement execution logic for the Jubilee
motion platform. All methods assume validation has already occurred in the
MotionPlatformStateMachine. 

The executor is owned by the state machine and is not accessed directly by other
components, so all movements go through validation.
"""
from typing import Optional
from science_jubilee.Machine import Machine
from Scale import Scale
from PistonDispenser import PistonDispenser
from trickler_labware import WeightWell
from MotionPlatformStateMachine import PositionType


class MovementExecutor:
    """
    Executes physical movements on the machine after state machine validation.
    
    This class should not be instantiated directly by user code. Instead, it is
    owned by MotionPlatformStateMachine and accessed through validated methods.
    """
    
    def __init__(self, machine: Machine, scale: Optional[Scale] = None):
        """
        Initialize the movement executor with a machine reference.
        
        Args:
            machine: The Jubilee Machine instance to control
            scale: Optional Scale instance (reference to JubileeManager's scale)
        """
        self._machine = machine
        self._scale = scale
    
    @property
    def machine(self) -> Machine:
        """
        Read-only access to machine for state queries only. 
        Queries should not modify platform state.
        """
        return self._machine
    
    # ===== MANIPULATOR MOVEMENTS =====
    
    def execute_pick_mold_from_well(
        self,
        well_id: str,
        deck,
        tamper_axis: str = 'V',
        tamper_travel_pos: float = 30.0,
        safe_z: float = 195.0
    ) -> None:
        """
        Execute the physical movements to pick up a mold from a well.
        
        Assumes the toolhead is above the chosen well at safe_z height
        with tamper axis in travel position.
        
        Args:
            well_id: Well identifier (e.g., "A1")
            deck: The Deck object with well configuration
            tamper_axis: Axis letter for tamper (default 'V')
            tamper_travel_pos: Travel position for tamper axis (default 30.0 mm)
            safe_z: Safe Z height (default 195.0 mm)
        """
        # Get well from deck for logging
        well = None
        try:
            # Convert well_id to slot index
            row = ord(well_id[0].upper()) - ord('A')
            col = int(well_id[1:]) - 1
            
            if row == 0:  # Row A: slots 0-6
                slot_index = col
            elif row == 1:  # Row B: slots 7-13
                slot_index = 7 + col
            elif row == 2:  # Row C: slots 14-17
                slot_index = 14 + col
            else:
                slot_index = None
            
            if slot_index is not None and str(slot_index) in deck.slots:
                slot = deck.slots[str(slot_index)]
                if slot.has_labware and hasattr(slot.labware, 'wells'):
                    for w in slot.labware.wells.values():
                        well = w
                        break
        except Exception:
            pass
        
        well_name = well.name if (well and hasattr(well, 'name')) else well_id
        print(f"Picking up mold: {well_name}")
        
        self._machine._set_absolute_positioning()
        self._machine.move(z=148, s=500)  # Move until tamper leadscrew almost grounded
        self._machine._set_relative_positioning()
        self._machine.move(y=-25.5, s=500)  # Move to the side of the mold
        self._machine.move_to(v=50, s=50)  # Move mold holder down
        self._machine._set_relative_positioning()
        self._machine.move(y=25.5, s=500)  # Move back under mold
        self._machine.move_to(v=tamper_travel_pos, s=50)  # Pick up mold and move to travel position
        self._machine.safe_z_movement()  # Move back to safe z
    
    def execute_place_mold_in_well(
        self,
        well_id: str,
        deck,
        tamper_axis: str = 'V',
        tamper_travel_pos: float = 30.0,
        safe_z: float = 195.0
    ) -> None:
        """
        Execute the physical movements to place a mold in a well.
        
        Args:
            well_id: Well identifier (e.g., "A1")
            deck: The Deck object with well configuration
            tamper_axis: Axis letter for tamper (default 'V')
            tamper_travel_pos: Travel position for tamper axis (default 30.0 mm)
            safe_z: Safe Z height (default 195.0 mm)
        """
        # Get well from deck for logging
        well = None
        try:
            # Convert well_id to slot index
            row = ord(well_id[0].upper()) - ord('A')
            col = int(well_id[1:]) - 1
            
            if row == 0:  # Row A: slots 0-6
                slot_index = col
            elif row == 1:  # Row B: slots 7-13
                slot_index = 7 + col
            elif row == 2:  # Row C: slots 14-17
                slot_index = 14 + col
            else:
                slot_index = None
            
            if slot_index is not None and str(slot_index) in deck.slots:
                slot = deck.slots[str(slot_index)]
                if slot.has_labware and hasattr(slot.labware, 'wells'):
                    for w in slot.labware.wells.values():
                        well = w
                        break
        except Exception:
            pass
        
        well_name = well.name if (well and hasattr(well, 'name')) else well_id
        print(f"Placing mold: {well_name}")
        
        self._machine._set_absolute_positioning()
        self._machine.move(z=148, s=500)  # Move until tamper leadscrew almost grounded
        self._machine.move_to(v=50, s=50)  # Put down mold holder
        self._machine._set_relative_positioning()
        self._machine.move(y=-25.5, s=500)  # Move out from under mold
        self._machine.move_to(v=tamper_travel_pos, s=50)  # Move into tamper travel position
        self._machine.safe_z_movement()  # Move back to safe z
    
    def execute_place_mold_on_scale(
        self,
        tamper_axis: str = 'V',
        tamper_travel_pos: float = 30.0
    ) -> None:
        """
        Execute movements to place mold on scale.
        
        Assumes the gantry has been moved to a known location in front of and
        above the cap dispenser.
        
        Args:
            tamper_axis: Axis letter for tamper (default 'V')
            tamper_travel_pos: Travel position for tamper axis (default 30.0 mm)
        """
        if self._scale is None:
            raise RuntimeError("Scale not configured in MovementExecutor")
        
        print("Placing mold on scale")
        
        self._machine._set_absolute_positioning()
        self._machine.move_to(z=134, s=500)  # Move to 5mm above scale
        self._machine.move_to(v=38.5, s=50)  # Move well to fit under trickler
        self._machine.move(y=184, s=500)  # Move well under trickler
        self._machine.move_to(v=45, s=50)  # Place well on scale
    
    def execute_pick_mold_from_scale(
        self,
        tamper_axis: str = 'V',
        tamper_travel_pos: float = 30.0
    ) -> None:
        """
        Execute movements to pick mold from scale.
        
        Only call if a mold has been placed under the trickler.
        
        Args:
            tamper_axis: Axis letter for tamper (default 'V')
            tamper_travel_pos: Travel position for tamper axis (default 30.0 mm)
        """
        if self._scale is None:
            raise RuntimeError("Scale not configured in MovementExecutor")
        
        print("Picking mold from scale")
        
        self._machine._set_absolute_positioning()
        self._machine.move_to(v=38.5, s=50)  # Pick up mold
        self._machine.move(y=self._scale.y, s=500)  # Move from under trickler
        self._machine.safe_z_movement()  # Move to safe z
        self._machine.move_to(v=tamper_travel_pos, s=50)  # Move to travel position
    
    def execute_place_top_piston(
        self,
        piston_dispenser: PistonDispenser,
        tamper_axis: str = 'V',
        tamper_travel_pos: float = 30.0,
        dispenser_safe_z: float = 254.0
    ) -> None:
        """
        Execute movements to place top piston on current mold.
        
        Args:
            piston_dispenser: The PistonDispenser with position and piston info
            tamper_axis: Axis letter for tamper (default 'V')
            tamper_travel_pos: Travel position for tamper axis (default 30.0 mm)
            dispenser_safe_z: Safe Z height for dispenser (default 254.0 mm)
        """
        print(f"Placing top piston from dispenser {piston_dispenser.index}")
        
        self._machine._set_absolute_positioning()
        self._machine.move_to(v=52, s=50)  # Fully lower mold
        self._machine.move(z=189, s=500)  # Move so mold fits under cap
        self._machine._set_relative_positioning()
        self._machine.move(y=35, s=500)  # Move under cap dispenser
        self._machine.move_to(v=37.3, s=50)  # Move to pick up cap
        self._machine.move(x=piston_dispenser.x, y=piston_dispenser.y, s=500)  # Return to start
        self._machine.move_to(v=tamper_travel_pos, s=50)  # Move to travel position
    
    def execute_tamp(
        self,
        tamper_axis: str = 'V'
    ) -> None:
        """
        Execute tamping movements.
        
        Args:
            tamper_axis: Axis letter for tamper (default 'V')
        """
        if self._scale is None:
            raise RuntimeError("Scale not configured in MovementExecutor")
        
        print("Executing tamp")
        
        self._machine._set_absolute_positioning()
        self._machine.move_to(v=38.5, s=50)  # Prepare for tamp
        self._machine.move(y=self._scale.y, s=50)  # Move from under trickler
        self._machine.move_to(v=0, s=50)  # Move until stall detection stops movement
    
    # ===== BASIC MOVEMENTS =====
    
    def execute_move_to_position(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        v: Optional[float] = None,
        speed: int = 500
    ) -> None:
        """
        Execute a basic move to specified coordinates.
        
        Args:
            x: X coordinate (None to skip)
            y: Y coordinate (None to skip)
            z: Z coordinate (None to skip)
            v: V/manipulator coordinate (None to skip)
            speed: Movement speed in mm/min (default 500)
        """
        self._machine.move_to(x=x, y=y, z=z, v=v, s=speed)
    
    def execute_safe_z_movement(self) -> None:
        """Move to safe Z height."""
        self._machine.safe_z_movement()
    
    def execute_home_all(self, registry) -> None:
        """Home all axes and return to global_ready position."""
        self._machine.home_all()
        # After homing, move to global_ready position
        global_ready_pos = registry.find_first_of_type(PositionType.GLOBAL_READY)
        if global_ready_pos and global_ready_pos.coordinates:
            coords = global_ready_pos.coordinates
            # Get z height from z_heights if needed
            z_height = None
            if coords.z == "USE_Z_HEIGHT_POLICY":
                # Use mold_transfer_safe z height
                z_heights = registry.z_heights
                if "mold_transfer_safe" in z_heights:
                    z_config = z_heights["mold_transfer_safe"]
                    if isinstance(z_config, dict):
                        z_height = z_config.get("z_coordinate")
            
            # Move to global_ready coordinates
            # Skip placeholders - they'll be handled by the state machine
            x = coords.x if (coords.x is not None and (not isinstance(coords.x, str) or not coords.x.startswith("PLACEHOLDER"))) else None
            y = coords.y if (coords.y is not None and (not isinstance(coords.y, str) or not coords.y.startswith("PLACEHOLDER"))) else None
            z = z_height if (z_height is not None and (not isinstance(z_height, str) or not z_height.startswith("PLACEHOLDER"))) else None
            v = coords.v if (coords.v is not None and (not isinstance(coords.v, str) or not coords.v.startswith("PLACEHOLDER"))) else None
            
            if x is not None or y is not None or z is not None or v is not None:
                self._machine.move_to(x=x, y=y, z=z, v=v)
    
    def execute_pickup_tool(
        self,
        tool,
        registry
    ) -> bool:
        """
        Pick up a tool and move to global_ready position.
        
        Note: The machine's pickup_tool() method is decorated with @requires_safe_z,
        which automatically raises the bed height to deck.safe_z + 20 if it is not
        already at that height.
        
        Args:
            tool: The Tool object to pick up (must be manipulator for now)
            registry: PositionRegistry to get global_ready coordinates
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate that only manipulator tool is supported
            if not hasattr(tool, 'name') or tool.name != "manipulator":
                raise ValueError(f"Only manipulator tool is supported. Attempted to pick up: {tool.name if hasattr(tool, 'name') else type(tool).__name__}")
            
            # Pick up the tool
            self._machine.pickup_tool(tool)
            
            # Move to global_ready position
            global_ready_pos = registry.find_first_of_type(PositionType.GLOBAL_READY)
            if global_ready_pos and global_ready_pos.coordinates:
                coords = global_ready_pos.coordinates
                # Get z height from z_heights if needed
                z_height = None
                if coords.z == "USE_Z_HEIGHT_POLICY":
                    # Use mold_transfer_safe z height
                    z_heights = registry.z_heights
                    if "mold_transfer_safe" in z_heights:
                        z_config = z_heights["mold_transfer_safe"]
                        if isinstance(z_config, dict):
                            z_height = z_config.get("z_coordinate")
                
                # Move to global_ready coordinates
                # Skip placeholders - they'll be handled by the state machine
                x = coords.x if (coords.x is not None and (not isinstance(coords.x, str) or not coords.x.startswith("PLACEHOLDER"))) else None
                y = coords.y if (coords.y is not None and (not isinstance(coords.y, str) or not coords.y.startswith("PLACEHOLDER"))) else None
                z = z_height if (z_height is not None and (not isinstance(z_height, str) or not z_height.startswith("PLACEHOLDER"))) else None
                v = coords.v if (coords.v is not None and (not isinstance(coords.v, str) or not coords.v.startswith("PLACEHOLDER"))) else None
                
                if x is not None or y is not None or z is not None or v is not None:
                    self._machine.move_to(x=x, y=y, z=z, v=v)
            
            return True
        except Exception as e:
            print(f"Error picking up tool: {e}")
            return False
    
    def execute_park_tool(
        self,
        registry
    ) -> bool:
        """
        Park the current tool and move to global_ready position.
        
        Note: The machine's park_tool() method is decorated with @requires_safe_z,
        which automatically raises the bed height to deck.safe_z + 20 if it is not
        already at that height. 
        
        Args:
            registry: PositionRegistry to get global_ready coordinates
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Park the tool
            self._machine.park_tool()
            
            # Move to global_ready position
            global_ready_pos = registry.find_first_of_type(PositionType.GLOBAL_READY)
            if global_ready_pos and global_ready_pos.coordinates:
                coords = global_ready_pos.coordinates
                # Get z height from z_heights if needed
                z_height = None
                if coords.z == "USE_Z_HEIGHT_POLICY":
                    # Use mold_transfer_safe z height
                    z_heights = registry.z_heights
                    if "mold_transfer_safe" in z_heights:
                        z_config = z_heights["mold_transfer_safe"]
                        if isinstance(z_config, dict):
                            z_height = z_config.get("z_coordinate")
                
                # Move to global_ready coordinates
                # Skip placeholders - they'll be handled by the state machine
                x = coords.x if (coords.x is not None and (not isinstance(coords.x, str) or not coords.x.startswith("PLACEHOLDER"))) else None
                y = coords.y if (coords.y is not None and (not isinstance(coords.y, str) or not coords.y.startswith("PLACEHOLDER"))) else None
                z = z_height if (z_height is not None and (not isinstance(z_height, str) or not z_height.startswith("PLACEHOLDER"))) else None
                v = coords.v if (coords.v is not None and (not isinstance(coords.v, str) or not coords.v.startswith("PLACEHOLDER"))) else None
                
                if x is not None or y is not None or z is not None or v is not None:
                    self._machine.move_to(x=x, y=y, z=z, v=v)
            
            return True
        except Exception as e:
            print(f"Error parking tool: {e}")
            return False
    
    def execute_home_xyz(self) -> None:
        """Home X, Y, Z axes."""
        self._machine.home_xyu()
        self._machine.home_z()
    
    def execute_move_to_well(
        self,
        well: WeightWell
    ) -> None:
        """
        Execute movement to a specific well location.
        
        Args:
            well: The WeightWell to move to
        """
        self._machine.safe_z_movement()
        self._machine.move_to(x=well.x, y=well.y)
    
    def execute_move_to_scale(
        self
    ) -> None:
        """
        Execute movement to the scale location.
        """
        if self._scale is None:
            raise RuntimeError("Scale not configured in MovementExecutor")
        
        self._machine.safe_z_movement()
        self._machine.move_to(x=self._scale.x, y=self._scale.y)
    
    def get_machine_position(self) -> dict:
        """Get current machine position."""
        return self._machine.get_position()
    
    def get_machine_axes_homed(self) -> list:
        """Get list of which axes are homed."""
        return getattr(self._machine, 'axes_homed', [False, False, False, False])
        
    def execute_move_to_well_by_id(
        self,
        well_id: str,
        deck
    ) -> bool:
        """
        Move to a specific well by well ID.
        
        Moved from JubileeManager._move_to_well()
        
        Args:
            well_id: Well identifier (e.g., "A1")
            deck: The Deck object with well configuration (from state machine's context)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get well from deck
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
                return False
            
            if str(slot_index) not in deck.slots:
                return False
            
            slot = deck.slots[str(slot_index)]
            if not slot.has_labware or not hasattr(slot.labware, 'wells'):
                return False
            
            # Get the well
            well = None
            for w in slot.labware.wells.values():
                well = w
                break
            
            if not well or not well.valid:
                return False
            
            self._machine.safe_z_movement()
            self._machine.move_to(x=well.x, y=well.y)
            return True
        except Exception as e:
            print(f"Error moving to well: {e}")
            return False
    
    def execute_move_to_scale_location(
        self
    ) -> bool:
        """
        Move to the scale location.
        
        Moved from JubileeManager._move_to_scale()
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if self._scale is None:
                raise RuntimeError("Scale not configured in MovementExecutor")
            
            self._machine.safe_z_movement()
            self._machine.move_to(x=self._scale.x, y=self._scale.y)
            # TODO: Figure out appropriate z offset from scale location to move to
            return True
        except Exception as e:
            print(f"Error moving to scale: {e}")
            return False
    
    def execute_dispense_powder(
        self,
        target_weight: float
    ) -> bool:
        """
        Dispense powder to the scale.
        
        Moved from JubileeManager._dispense_powder()
        
        Args:
            target_weight: Target weight to dispense
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # TODO: Implement powder dispensing logic
            # This is a placeholder for the actual dispensing implementation
            return True
        except Exception as e:
            print(f"Error dispensing powder: {e}")
            return False
        
    def execute_home_tamper(
        self,
        tamper_axis: str = 'V'
    ) -> None:
        """
        Perform sensorless homing for the tamper axis.
        
        Moved from Manipulator.home_tamper()
        
        Args:
            tamper_axis: Axis letter for tamper (default 'V')
            
        Raises:
            RuntimeError: If axes are not properly homed before attempting tamper homing
        """
        # Check if axes are homed
        axes_homed = getattr(self._machine, 'axes_homed', [False, False, False, False])
        axis_names = ['X', 'Y', 'Z', 'U']
        not_homed = [axis_names[i] for i in range(4) if not axes_homed[i]]
        
        if not_homed:
            print(f"Axes not homed: {', '.join(not_homed)}")
            raise RuntimeError(
                f"X, Y, Z, and U axes must be homed before homing the tamper "
                f"({tamper_axis}) axis."
            )
        
        # Perform homing for tamper axis
        self._machine.send_command(f'M98 P"home{tamper_axis.lower()}.g"')
        
        print(f"Homing complete. {tamper_axis} axis position reset to 0.0mm")
    
    def execute_home_manipulator(
        self,
        manipulator_axis: str = 'V'
    ) -> bool:
        """
        Home the manipulator axis (V).
        
        Args:
            manipulator_axis: Axis letter for manipulator (default 'V')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Perform homing for manipulator axis
            self._machine.send_command(f'M98 P"home{manipulator_axis.lower()}.g"')
            print(f"Manipulator ({manipulator_axis}) homing complete. Position reset to 0.0mm")
            return True
        except Exception as e:
            print(f"Error homing manipulator: {e}")
            return False
    
    def execute_home_trickler(
        self,
        trickler_axis: str = 'W'
    ) -> bool:
        """
        Home the trickler axis (W).
        
        Args:
            trickler_axis: Axis letter for trickler (default 'W')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Trickler can be homed at any time, no prerequisites
            self._machine.send_command(f'M98 P"home{trickler_axis.lower()}.g"')
            print(f"Trickler ({trickler_axis}) homing complete. Position reset to 0.0mm")
            return True
        except Exception as e:
            print(f"Error homing trickler: {e}")
            return False

