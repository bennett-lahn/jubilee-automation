G91              ; relative moves
G1 V400 F800 H1 ; big, slow positive move to look for endstop
G1 V-1 F600       ; back off endstop
G1 V10 F600 H1  ; find endstop again, slower
G90              ; absolute moves
G1 V0.5 F600     ; move to a position of 0.5 to start