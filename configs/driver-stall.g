; Driver stall event handler for tamper
; This macro is called by RepRapFirmware when a driver stall is detected
; Parameters:
;   param.D = local driver number
;   param.B = CAN address of the board
;   param.S = full text string describing the fault

; Check if this is the tamper driver (driver 0 on main board)
if param.D == 0 && param.B == 0
    echo "Tamper stall detected - material appears to be fully tamped"
    
    ; Step 1: Immediately stop all movements (M400)
    ; M400 waits for all moves to complete and stops the machine
    M400
    echo "M400: Stopped all movements"
    
    ; Step 2: Move up 10mm from current position
    var up_position = move.axes[2].machinePosition + 10.0
    G1 Z{var.up_position}
    
    ; Step 3: Shake up and down 10 times to shake off powder
    ; Each shake is 1mm down and 1mm up
    var shake_distance = 1
    var shake_count = 10
    
    while var.shake_count > 0
        ; Move down
        var down_position = var.up_position - var.shake_distance
        G1 Z{var.down_position} F30000
        
        ; Move back up
        G1 Z{var.up_position} F30000
        
        ; Decrement counter
        set var.shake_count = var.shake_count - 1
    endwhile

    ; Step 4: Rehome to fully retract to Z=0
    G1 Z0 F30000
    echo "Fully retracting to home position"
    
    ; Continue with normal operation
    echo "Stall response sequence complete. Tamper fully retracted."
else
    ; This is a different driver stall - handle appropriately
    echo "Driver stall detected on driver " ^ param.D ^ " (board " ^ param.B ^ ")"
    echo "Stall details: " ^ param.S
    
    ; For non-tamper stalls, might want to pause or take other action
    M25 ; Pause
endif 