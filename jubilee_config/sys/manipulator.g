M563 P0 S"manipulator"

G10 P0 X32.4 Y0.0 Z-40.0 V0.0    ; Set tool offsets
G10  P0 S-273 R-273              ; Set tool 0 operating and standby temperatures
                                 ; (-273 = "off")

M501                        ; Load saved parameters from non-volatile memory

