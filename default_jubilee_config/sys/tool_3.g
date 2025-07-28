M563 P3 S"Extruder #4" D3; Px = Tool number
                            ; Dx = Drive Number
                            ; H1 = Heater Number
M569 P2.1 S0				; Invert drive 0.0 (Gel Extruder)
                            ; Fx = Fan number print cooling fan
;M350 E16 I1                  ; Microstep Factor with interpolation
;M92 E3200					; steps per mm
;M201 E1000					; Extruder Acceleration
;M203 E500

G10 P3 X0 Y51.8679 Z-64.6
G10  P3 S0 R0               ; Set tool 0 operating and standby temperatures
                            ; (-273 = "off")
;M302 P1      ; disable cold extrusion checking
;M302 S0      ; always allow extrusion (disable checking)
;M572 D0 S0.085              ; Set pressure advance


;M98  P"/sys/Toffsets.g"     ; Set tool offsets from the bed


M501                        ; Load saved parameters from non-volatile memory