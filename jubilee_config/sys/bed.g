; This macro should ONLY be called from homez.g, as it assumes it is in a safe position to move
; to the front left probe point.
M290 R0 S0                  ; Reset baby stepping
M561                        ; Disable any Mesh Bed Compensation
G90                         ; Ensure the machine is in absolute mode

G1 Z60                      ; pop bed down
G1 X271.3 Y190                     
G30 P0 X271.3 Y190 Z-99999  ; probe near front left leadscrew
G1 Z60
G1 Y178                     ; Move out of way of trickler
G1 X50 
G1 Y192
G30 P1 X50 Y192 Z-99999     ; probe near front right leadscrew and calibrate 3 motors
G1 Z60
G1 Y15                      ; move near back leadscrew, avoiding trickler
G1 X135 
G30 P2 X135 Y15 Z-99999 S3  ; probe near back leadscrew
G1 Z90                      ; Move bed to mold transfer height when finished
; G29 S2                      ; Disable Mesh Bed Compensation (height map not accurate for current bed)
G1 X150.0 Y80.0 F1000       ; Move to global ready position