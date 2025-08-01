"""
Basic Scale Test Script
This script connects to a scale and measures the weight of an object.
"""

import time
from Scale import Scale
import serial

def main():
    ser = serial.Serial('/dev/serial1337', 2400, timeout=1)
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


    # port = input("Enter the serial port for the scale (e.g., COM3 or /dev/ttyUSB0): ")
    # scale = Scale(port)
    # try:
    #     scale.connect()
    #     print("\nPlace the empty container on the scale and press Enter...")
    #     input()
    #     print("Taring the scale...")
    #     scale.tare()
    #     print("Tare complete. Remove your hands and wait for the scale to stabilize.")
    #     time.sleep(2)
    #     print("\nPlace the object to be weighed in the container and press Enter...")
    #     input()
    #     print("Measuring weight...")
    #     weight = scale.get_weight(stable=True)
    #     print(f"Measured weight: {weight:.4f} g")
    # except Exception as e:
    #     print(f"Error: {e}")
    # finally:
    #     scale.disconnect()

if __name__ == "__main__":
    main()
