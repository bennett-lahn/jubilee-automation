import time
import serial
from enum import Enum

MAX_WEIGHT = 10 # Immediately throw error if measured weight after taring exceeds this value; container may be overloaded

CR = '\r'
LF = '\n'
CRLF = CR + LF
ACK = b'\x06'  # ASCII 06h

# Commands that expect ACK responses
ACK_COMMANDS = {
    'C': False,      # Cancel - no ACK
    'Q': False,      # Query weight - no ACK, returns data
    'S': False,      # Stable weight - no ACK, returns data
    'SI': False,     # Instant weight - no ACK, returns data
    'SIR': False,    # Continuous weight - no ACK, returns data
    '\x1bP': False,  # ESC+P - no ACK, returns data
    'CAL': True,     # Calibrate - sends ACK when received, then ACK when executed
    'EXC': True,     # External calibration - sends ACK
    'OFF': True,     # Display off - sends ACK
    'ON': True,      # Display on - sends ACK when received, then ACK when executed
    'PRT': False,    # Print weight - no ACK, returns data
    'R': True,       # Re-zero - sends ACK when received, then ACK when executed
    'SMP': True,     # Sample - sends ACK
    'T': True,       # Tare - sends ACK when received, then ACK when executed
    'U': True,       # Mode change - sends ACK
    '?ID': False,    # Get ID - no ACK, returns data
    '?SN': False,    # Get serial number - no ACK, returns data
    '?TN': False,    # Get model - no ACK, returns data
    '?PT': False,    # Get tare weight - no ACK, returns data
    'PT:': True,     # Set tare weight - sends ACK
}

# Commands that send two ACKs (one when received, one when executed)
DUAL_ACK_COMMANDS = {'CAL', 'ON', 'P', 'R', 'Z', 'T'}

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
ACK_TIMEOUT = 5.0  # seconds for dual ACK commands

class ScaleError(Enum):
    E00 = 'E00'  # Communications error
    E01 = 'E01'  # Undefined command error
    E02 = 'E02'  # Not ready
    E03 = 'E03'  # Timeout error
    E04 = 'E04'  # Excess characters error
    E06 = 'E06'  # Format error
    E07 = 'E07'  # Parameter setting error
    E11 = 'E11'  # Stability error
    E17 = 'E17'  # Out of range error
    E20 = 'E20'  # Internal mass error (FZ-i only)
    E21 = 'E21'  # Calibration weight error (too light)
    OVERLOAD = 'OVERLOAD'  # Overload state
    BAD_UNIT = 'BAD_UNIT'  # Incorrect weighing unit
    BAD_HEADER = 'BAD_HEADER'  # Unexpected header for command
    MAX_WEIGHT = 'MAX_WEIGHT'  # Maximum weight exceeded
    ACK_TIMEOUT = 'ACK_TIMEOUT'  # ACK timeout error
    COMMAND_FAILED = 'COMMAND_FAILED'  # Command failed after retries
    # ... add more as needed

    @property
    def desc(self):
        return {
            # TODO: Add appropriate response to errors other than hard fail
            ScaleError.E00: "Communications error: A protocol error occurred in communications. Confirm the format, baud rate and parity.",
            ScaleError.E01: "Undefined command error: An undefined command was received. Confirm the command.",
            ScaleError.E02: "Not ready: A received command cannot be processed. (e.g., not in weighing mode or busy)",
            ScaleError.E03: "Timeout error: The balance did not receive the next character of a command within the time limit (probably 1 second).",
            ScaleError.E04: "Excess characters error: The balance received excessive characters in a command.",
            ScaleError.E06: "Format error: A command includes incorrect data (e.g., numerically incorrect).",
            ScaleError.E07: "Parameter setting error: The received data exceeds the range that the balance can accept.",
            ScaleError.E11: "Stability error: The balance cannot stabilize due to an environmental problem (vibration, drafts, etc).", # For this error, press CAL to return to weighing
            ScaleError.E17: "Out of range error: The value entered is beyond the settable range.",
            ScaleError.E20: "Calibration weight error: The calibration weight is too heavy. Confirm that the weighing pan is properly installed. Confirm the calibration weight value.",
            ScaleError.E21: "Calibration weight error: The calibration weight is too light. Confirm that the weighing pan is properly installed. Confirm the calibration weight value.",
            ScaleError.OVERLOAD: "Overload error: The scale is in overload state (OL). Remove the sample from the pan.",
            ScaleError.BAD_UNIT: "Weighing unit incorrect: The unit is not '  g' (grams) as expected. Check the unit on the scale display.",
            ScaleError.BAD_HEADER: "Unexpected header: The header is not appropriate for the command context.",
            ScaleError.MAX_WEIGHT: "Max weight exceeded: The measured weight exceeds the maximum weight allowed in the mold/container.",
            ScaleError.ACK_TIMEOUT: "ACK timeout: The scale did not send an ACK within the expected time.",
            ScaleError.COMMAND_FAILED: "Command failed: The command failed after multiple retry attempts.",
        }.get(self, "Unknown error code. Check error code on scale display and consult FX-120i manual.")

    @staticmethod
    def from_response(resp: str):
        if resp.startswith('EC,'):
            code = resp[4:7]
            try:
                return ScaleError[code]
            except KeyError:
                return code  # Unknown error code
        return None

class ScaleException(Exception):
    pass

class ScaleUnitException(ScaleException):
    pass

class ScaleHeaderException(ScaleException):
    pass

class ScaleOverloadException(ScaleException):
    pass

class ScaleMaxWeightException(ScaleException):
    # to string: Max weight exceeded: The measured weight exceeds the maximum weight allowed in the mold/container.
    pass

class ScaleAckTimeoutException(ScaleException):
    pass

class ScaleCommandFailedException(ScaleException):
    pass

# Data format for weight responses from the scale:
# Header: 2 characters, 'ST' (stable), 'US' (unstable), or 'OL' (overload)
# Separator: ',' (comma)
# Polarity sign: 1 character, '+' or '-'
# Data: Numeric value, continues until first space (start of unit)
# Unit: 3 characters, should be '  g' (two spaces and a 'g')
# Terminator: CR LF (\r\n)
# Example: 'ST,+00123.45  g\r\n'

class Scale:
    """
    Class for a digital scale connected via serial port (A&D FX-120i protocol).
    Provides methods to send commands and parse responses according to the scale's protocol.
    """

    def __init__(self, port: str, baudrate: int = 9600, timeout: int = 10, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS):
        """
        Initialize the Scale object and connection parameters.
        :param port: Serial port (e.g., 'COM1' or '/dev/ttyUSB0')
        :param baudrate: Baud rate for serial communication
        :param timeout: Read timeout in seconds
        :param parity: Parity setting (default: PARITY_NONE)
        :param stopbits: Stop bits setting (default: STOPBITS_ONE)
        :param bytesize: Byte size setting (default: EIGHTBITS)
        """
        self.port = port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.timeout = timeout
        self.serial = None
        self._is_connected = False
        self.x = ... # x coordinate of the scale
        self.y = ... # y coordinate of the scale
        self.z = ... # z coordinate of the scale

    def connect(self):
        """
        Establish a serial connection to the scale.
        Raises ScaleException if connection fails.
        """
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout
            )
            self._is_connected = True
            print(f"[DEBUG] Serial connection established: {self.serial}")
            print(f"[DEBUG] Serial port open: {self.serial.is_open}")
        except serial.SerialException as e:
            self._is_connected = False
            raise ScaleException(f"Error connecting to scale: {e}")

    def disconnect(self):
        """
        Close the serial connection to the scale.
        """
        if self.serial and self.serial.is_open:
            self.serial.close()
        self._is_connected = False
        self.serial = None

    @property
    def is_connected(self) -> bool:
        """
        Check if the scale is currently connected.
        :return: True if connected, False otherwise
        """
        return self._is_connected and self.serial and self.serial.is_open

    def _wait_for_ack(self, timeout: float = ACK_TIMEOUT) -> tuple:
        """
        Wait for an ACK response from the scale.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (success: bool, received_data: bytes)
            
        Raises:
            ScaleException: If error response received instead of ACK
        """
        start_time = time.time()
        buffer = b''
        expected_ack_sequence = b'\x06\r\n'  # ACK CR LF
        
        while time.time() - start_time < timeout:
            if self.serial.in_waiting > 0:
                # Read available data
                new_data = self.serial.read(self.serial.in_waiting)
                buffer += new_data
                
                # Check if we have the ACK sequence
                if expected_ack_sequence in buffer:
                    # Find position of ACK sequence
                    ack_pos = buffer.find(expected_ack_sequence)
                    # Check for any data before ACK
                    if ack_pos > 0:
                        print(f"[DEBUG] Warning: Unexpected data before ACK: {buffer[:ack_pos]}")
                    # Remove ACK sequence and everything before it from buffer
                    buffer = buffer[ack_pos + len(expected_ack_sequence):]
                    # Put remaining data back in buffer
                    if buffer:
                        print(f"[DEBUG] Data after ACK: {buffer}")
                        # Note: We can't put data back, so we'll just note it
                    return (True, buffer)
                
                # Check for error response
                if b'EC,' in buffer:
                    # Parse error response
                    try:
                        error_str = buffer.decode('ascii', errors='ignore')
                        if 'EC,' in error_str:
                            lines = error_str.split('\r\n')
                            for line in lines:
                                if line.startswith('EC,'):
                                    err = ScaleError.from_response(line)
                                    raise ScaleException(f"Scale error: {err} ({line})")
                    except UnicodeDecodeError:
                        pass
            
            time.sleep(0.01)  # Small delay to prevent busy waiting
        
        # Timeout - return the buffer we received
        return (False, buffer)

    def _send_command(self, cmd: str, expect_data: bool = False) -> str:
        """
        Send a command to the scale with retry logic and ACK handling.
        
        Args:
            cmd: Command string to send
            expect_data: If True, expects a data response after ACK
            
        Returns:
            Response string from the scale
            
        Raises:
            ScaleException: If command fails after retries or ACK timeout
        """
        # Determine if command expects ACK
        expect_ack = ACK_COMMANDS.get(cmd, True)  # Default to True for unknown commands
        
        # Check if this is a dual ACK command
        is_dual_ack = cmd in DUAL_ACK_COMMANDS
        
        for attempt in range(MAX_RETRIES):
            try:
                if not self.is_connected:
                    raise ScaleException("Scale is not connected.")
                
                # Clear input buffer and send command
                self.serial.reset_input_buffer()
                self.serial.write((cmd + CRLF).encode('ascii'))
                
                if expect_ack:
                    # Wait for first ACK
                    ack_received, received_data = self._wait_for_ack(ACK_TIMEOUT)
                    if not ack_received:
                        if attempt < MAX_RETRIES - 1:
                            print(f"[DEBUG] Command '{cmd}' failed on attempt {attempt + 1}, retrying...")
                            print(f"[DEBUG] Received serial data: {received_data}")
                            time.sleep(RETRY_DELAY)
                            continue
                        else:
                            print(f"[DEBUG] Final failure - Received serial data: {received_data}")
                            raise ScaleAckTimeoutException(f"ACK timeout for command '{cmd}' after {MAX_RETRIES} attempts")
                    
                    # For dual ACK commands, wait for second ACK
                    if is_dual_ack:
                        ack_received, received_data = self._wait_for_ack(ACK_TIMEOUT)
                        if not ack_received:
                            if attempt < MAX_RETRIES - 1:
                                print(f"[DEBUG] Command '{cmd}' failed on attempt {attempt + 1} (second ACK), retrying...")
                                print(f"[DEBUG] Received serial data: {received_data}")
                                time.sleep(RETRY_DELAY)
                                continue
                            else:
                                print(f"[DEBUG] Final failure - Received serial data: {received_data}")
                                raise ScaleAckTimeoutException(f"Second ACK timeout for dual ACK command '{cmd}' after {MAX_RETRIES} attempts")
                
                if expect_data:
                    # Read data response
                    data = self.serial.readline()
                    if not data:
                        # Check if there's any data in the buffer
                        remaining = b''
                        if self.serial.in_waiting > 0:
                            remaining = self.serial.read(self.serial.in_waiting)
                        if attempt < MAX_RETRIES - 1:
                            print(f"[DEBUG] Command '{cmd}' failed on attempt {attempt + 1} (no data response), retrying...")
                            print(f"[DEBUG] Received serial data: {remaining}")
                            time.sleep(RETRY_DELAY)
                            continue
                        else:
                            print(f"[DEBUG] Final failure - Received serial data: {remaining}")
                            raise ScaleException("No data response from scale after ACK")
                    
                    decoded = data.decode('ascii').strip()
                    print(f"[DEBUG] Data response: {decoded}")
                    
                    # Check for error in data response
                    if decoded.startswith('EC,'):
                        err = ScaleError.from_response(decoded)
                        raise ScaleException(f"Scale error in data response: {err} ({decoded})")
                    
                    return decoded
                
                # Command completed successfully
                return 'ACK'
                
            except (ScaleException, ScaleAckTimeoutException):
                if attempt < MAX_RETRIES - 1:
                    # Logging already done above at point of failure
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    raise
        
        raise ScaleCommandFailedException(f"Command '{cmd}' failed after {MAX_RETRIES} attempts")

    # --- Command Methods ---
    def cancel(self):
        """Cancel the S or SIR command."""
        return self._send_command('C')

    def query_weight(self):
        """Request the weight data immediately (Q command)."""
        return self._send_command('Q', expect_data=True)

    def request_stable_weight(self):
        """Request the weight data when stabilized (S command)."""
        return self._send_command('S', expect_data=True)

    def request_instant_weight(self):
        """Request the weight data immediately (SI command)."""
        return self._send_command('SI', expect_data=True)

    def request_continuous_weight(self):
        """Request the weight data continuously (SIR command)."""
        return self._send_command('SIR', expect_data=True)

    def request_stable_weight_escp(self):
        """Request the weight data when stabilized (ESC+P command)."""
        return self._send_command('\x1bP', expect_data=True)  # ESC+P

    def calibrate(self):
        """Perform calibration (CAL command)."""
        return self._send_command('CAL')

    def calibrate_external(self):
        """Calibrate using an external weight (EXC command)."""
        return self._send_command('EXC')

    def display_off(self):
        """Turn the display off (OFF command)."""
        return self._send_command('OFF')

    def display_on(self):
        """Turn the display on (ON command)."""
        return self._send_command('ON')

    def power_on(self):
        """Alias for turning the display on."""
        return self.display_on()

    def power_off(self):
        """Alias for turning the display off."""
        return self.display_off()

    def print_weight(self):
        """Print the current weight (PRT command)."""
        return self._send_command('PRT', expect_data=True)

    def re_zero(self):
        """Re-zero the scale (R command)."""
        return self._send_command('R')

    def sample(self):
        """Sample command (SMP command)."""
        return self._send_command('SMP')

    def tare(self):
        """Tare the scale (T command)."""
        return self._send_command('T')

    def mode(self):
        """Change the weighing mode (U command)."""
        return self._send_command('U')

    def get_id(self):
        """Request the ID number (?ID command)."""
        return self._send_command('?ID', expect_data=True)

    def get_serial_number(self):
        """Request the serial number (?SN command)."""
        return self._send_command('?SN', expect_data=True)

    def get_model(self):
        """Request the model name (?TN command)."""
        return self._send_command('?TN', expect_data=True)

    def get_tare_weight(self):
        """Request the tare weight (?PT command)."""
        return self._send_command('?PT', expect_data=True)

    def set_tare_weight(self, value: float, unit: str = 'g'):
        """
        Set the tare weight (PT command).
        :param value: Tare weight value
        :param unit: Weighing unit (default 'g')
        """
        cmd = f'PT:{value:.3f}{unit}'
        return self._send_command(cmd)

    def get_weight(self, stable: bool = True) -> float:
        """
        Get the current weight from the scale, parsing the response according to the data format.
        :param stable: If True, waits for stable weight; otherwise, allows unstable
        :return: The weight in grams
        """
        resp = self.request_stable_weight() if stable else self.request_instant_weight()
        print(f"[DEBUG] Response: {resp}")
        return self._parse_weight(resp, expect_stable=stable)

    def _parse_weight(self, data: str, expect_stable: bool = True) -> float:
        """
        Parse the weight data string from the scale according to the protocol data format.
        Checks header, sign, value, unit, and overload state. Throws errors for protocol violations.
        :param data: Raw data string from the scale
        :param expect_stable: If True, expects 'ST' header; else allows 'ST' or 'US'
        :return: Parsed weight as float
        """
        # Data format: HH,PSDDDDDD UNIT\r\n
        # Example: 'ST,+00123.45  g\r\n' or 'US,-00012.34  g\r\n' or 'OL,+00000.00  g\r\n'
        try:
            if not data or len(data) < 13:
                raise ScaleException(f"Data too short to parse: '{data}'")
            header = data[0:2]
            if data[2] != ',':
                raise ScaleException(f"Expected ',' after header in: '{data}'")
            if header == 'OL':
                raise ScaleOverloadException(ScaleError.OVERLOAD.desc)
            if expect_stable:
                if header != 'ST':
                    raise ScaleHeaderException(ScaleError.BAD_HEADER.desc + f" Got '{header}' when expecting 'ST'.")
            else:
                if header not in ('ST', 'US'):
                    raise ScaleHeaderException(ScaleError.BAD_HEADER.desc + f" Got '{header}' when expecting 'ST' or 'US'.")
            sign = data[3]
            if sign not in ('+', '-'):  # Polarity sign, 0 is positive, but protocol uses +/-, so accept both
                raise ScaleException(f"Unexpected sign character: '{sign}' in '{data}'")
            # Find start of unit (first space after data)
            try:
                unit_start = data.index(' ', 4)
            except ValueError:
                raise ScaleException(f"Could not find start of unit in: '{data}'")
            value_str = data[4:unit_start]
            try:
                value = float(value_str)
            except ValueError:
                raise ScaleException(f"Could not parse numeric value from: '{value_str}' in '{data}'")
            unit = data[unit_start:unit_start+4]
            if unit != '  g':
                raise ScaleUnitException(ScaleError.BAD_UNIT.desc + f" Got '{unit}' instead.")
            
            # Apply sign to get final weight value
            final_value = value if sign == '+' else -value
            
            # Check for negative weight (possible tare issue)
            if final_value < -1.0:
                print(f"[DEBUG] Warning: Negative weight detected: {final_value:.4f} g (possible tare issue or container removed)")
            
            # Check for positive weight exceeding maximum
            if value > MAX_WEIGHT:
                # TODO: In the future, the jubilee should respond to this exception by removing the container from the scale
                raise ScaleMaxWeightException(ScaleError.MAX_WEIGHT.desc)
            
            return final_value
        except ScaleException:
            raise
        except Exception as e:
            raise ScaleException(f"Could not parse weight from: '{data}'. Error: {e}") 