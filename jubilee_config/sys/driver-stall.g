; Driver stall event handler for tamper
; This macro is called by RepRapFirmware when a driver stall is detected
; Parameters:
;   param.D = local driver number
;   param.B = CAN address of the board
;   param.S = full text string describing the fault

; Check if this is the manipulator driver (driver 0 on main board)
; TODO: Change these to match z-axis drivers
; TODO: Update this to improve stall logic. Need a better way to stop all movements than M400
; TODO: Change tamper axis name to a better name
if param.D == 0 && param.B == 0
    ; Manipulator has stalled   
    echo "Manipulator stall detected - this is bad...abort."
    abort



else if param.D == 0 && (param.B == 2 || param.B == 3 || param.B == 4)
    ; TODO: Update this with a better method for stopping movement
    ; Z-axis has stalled, probably (hopefully) due to tamping
    
    ; Step 1: Immediately stop all movements (M400)
    ; M400 waits for all moves to complete and stops the machine
    M400
    echo "M400: Stopped all movements"
    
else
    ; This is a different driver stall - handle appropriately
    echo "Driver stall detected on driver " ^ param.D ^ " (board " ^ param.B ^ ")"
    echo "Stall details: " ^ param.S
    
    ; For other stalls, might want to pause or take other action
    ; M25 ; Pause
endif 