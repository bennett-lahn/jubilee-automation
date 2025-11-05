"""
Basic Scale Test Script
This script connects to a scale and measures the weight of an object.
"""

import time
from Scale import Scale
import serial
from science_jubilee.Machine import Machine
import matplotlib.pyplot as plt
import numpy as np

def listener_mode(port):
    ser = serial.Serial(port, 2400, timeout=1)
    ser.reset_input_buffer()
    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('ascii', errors='ignore').rstrip()
                print(f"Received: {line}")
    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        ser.close()

def scale_test_mode(port):
    scale = Scale(port)
    try:
        scale.connect()
        print("\nPlace the empty container on the scale and press Enter...")
        input()
        print("Taring the scale...")
        # scale.tare()
        print("Tare complete. Remove your hands and wait for the scale to stabilize.")
        time.sleep(2)
        print("\nPlace the object to be weighed in the container and press Enter...")
        input()
        print("Measuring weight...")
        weight = scale.get_weight(stable=True)
        print(f"Measured weight: {weight:.4f} g")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        scale.disconnect()

def continuous_weight_mode(port):
    scale = Scale(port)
    try:
        scale.connect()
        # print("\nPlace the empty container on the scale and press Enter...")
        # input()
        # print("Taring the scale...")
        # scale.tare()
        # print("Tare complete.")
        print("Starting continuous weight monitoring...")
        print("Press Ctrl+C to stop.\n")
        time.sleep(1)
        
        # Continuously read weight
        while True:
            try:
                weight = scale.get_weight(stable=False)
                print(f"\rCurrent weight: {weight:>10.4f} g", end='', flush=True)
                time.sleep(0.1)  # Update 10 times per second
            except KeyboardInterrupt:
                print("\n\nStopping continuous monitoring...")
                break
            except Exception as e:
                print(f"\nError reading weight: {e}")
                time.sleep(0.5)
                
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        scale.disconnect()

def movement_repeatability_test(port, machine_address="192.168.1.2", iterations=100):
    """Test movement repeatability by moving V axis and measuring weight changes"""
    scale = None
    machine = None
    weights = []
    
    try:
        print("Connecting to scale...")
        scale = Scale(port)
        scale.connect()
        print("Scale connected!")
        
        print("Connecting to Jubilee...")
        machine = Machine(address=machine_address)
        machine.connect()
        print("Jubilee connected!")
        
        print("\nPlace container on scale and press Enter...")
        input()
        print("Taring scale...")
        scale.tare()
        time.sleep(2)
        
        print("\nInitializing coordinate system...")
        # Set current position as origin
        machine.gcode("G92 X0 Y0 Z0 U0 V0")
        # Set to relative positioning
        machine.gcode("G91")
        time.sleep(0.5)
        
        print(f"\nStarting {iterations} movement cycles...")
        print("This will move V axis by 0.1mm each iteration and record weight.\n")
        
        for i in range(iterations):
            # Move V axis by 0.1mm
            machine.gcode("G1 V0.1")
            time.sleep(2)  # Wait for movement to complete and settle
            
            # Take weight reading
            try:
                weight = scale.get_weight(stable=True)
                weights.append(weight)
                print(f"Iteration {i+1}/{iterations}: Position V={0.1*(i+1):.1f}mm, Weight={weight:.4f}g")
            except Exception as e:
                print(f"Error reading weight at iteration {i+1}: {e}")
                weights.append(np.nan)  # Add NaN for failed readings
        
        print("\n" + "="*60)
        print("Movement Repeatability Test Complete")
        print("="*60)
        
        # Filter out NaN values for statistics
        valid_weights = [w for w in weights if not np.isnan(w)]
        
        if len(valid_weights) < 2:
            print("Insufficient valid weight readings for analysis.")
            return
        
        # Calculate differences between consecutive readings
        differences = []
        for i in range(1, len(valid_weights)):
            diff = valid_weights[i] - valid_weights[i-1]
            differences.append(diff)
        
        # Calculate statistics
        avg_difference = np.mean(differences)
        std_difference = np.std(differences)
        max_difference = np.max(np.abs(differences))
        
        print(f"\nWeight Statistics:")
        print(f"  Total readings: {len(weights)}")
        print(f"  Valid readings: {len(valid_weights)}")
        print(f"  Initial weight: {valid_weights[0]:.4f} g")
        print(f"  Final weight: {valid_weights[-1]:.4f} g")
        print(f"  Total weight change: {valid_weights[-1] - valid_weights[0]:.4f} g")
        
        print(f"\nMovement Impact Analysis:")
        print(f"  Average weight change per movement: {avg_difference:.6f} g")
        print(f"  Std deviation of changes: {std_difference:.6f} g")
        print(f"  Maximum single change: {max_difference:.6f} g")
        
        # Create graphs
        print("\nGenerating graphs...")
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # Graph 1: Weight over iterations
        ax1.plot(range(1, len(valid_weights)+1), valid_weights, 'b-o', markersize=3)
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Weight (g)')
        ax1.set_title('Weight Measurements vs Movement Iterations')
        ax1.grid(True, alpha=0.3)
        ax1.axhline(y=valid_weights[0], color='r', linestyle='--', label=f'Initial: {valid_weights[0]:.4f}g')
        ax1.legend()
        
        # Graph 2: Weight differences between consecutive readings
        ax2.plot(range(1, len(differences)+1), differences, 'g-o', markersize=3)
        ax2.axhline(y=avg_difference, color='r', linestyle='--', 
                    label=f'Average: {avg_difference:.6f}g')
        ax2.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        ax2.set_xlabel('Movement Number')
        ax2.set_ylabel('Weight Change (g)')
        ax2.set_title('Weight Change Between Consecutive Movements')
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        
        plt.tight_layout()
        
        # Save the figure
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"movement_repeatability_{timestamp}.png"
        plt.savefig(filename, dpi=150)
        print(f"Graph saved as: {filename}")
        
        # Show the plot
        plt.show()
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Return to absolute positioning and disconnect
        if machine:
            try:
                machine.gcode("G90")
            except:
                pass
            try:
                machine.disconnect()
            except:
                pass
        
        if scale:
            try:
                scale.disconnect()
            except:
                pass

def main():
    port = input("Enter the serial port for the scale (default: /dev/ttyUSB0): ").strip()
    if not port:
        port = "/dev/ttyUSB0"
        print(f"Using default port: {port}")
    print("Select mode:")
    print("1. Listener mode (raw serial output)")
    print("2. Scale test mode (tare and weigh once)")
    print("3. Continuous weight mode (tare and continuous monitoring)")
    print("4. Movement repeatability test (Jubilee + scale)")
    mode = input("Enter 1, 2, 3, or 4: ").strip()
    if mode == "1":
        listener_mode(port)
    elif mode == "2":
        scale_test_mode(port)
    elif mode == "3":
        continuous_weight_mode(port)
    elif mode == "4":
        machine_address = input("Enter Jubilee IP address (default: 192.168.1.2): ").strip()
        if not machine_address:
            machine_address = "192.168.1.2"
        iterations_str = input("Enter number of iterations (default: 100): ").strip()
        iterations = int(iterations_str) if iterations_str else 100
        movement_repeatability_test(port, machine_address, iterations)
    else:
        print("Invalid selection.")

if __name__ == "__main__":
    main()
