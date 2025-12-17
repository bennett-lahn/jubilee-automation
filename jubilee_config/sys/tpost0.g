; tpost0.g
; Manipulator
; called after firmware thinks Tool0 is selected
; Note: tool offsets are applied at this point!
; Note that commands preempted with G53 will NOT apply the tool offset.

; M116 P1                  ; Wait for set temperatures to be reached
; M302 P1                  ; Prevent Cold Extrudes, just in case temp setpoints are at 0

G90                        ; Ensure the machine is in absolute mode before issuing movements.
G1 Z90                     ; Ensure leadscrew will clear molds when tool is removed
M208 Z27:Z195              ; Set hard limit so tool won't crash into bed if bad command given(this is bypassed during scale mold movements)
G1 Y321.5 F300
M98 P"/macros/tool_lock.g" ; Lock the tool
G1 Y270.0 F300         ; Back off the tool post
G1 Y80.0 F1200         ; Move back to global ready position in dogleg shape to avoid hitting trickler
G1 X150.0 F1200
