; Jubilee Tamper Configuration for RepRapFirmware
; This file contains the necessary configuration for the tamper tool with sensorless homing and stall detection

; ============================================================================
; MOTOR AND DRIVER CONFIGURATION
; ============================================================================

; Configure tamper motor driver (TMC2209) for stealthChop mode
; P2 = driver number 2, D3 = stealthChop mode
M569 P2 D3

; Set motor current for tamper (1000mA = 1A)
M906 Z1000

; Set motor microstepping (16 microsteps per full step)
M350 Z16 I1

; ============================================================================
; AXIS CONFIGURATION
; ============================================================================

; Configure Z axis for tamper movement
; Steps per mm calculation: (200 steps/rev * 16 microsteps) / (8mm lead screw pitch) = 400 steps/mm
M92 Z400

; Set maximum feedrate for Z axis (mm/min)
M203 Z2000

; Set maximum acceleration for Z axis (mm/s²)
M201 Z500

; Set maximum jerk for Z axis (mm/s)
M566 Z500

; ============================================================================
; ENDSTOP CONFIGURATION
; ============================================================================

; Configure Z axis for sensorless homing
; S1 = sensorless homing enabled, F1 = inverted logic
M574 Z1 S1

; Set homing speed for Z axis (mm/min)
M913 Z80

; ============================================================================
; STALL DETECTION CONFIGURATION (DEFAULT MODE)
; ============================================================================

; Configure stall detection for tamper tamping operations
; Z = axis, S3 = threshold, F1 = filtered, H200 = min speed, R2 = create event
M915 Z S3 F1 H200 R2

; ============================================================================
; HOMING CONFIGURATION
; ============================================================================

; Set homing speeds (mm/min)
M913 Z80

; Set homing acceleration (mm/s²)
M201 Z1000

; Set homing jerk (mm/s)
M566 Z800

; ============================================================================
; SAFETY LIMITS
; ============================================================================

; Set software endstops for Z axis
M208 Z0:20

; Set maximum travel for Z axis (mm)
M208 Z0:20

; ============================================================================
; TOOL CONFIGURATION
; ============================================================================

; Define tamper tool
; T2 = tool number 2, P2 = driver number 2
M563 P2 D2 H2 F2

; Set tool name
M563 P2 S"Tamper"

; ============================================================================
; MACRO CONFIGURATION
; ============================================================================

; Enable rehome.g macro for sensorless homing
; This macro will be called when G28 Z is executed

; ============================================================================
; EVENT HANDLING
; ============================================================================

; Ensure driver-stall.g is in the system folder for handling stall events
; The driver-stall.g macro will be called automatically when stall events occur

echo "Tamper configuration loaded successfully" 