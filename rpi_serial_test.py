import serial

def main():
   test_string = b"Loopback Test!"
   port = "/dev/ttyS0"  # Use /dev/ttyAMA0 if appropriate for your Pi version

   ser = serial.Serial(port, 9600, timeout=2)
   ser.write(test_string)
   echo = ser.read(len(test_string))
   print("Received:", echo)
   if echo == test_string:
      print("Serial loopback OK!")
   else:
      print("Serial loopback FAILED!")
   ser.close()

if __name__ == "__main__":
   main()
   