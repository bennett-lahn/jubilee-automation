# Tamper with Stall Detection and Sensorless Homing

This document describes the implementation of a tamper tool for the Jubilee automation system that uses TMC driver stall detection for tamping operations and sensorless homing for finding the home position.

## Overview

The tamper is a fixed tool that moves vertically to compress powder material in molds. It uses two distinct TMC2209 driver configurations:
- **Sensorless Homing**: For finding the home position without physical endstops
- **Stall Detection**: For determining when material has been fully compressed during tamping

## Key Features

- **Fixed Tamper Design**: The tamper is fixed to the toolhead, and the manipulator moves vertically to perform tamping
- **Dual M915 Configuration**: Separate configurations for homing (R1) and stall detection (R2)
- **Sensorless Homing**: Uses TMC2209 StallGuard 4 to find home position without endstops
- **Stall Detection**: Uses TMC2209 StallGuard 4 to detect when material resistance prevents further movement
- **Configurable Parameters**: Motor specifications and detection parameters can be configured via JSON
- **Automatic Event Handling**: Stall events are automatically handled by RepRapFirmware's driver-stall.g macro
- **Two-Phase Tamping**: Fast approach followed by slow tamping with stall detection
- **Intelligent Stall Response**: Automatic powder removal and retraction sequence when stall is detected

## Hardware Requirements

- **Motor**: NEMA 17 stepper motor (1.8° step angle, 200 steps/rev)
- **Driver**: TMC2209 with StallGuard 4 support
- **Controller**: RepRapFirmware-compatible board (Duet 3, etc.)
- **Axis**: Z-axis for vertical tamper movement

## Configuration

### Motor Specifications

The tamper uses the following default motor specifications:

```json
{
    "full_steps_per_rev": 200,
    "rated_current": 1.5,
    "actual_current": 1.0,
    "rated_holding_torque": 0.4,
    "driver_type": "TMC2209"
}
```

### Stall Detection Parameters (for tamping)

Stall detection is configured using the M915 command with these parameters:

- **S (threshold)**: Stall detection sensitivity (-64 to +63 for TMC2209)
- **F (filter)**: Filter mode (1 = filtered, 0 = unfiltered)
- **H (min_speed)**: Minimum speed for reliable stall detection
- **R (action)**: Action on stall (2 = create event)

### Sensorless Homing Parameters (for homing)

Sensorless homing uses separate M915 parameters:

- **S (threshold)**: Homing sensitivity (typically same as stall detection)
- **F (filter)**: Filter mode (1 = filtered)
- **R (action)**: Action on stall (1 = report only during homing)

### Stall Response Parameters

The stall response sequence is configurable:

- **step_size**: Distance per step for stall response movements (mm)
- **speed**: Speed for stall response movements (mm/min)
- **shake_count**: Number of shake cycles to remove powder
- **shake_distance**: Distance for each shake movement (mm)

### Configuration File

Create a `tamper_config.json` file:

```json
{
    "tamper": {
        "motor_specs": {
            "full_steps_per_rev": 200,
            "rated_current": 1.5,
            "actual_current": 1.0,
            "rated_holding_torque": 0.4,
            "driver_type": "TMC2209"
        },
        "stall_detection": {
            "threshold": 3,
            "filter": 1,
            "min_speed": 200,
            "action": 2
        },
        "sensorless_homing": {
            "threshold": 3,
            "filter": 1,
            "action": 1,
            "speed": 2000,
            "acceleration": 1000,
            "current": 0.8
        },
        "stall_response": {
            "step_size": 0.1,
            "speed": 500,
            "shake_count": 5,
            "shake_distance": 0.2
        },
        "movement": {
            "axis": "Z",
            "driver": 2,
            "board_address": 0,
            "speed": 1000,
            "acceleration": 500
        },
        "tamping": {
            "default_depth": 5.0,
            "approach_speed": 1000,
            "tamp_speed": 500,
            "max_depth": 20.0
        }
    }
}
```

## Stall Detection Theory

### Minimum Speed Calculation

The minimum speed for reliable stall detection is calculated using:

```
Hmin = full_steps_per_rev × rated_current × actual_current / (√2 × π × rated_holding_torque)
```

Where:
- `full_steps_per_rev`: 200 for 1.8° steppers
- `rated_current`: Motor rated current in amps
- `actual_current`: Actual current used (often reduced for stall detection)
- `rated_holding_torque`: Motor holding torque in Nm

### TMC2209 Configuration

For TMC2209 drivers, the following configuration is required:

1. **StealthChop Mode**: Set driver to stealthChop mode using `M569 P[driver] D3`
2. **Stall Detection**: Configure using `M915 [axis] S[threshold] F[filter] H[min_speed] R[action]`
3. **Sensorless Homing**: Configure using `M915 [axis] S[threshold] F[filter] R[action]`

## Stall Response Behavior

### M400 Command Function

The **M400** command is a critical RepRapFirmware command that:

- **Waits for all moves to complete**: Ensures all queued movements finish before proceeding
- **Stops the machine**: Halts all motor movement immediately
- **Prevents further movement**: Blocks new movements until explicitly commanded
- **Maintains position**: Keeps the machine at its current position without losing steps

**Why M400 is used in stall response:**
1. **Immediate Stop**: When a stall is detected, the motor must stop immediately to prevent damage
2. **Position Safety**: Ensures the tamper doesn't continue trying to move into the material
3. **Clean State**: Provides a clean starting point for the response sequence
4. **Prevents Queuing**: Stops any additional movements that might be queued

### Stall Response Sequence

When a stall is detected, the tamper automatically executes this sequence:

#### Step 1: Immediate Stop (M400)
```gcode
M400  ; Wait for all moves to complete and stop
```
- Stops all motor movement immediately
- Ensures clean state for response sequence
- Prevents further damage to motor or material

#### Step 2: Move Up 2 Steps
```gcode
G1 Z{current_position + 0.2} F30000  ; Move up 0.2mm
```
- Moves up 0.2mm (2 steps) from stall position
- Creates space for powder removal
- Uses fast speed (30,000 mm/min) for quick response

#### Step 3: Shake Sequence (5 cycles)
```gcode
; Repeat 5 times:
G1 Z{up_position - 0.2} F30000  ; Down 0.2mm
G1 Z{up_position} F30000        ; Up 0.2mm
```
- Shakes up and down 5 times
- Each shake is 0.2mm down, then 0.2mm up
- Removes powder stuck to the tamper
- Uses fast speed for effective powder removal

#### Step 4: Full Retraction
```gcode
G1 Z0 F30000  ; Retract to home position
```
- Moves tamper back to home position (Z=0)
- Completes the tamping cycle
- Prepares for next operation

### Stall Response Parameters

The stall response behavior can be customized:

```json
"stall_response": {
    "step_size": 0.1,        // mm per step (default: 0.1mm)
    "speed": 500,            // mm/min for response movements
    "shake_count": 5,        // number of shake cycles
    "shake_distance": 0.2    // mm for each shake movement
}
```

### Benefits of This Response Sequence

1. **Material Protection**: Immediate stop prevents over-compression
2. **Powder Removal**: Shake sequence removes stuck powder
3. **Tool Protection**: Full retraction prevents tool damage
4. **Automation Ready**: System is ready for next operation
5. **Consistent Results**: Standardized response ensures repeatability

## RepRapFirmware Integration

### Using Sensorless Homing AND Stall Detection

The system follows RepRapFirmware guidelines for using both sensorless homing and stall detection:

1. **Homing Macro (rehome.g)**: Starts with M915 for sensorless homing, ends with M915 for stall detection
2. **Config.g**: Contains the default stall detection configuration
3. **Event Handling**: driver-stall.g automatically handles stall events with response sequence

### Driver Stall Event Handler

Create a `driver-stall.g` file in your RepRapFirmware system folder:

```gcode
; Driver stall event handler for tamper
if param.D == 2 && param.B == 0
    ; This is the tamper driver stall
    echo "Tamper stall detected - material appears to be fully tamped"
    
    ; Step 1: Immediately stop all movements (M400)
    M400
    echo "M400: Stopped all movements"
    
    ; Step 2: Move up 2 steps (0.2mm) from current position
    var up_position = move.axes[2].machinePosition + 0.2
    G1 Z{var.up_position} F30000
    echo "Moving up 0.2mm to shake off powder"
    
    ; Step 3: Shake up and down 5 times to shake off powder
    var shake_distance = 0.2
    var shake_count = 5
    
    while var.shake_count > 0
        ; Move down
        var down_position = var.up_position - var.shake_distance
        G1 Z{var.down_position} F30000
        echo "Shake {var.shake_count}: Down"
        
        ; Move back up
        G1 Z{var.up_position} F30000
        echo "Shake {var.shake_count}: Up"
        
        ; Decrement counter
        set var.shake_count = var.shake_count - 1
    endwhile
    
    ; Step 4: Fully retract to home position (Z=0)
    G1 Z0 F30000
    echo "Fully retracting to home position"
    
    ; Set global variable to indicate tamper stall
    set global.tamper_stall_detected = true
    set global.tamper_stall_time = move.axes[2].machinePosition
    
    ; Continue with normal operation
    echo "Stall response sequence complete. Tamper fully retracted."
else
    ; Handle other driver stalls
    echo "Driver stall detected on driver " ^ param.D
endif
```

### Homing Macro (rehome.g)

Create a `rehome.g` file that follows the RepRapFirmware guidelines:

```gcode
; Tamper sensorless homing macro
; Step 1: Configure sensorless homing at the start
M915 Z S3 R1 F1

; Step 2: Reduce motor current for homing
M906 Z800

; Step 3: Set homing parameters
M201 Z1000
M566 Z800

; Step 4: Perform homing move
G28 Z

; Step 5: Wait for completion
M400

; Step 6: Revert to stall detection configuration
M915 Z S3 F1 H200 R2

; Step 7: Restore normal parameters
M906 Z1000
M201 Z500
M566 Z500
G92 Z0

echo "Tamper sensorless homing complete"
```

### Configuration Commands

Add these commands to your `config.g`:

```gcode
; Configure tamper motor driver for stealthChop
M569 P2 D3

; Configure stall detection for tamper (default mode)
M915 Z S3 F1 H200 R2

; Configure sensorless homing
M574 Z1 S1

; Set tamper axis parameters
M201 Z500
M203 Z2000
M566 Z500
```

## Usage

### Basic Workflow

```python
from Manipulator import Manipulator

# Create manipulator with configuration
with open('tamper_config.json', 'r') as f:
    config = json.load(f)

manipulator = Manipulator(index=0, name="tamper", config=config)

# Select tamper tool
manipulator.select_tool(Manipulator.TOOL_TAMPER)

# Step 1: Home the tamper (uses sensorless homing)
manipulator.home_tamper(machine_connection=machine_connection)

# Step 2: Configure stall detection for tamping
manipulator.configure_stall_detection(machine_connection)

# Step 3: Perform tamping with stall detection
manipulator.tamp(target_depth=10.0, machine_connection=machine_connection)
```

### Advanced Tamping

```python
# Tamp with custom speeds
manipulator.tamp_with_stall_detection(
    target_depth=15.0,
    approach_speed=1200,  # mm/min
    tamp_speed=400,       # mm/min
    machine_connection=machine_connection
)
```

## Calibration and Tuning

### Stall Detection Calibration

Follow these steps to calibrate stall detection:

1. **Start with baseline settings**:
   - M915 Z S3 R1 F1 (report only)
   - M906 Z500 (motor current)
   - M201 Z500 (acceleration)
   - M566 Z500 (jerk)

2. **Test for false stalls**:
   - Run test operations
   - Monitor console for false stall reports
   - Adjust parameters if needed

3. **Fine-tune sensitivity**:
   - If too many false stalls: increase S value (S3 → S5)
   - If no stall detection: decrease S value (S3 → S1)
   - Adjust motor current, acceleration, and jerk as needed

4. **Test hard stall detection**:
   - Simulate hard stall conditions
   - Verify stall detection works reliably

5. **Enable event creation**:
   - Change R1 to R2 or R3 for production use

### Sensorless Homing Calibration

1. **Set homing parameters**:
   - Use same S value as stall detection
   - Set R=1 for reporting only during testing
   - Use reduced motor current for homing

2. **Test homing reliability**:
   - Run homing operations multiple times
   - Verify consistent home position
   - Adjust parameters if needed

3. **Enable production mode**:
   - Change R=1 to R=2 or R=3 for production use

### Stall Response Tuning

1. **Adjust step size**:
   - Increase for more aggressive powder removal
   - Decrease for finer control

2. **Tune shake parameters**:
   - Increase shake_count for more thorough powder removal
   - Adjust shake_distance based on powder characteristics

3. **Optimize speeds**:
   - Faster speeds for quicker response
   - Slower speeds for more controlled movement

## Testing

Run the test script to verify functionality:

```bash
python tamper_test.py
```

This will:
1. Test configuration loading
2. Test sensorless homing setup and operation
3. Test stall detection setup
4. Test tamping operations
5. Test batch tamping
6. Test complete workflow (homing → tamping → batch operations)
7. Test stall response sequence
8. Verify stall event detection

## Troubleshooting

### Stall Detection Not Working

1. **Check Motor Current**: Ensure actual current is sufficient but not too high
2. **Verify Speed**: Ensure movement speed is above minimum stall detection speed
3. **Adjust Threshold**: Try different S values (1-10 for most motors)
4. **Check Driver Mode**: Ensure TMC2209 is in stealthChop mode
5. **Verify M915 Configuration**: Check that R parameter is set correctly

### False Stall Detection

1. **Increase Threshold**: Try higher S values
2. **Use Filtered Mode**: Set F=1 for filtered stall detection
3. **Reduce Acceleration**: Lower acceleration can reduce false stalls
4. **Check Motor Temperature**: Hot motors may cause false stalls
5. **Adjust Jerk Settings**: Lower jerk values can help

### Sensorless Homing Issues

1. **Check Homing Speed**: Ensure speed is appropriate for your setup
2. **Verify Current Settings**: Reduced current helps with homing reliability
3. **Check M915 Configuration**: Ensure R=1 during homing
4. **Test Homing Consistency**: Run multiple homing operations
5. **Adjust Threshold**: Same S value as stall detection typically works

### No Stall Detection

1. **Check Speed**: Ensure speed is above calculated minimum
2. **Verify Configuration**: Check M915 and M569 commands
3. **Test Hardware**: Verify motor and driver connections
4. **Check Material**: Ensure material provides sufficient resistance
5. **Verify R Parameter**: Ensure R=2 or R=3 for event creation

### Stall Response Issues

1. **Check M400 Execution**: Verify M400 command is being sent and executed
2. **Adjust Response Parameters**: Tune step_size, speed, and shake parameters
3. **Verify Movement Commands**: Check that G1 commands are being sent correctly
4. **Test Response Sequence**: Run manual tests of the response sequence
5. **Check Position Tracking**: Ensure position is being updated correctly

## Safety Considerations

- **Maximum Depth**: Always set reasonable maximum tamping depths
- **Emergency Stop**: Ensure emergency stop functionality is available
- **Material Limits**: Be aware of material compression limits
- **Motor Protection**: Monitor motor temperature and current
- **Homing Safety**: Ensure homing doesn't cause mechanical damage
- **Stall Response Safety**: Verify response sequence doesn't cause collisions

## API Reference

### Manipulator Class

#### Methods

- `configure_sensorless_homing(machine_connection)`: Configure sensorless homing
- `configure_stall_detection(machine_connection)`: Configure stall detection
- `home_tamper(machine_connection)`: Perform sensorless homing
- `tamp(target_depth, machine_connection)`: Perform tamping operation
- `tamp_with_stall_detection(target_depth, approach_speed, tamp_speed, machine_connection)`: Advanced tamping
- `handle_stall_event(stall_event, machine_connection)`: Handle stall event with response sequence
- `get_tamper_status()`: Get current tamper status

#### Attributes

- `tamper_position`: Current tamper position in mm
- `stall_detection_configured`: Whether stall detection is configured
- `sensorless_homing_configured`: Whether sensorless homing is configured
- `tamper_motor_specs`: Motor specifications dictionary
- `stall_response_parameters`: Stall response configuration

### TamperStallEvent Class

#### Attributes

- `driver_number`: Local driver number
- `board_address`: CAN address of the board
- `timestamp`: Event timestamp
- `event_type`: Event type ("driver-stall")

## Future Enhancements

- **Adaptive Threshold**: Automatically adjust stall threshold based on material
- **Multi-Axis Tamping**: Support for complex tamping patterns
- **Force Feedback**: Integration with force sensors for additional feedback
- **Material Database**: Database of material-specific tamping parameters
- **Advanced Homing**: Support for multiple homing strategies
- **Calibration Automation**: Automated calibration procedures
- **Advanced Stall Response**: Material-specific response sequences
- **Real-time Monitoring**: Live monitoring of motor current and position during tamping 