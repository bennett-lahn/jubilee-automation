; Home T (Tamper) axis

; Set-up for sensorless homing
; Z = axis, S3 = threshold, F1 = not filtered, H200 = min speed, R1 = log stall
M915 T S3 F0 H200 R1

M400                    ; Wait for current move to finish

M913 T30                ; drop motor current to 30%
G91                     ; Set relative mode
G1 H2 Z5 F5000          ; Lower the bed
G1 T-400 F6000 H1       ; Big negative move to search for endstop
G1 T4 F600              ; Back off the endstop
G1 T-10 F600 H1         ; Find endstop again slowly
G1 H2 Z-5 F5000         ; Raise the bed
M913 T30                ; return current to 100%
G90                     ; Set absolute mode

; Enable Tamper stall detection again
; Z = axis, S3 = threshold, F1 = filtered, H200 = min speed, R2 = create event
M915 T S3 F1 H200 R2
