; This is not actually used by RRF anymore. Leave for reference.

; Tamper sensorless homing macro
; This macro follows RepRapFirmware guidelines for using sensorless homing AND stall detection
; The M915 command for sensorless homing is at the start, and reverts to stall detection at the end

; Step 1: Configure sensorless homing at the start of homing macro
; This sets up M915 for homing with reporting only (R1)
M915 Z S3 R1 F1

; Step 2: Reduce motor current for homing (M906)
; Reduced current helps with stall detection during homing
M906 Z800

; Step 3: Set homing acceleration (M201)
M201 Z1000

; Step 4: Set homing speed (M566 - max speed change/jerk)
M566 Z800

; Step 5: Perform the actual homing move
G28 Z

; Step 6: Wait for homing to complete
M400

; Step 7: Revert M915 to stall detection configuration at the end of homing macro
; This sets up M915 for stall detection with event creation (R2)
M915 Z S3 F1 H200 R2

; Step 8: Restore normal motor current after homing
M906 Z1000

; Step 9: Restore normal acceleration
M201 Z500

; Step 10: Restore normal jerk settings
M566 Z500

; Step 11: Set position to 0 after homing
G92 Z0

echo "Tamper sensorless homing complete" 