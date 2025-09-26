; Home M (Manipulator) axis

; Set-up for sensorless homing
; M = axis, S3 = threshold, F1 = not filtered, H200 = min speed, R1 = log stall
M915 P0.0 S3 F0 H200 R1

M400                    ; Wait for current move to finish

M913 M30                ; drop motor current to 30%
G90                     ; Set absolute mode
G1 H2 Z215 F5000        ; Set bed to safe z height
G91                     ; Set relative mode
G1 M400 F6000 H1        ; Big positive move to search for endstop
G1 M-4 F600             ; Back off the endstop
G1 M10 F600 H1          ; Find endstop again slowly
G1 H2 Z-5 F5000         ; Raise the bed
M913 T30                ; return current to 100%
G90                     ; Set absolute mode

; Enable Manipulator stall detection again
; M = axis, S3 = threshold, F1 = filtered, H200 = min speed, R2 = create event
M915 P0.0 S3 F1 H200 R2
