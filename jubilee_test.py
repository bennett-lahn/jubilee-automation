"""
Basic Jubilee Test Script
This script homes the Jubilee motion platform and moves it in a circle twice.
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
        
        # Circle parameters
        num_points = 50  # Number of points to approximate the circle
        theta_step = 2 * math.pi / num_points  # Angle step between points
        
        print("Starting circular motion...")
        
        # Perform two complete circles
        for circle_num in range(2):
            print(f"Circle {circle_num + 1}/2")
            
            theta = 0
            for point in range(num_points + 1):  # +1 to complete the circle
                # Calculate x, y coordinates on the circle
                x = center_x + radius * math.cos(theta)
                y = center_y + radius * math.sin(theta)
                
                # Move to the calculated position
                machine.move_to(x=x, y=y, z=safe_z, s=3000)  # s=3000 is speed in mm/min
                
                # Increment angle for next point
                theta += theta_step
                
                # Small delay to make motion visible
                time.sleep(0.1)
            
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
