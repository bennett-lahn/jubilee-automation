"""
Basic Scale Test Script
This script connects to a scale and measures the weight of an object.
"""

import time
from Scale import Scale
import serial

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
        scale.tare()
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

def main():
    port = input("Enter the serial port for the scale (e.g., COM3 or /dev/ or /dev/serial0): ")
    print("Select mode:")
    print("1. Listener mode (raw serial output)")
    print("2. Scale test mode (tare and weigh)")
    mode = input("Enter 1 or 2: ").strip()
    if mode == "1":
        listener_mode(port)
    elif mode == "2":
        scale_test_mode(port)
    else:
        print("Invalid selection.")

if __name__ == "__main__":
    main()
