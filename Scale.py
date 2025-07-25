import time
import serial
from enum import Enum

MAX_WEIGHT = 10 # Immediately throw error if measured weight after taring exceeds this value; container may be overloaded

CR = '\r'
LF = '\n'
CRLF = CR + LF
ACK = b'\x06'  # ASCII 06h

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
    # ... add more as needed

    @property
    def desc(self):
        return {
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

    def __init__(self, port: str, baudrate: int = 2400, timeout: int = 1):
        """
        Initialize the Scale object and connection parameters.
        :param port: Serial port (e.g., 'COM1' or '/dev/ttyUSB0')
        :param baudrate: Baud rate for serial communication
        :param timeout: Read timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = None
        self._is_connected = False

    def connect(self):
        """
        Establish a serial connection to the scale.
        Raises ScaleException if connection fails.
        """
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            self._is_connected = True
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

    # TODO: Update to properly handle ACK; some commands send ACK, some don't
    # Also update to handle some errors without hard fail; i.e. lost command gets resent first before throwing exception
    # Also, not sure if response would be ACK or ACK + CRLF
    # Also add an error if returned weight is negative and handling like re-taring
    # Also add MAX_WEIGHT error handling (add to enum?)
    def _send_command(self, cmd: str, expect_data: bool = False) -> str:
        """
        Send a command to the scale and return the response.
        Handles ACK, error codes, and data responses.
        :param cmd: Command string to send
        :param expect_data: If True, expects a data response after ACK
        :return: Response string from the scale
        """
        if not self.is_connected:
            raise ScaleException("Scale is not connected.")
        # Send command with CR+LF
        self.serial.reset_input_buffer()
        self.serial.write((cmd + CRLF).encode('ascii'))
        # Read response
        response = self.serial.readline()
        if not response:
            raise ScaleException("No response from scale (timeout).")
        # Handle ACK or error
        if response == ACK: # Data requests may not return ACK if data is immediately available
            if expect_data:
                # Read next line for data
                data = self.serial.readline()
                if not data:
                    raise ScaleException("No data after ACK.")
                return data.decode('ascii').strip()
            return 'ACK'
        decoded = response.decode('ascii').strip()
        if decoded.startswith('EC,'):
            err = ScaleError.from_response(decoded)
            raise ScaleException(f"Scale error: {err} ({decoded})")
        return decoded

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
        return self._send_command('PRT')

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
            if value > MAX_WEIGHT:
                raise ScaleMaxWeightException(ScaleError.MAX_WEIGHT.desc)
            return value if sign == '+' else -value
        except ScaleException:
            raise
        except Exception as e:
            raise ScaleException(f"Could not parse weight from: '{data}'. Error: {e}") 