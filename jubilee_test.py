"""
Basic Jubilee Test Script
This script homes the Jubilee motion platform and moves it in a circle twice using G28 arc commands.
"""

import math
import time
from science_jubilee.Machine import Machine

def main():
    # Initialize the Machine
    # Note: May need to adjust the address parameter based on Jubilee's IP
    print("Initializing Jubilee machine...")
    machine = Machine(address="192.168.1.2")  # Default Jubilee IP
    
    try:
        machine.connect()
        # Home all axes
        print("Homing all axes...")
        machine.home_all()
        print("Homing complete!")
        
        # Wait a moment for homing to complete
        while not all(machine.axes_homed.values()):
            time.sleep(1)
        
        # Move to starting position (center of work area)
        center_x = 150  # mm (adjust based on your bed size)
        center_y = 150  # mm (adjust based on your bed size)
        safe_z = 50    # mm (safe height above bed)
        radius = 30    # mm (circle radius)
        
        print(f"Moving to starting position: X={center_x}, Y={center_y}")
        machine.safe_z_movement()
        machine.move_to(x=center_x, y=center_y)
        
        # Calculate starting point on the circle (at 0 degrees)
        start_x = center_x + radius
        start_y = center_y
        
        print("Starting circular motion using G28 arc commands...")
        
        # Perform two complete circles using G28 arc commands
        for circle_num in range(2):
            print(f"Circle {circle_num + 1}/2")
            
            # Move to starting point of the circle
            machine.move_to(x=start_x, y=start_y, z=safe_z)
            
            # G28 command for full circle: G28 X<center_x> Y<center_y> I<radius> J0
            # This creates a full circle centered at (center_x, center_y) with radius
            gcode_command = f"G28 X{center_x} Y{center_y} I{radius} J0 F3000"
            print(f"Executing: {gcode_command}")
            machine.gcode(gcode_command)
            
            print(f"Circle {circle_num + 1} completed!")
            time.sleep(1)  # Pause between circles
        
        # Return to center position
        print("Returning to center position...")
        machine.move_to(x=center_x, y=center_y, z=safe_z)
        
        print("Motion sequence completed successfully!")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        print("Make sure your Jubilee is connected and properly configured.")
        
    finally:
        # Clean disconnect
        print("Disconnecting from machine...")
        machine.disconnect()

if __name__ == "__main__":
    main()
