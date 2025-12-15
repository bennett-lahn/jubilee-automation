M290 R0 S0                  ; Reset baby stepping
M561                        ; Disable any Mesh Bed Compensation

G1 Z60                      ; pop bed down
G1 X135 Y8                 ; move near back leadscrew
G30 P0 X135 Y8 Z-99999     ; probe near back leadscrew
G1 Z60 ; pop bed down
G1 X265 Y174                     
G30 P1 X265 Y175 Z-99999    ; probe near front left leadscrew
G1 Z60
G1 X50 Y174
G30 P2 X50 Y175 Z-99999 S3  ; probe near front right leadscrew and calibrate 3 motors
G29 S1                      ; Enable Mesh Bed Compensation
G1 Z80                     ; pop bed down when finished