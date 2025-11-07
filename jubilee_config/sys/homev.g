G91              ; relative moves
G1 V-300 F400 H1 ; big, slow positive move to look for endstop
G1 V5 F500       ; back off endstop
G1 V-10 F200 H1  ; find endstop again, slower
G90              ; absolute moves
G1 V30 F1500     ; move to a position of 0.5 to start