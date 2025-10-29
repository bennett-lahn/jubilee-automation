; Engage the toolchanger lock

G91                 ; Set relative mode
M400                ; Wait for all commands to finish
G1 U10 F5000 H0     ; Back off the limit switch with a small move
M400                ; Wait for all commands to finish
M906 U900           ; temporarily increase max current setting
G1 U200 F5000 H1    ; Perform up to one rotation looking for the torque limit switch
M400                ; Wait for all commands to finish
M906 U670           ; revert to acceptable current setting
G90                 ; Set absolute mode
