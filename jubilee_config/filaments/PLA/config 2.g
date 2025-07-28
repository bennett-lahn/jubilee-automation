M207 S0.9 R0.0 F3000 T3000 Z0.0           ; firmware retraction settings for PETG
;M307 H0 A214.3 C641.7 D1.3 S1.00 V24.0 B0 ; Bed PID tune for 120c
;M307 H1 A491.0 C190.9 D2.8 S1.00 V23.9 B0 ; Hot end PID tune at 280c
M566 X1200 Y1200 Z60 E3000                ; jerk settings for PETG
M204 P1000 T4000                          ; Set printing and travel accelerations
