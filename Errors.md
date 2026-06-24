# EXII Error Codes & Troubleshooting
 
Diagnostic and error reference for 3M MicroTouch EX II serial touch controllers. Use this when something isn't working as expected.
 
---
 
## Command Response Codes
 
These codes are returned by the controller for any command.
 
| Code | Meaning | Action |
|------|---------|--------|
| `0` | Success - command accepted and executed | None, continue |
| `1` | Invalid or unsupported command | Check the firmware version (NM) - command may not be supported in this variant |
| `2` | Parameter error or operation failed | Depends on the command; see specific codes below |
 
---
 
## DX Diagnostic Codes
 
The `DX` command runs the sensor self-test and returns:
 
### DX = 0: All OK
**Status:** Sensor healthy, all four corners coupled and reading properly.
 
**What to do:** Nothing - everything is working. You can proceed to `FT + MS` to stream coordinates.
 
---
 
### DX = 1: Command Not Supported
**Status:** This firmware doesn't have a DX command (very rare).
 
**What to do:** Try a different command like Z or NM to confirm the board is alive. Check the firmware version.
 
---
 
### DX = 2: FAILURE - Sensor Problem
**Status:** One or more corners are not reading correctly.
 
**Causes (in order of likelihood):**
 
1. **Wrong sensor type** (most common)
   - You have a resistive panel plugged into a capacitive-only controller
   - Capacitive boards cannot read resistive touch
   - Resistive needs two conductive layers that short together when pressed
   - Capacitive reads your finger's electrical field
   - They are mutually exclusive
2. **No sensor attached**
   - The flex cable isn't plugged in
   - Or it's plugged into the wrong header
3. **Flex cable not seated**
   - The FFC/ZIF connector needs to be fully pushed in
   - The little latch must be closed
   - Check for bent pins or debris in the connector
4. **One corner wire broken**
   - Cracked flex trace right at the bend/strain relief
   - Oxidized or corroded ZIF contact
   - Test with a multimeter: continuity from board pin to glass corner pad
5. **Board is genuinely faulty**
   - If you've tried a known-good capacitive panel and still get DX=2, the board itself may be dead
**How to diagnose which one:**
 
- **Run Format Raw:** Type `raw` in the console. Watch the four corner bars when you press different areas of the glass.
  - All four bars jump = sensor is capacitive and working, DX=2 is a baseline/false-alarm
  - Three bars jump, one stays flat = that corner's wire is broken
  - No bars jump no matter where you press = wrong sensor type or completely disconnected
  
- **Multimeter test:** Power off. Unplug the sensor. Probe from each corner lead to its busbar on the glass.
  - No continuity on one corner = broken wire
  - All show continuity = it's connected, so either wrong type or board issue
---
 
## No Response on Any Baud Rate
 
**What it means:** The board isn't answering on 9600, 19200, 4800, or 2400 baud.
 
**Causes:**
 
1. **Board has no power**
   - Check for a separate power connector (not just TX/RX/GND on the DB9)
   - These boards often need +5V or +12V on dedicated pins
   - A powered-but-unpowered board looks dead
2. **TX/RX lines swapped**
   - Your computer sends on the wrong line
   - Try crossing the data lines: swap TX and RX at the connector
3. **Wrong COM port**
   - You're talking to a printer or modem instead of the controller
   - Use Device Manager or `mode COM7` to verify the port exists
4. **Serial adapter broken**
   - Test with a different USB-to-serial adapter
   - Or a different machine if possible
5. **Board is actually dead**
   - No response after trying all above
**How to fix:**
 
```
1. Confirm power is reaching the board (look for LED, test with multimeter)
2. Double-check TX/RX are not swapped
3. Try a different COM port
4. Swap the serial adapter
5. If still nothing, the board may be bricked
```
 
---
 
## LED Status Patterns
 
The board usually has a status LED. Patterns vary by firmware, but:
 
| Pattern | Meaning |
|---------|---------|
| Steady bright | Power-on self-test running |
| Steady dim | Powered and idle, sensor OK |
| Blinking / flashing | Self-test failed (usually DX=2 candidate) |
| Off | No power or board is dead |
| Bright on touch | Sensing activity (older firmware) |
 
**What to expect:** After power-up, the LED should flash while the self-test runs (~1 second), then settle to a steady dim glow. If it keeps flashing, the self-test is looping (sensor not found).
 
---
 
## Touch Not Working (But DX = 0)
 
**What it means:** The sensor checks out, but no coordinates come through when you touch.
 
**Causes:**
 
1. **Not in stream mode**
   - You sent `FT` (format tablet) but forgot `MS` (mode stream)
   - Without `MS`, the board doesn't send anything on touch
2. **Wrong format set**
   - You sent `FR` (format raw) instead of `FT` (tablet)
   - Raw mode sends impedance, not coordinates
   - Send `FT` for touch coordinates
3. **Sensor is capacitive but too far / not coupled**
   - The sensor glass has a protective cover (plastic sheet)
   - Capacitive touch may not work through thick covers
   - Remove the cover or press harder
4. **Board timeout or buffering issue**
   - Send `R` (reset) to clear any stuck state
   - Then `FT` and `MS` again
5. **Host is not listening**
   - You sent `MS` but are only reading one packet
   - `MS` sends continuously until you send `R`
   - Keep reading or use a terminal that buffers incoming data
**How to fix:**
 
```
R       (reset to clear state)
FT      (format tablet for coordinates)
MS      (enter stream mode - now sends on touch)
(press the glass - coordinates should appear)
R       (exit stream mode)
```
 
---
 
## Garbled Output / Noise
 
**What it means:** You're getting data, but it's full of junk or the signal is too noisy.
 
**Causes:**
 
1. **Wrong baud rate**
   - Even if the board responds to `Z`, data streaming may need a specific baud
   - Try `SR [code]` to set baud, or use `RD` to restore defaults
2. **Loose ground**
   - Capacitive sensors are sensitive to interference
   - Make sure the shield on your serial cable is grounded
   - Check GND connection between board and host
3. **Long cable or poor shielding**
   - >10 feet of unshielded serial is asking for trouble
   - Use a shielded DB9 cable
   - Keep away from AC power cables
4. **Sensor isn't properly grounded**
   - The flex-tail shield must be connected
   - If the shield is floating (not landed), noise floods in
5. **Normal raw noise**
   - If you're using `FR` (format raw), some noise is expected
   - The console's `raw` meter filters and smooths it
   - If you're reading raw yourself, apply a moving average or exponential smoothing
**How to fix:**
 
```
- Check baud with SR/RD
- Verify ground connections with multimeter
- Use shielded cable, keep it short
- Confirm shield is landed on the board and sensor
- If using FR data, apply low-pass filtering
```
 
---
 
## Serial Timeout (Command Hangs)
 
**What it means:** You sent a command and got no response after 1+ second.
 
**Causes:**
 
1. **Wrong baud rate**
   - Board is listening on 2400, you're sending at 9600
   - Your bytes are gibberish to the board, it ignores them
   - The tool auto-detects baud, but if you're using raw serial, you have to match
2. **Board not powered**
   - Responds to `Z` but not to longer commands
   - Usually means +V/GND are OK but the board isn't fully powered
3. **Command has a parameter typo**
   - `SR X` (invalid baud code) might timeout instead of returning `2`
   - Check the command syntax in COMMANDS.md
4. **Board is in stream mode and stuck**
   - If `MS` is active, the board is only sending touch data
   - Send `R` (reset) to exit stream mode, then try your command again
5. **Board is genuinely hung**
   - Rare, but it happens with corrupted firmware
   - Power cycle the board
   - If it still hangs, try `RD` (restore defaults) once to clear config
**How to fix:**
 
```
1. Confirm correct baud rate (use auto-detect tool, or try 2400/9600)
2. Verify power is reaching the board
3. Send R (reset) to clear any stuck state
4. Try a simple command like Z
5. If still stuck, power-cycle and try RD
```
 
---
 
## Board Responds but Then Goes Silent
 
**What it means:** Initial commands work (you get `R`, `Z` responses), but then nothing.
 
**Causes:**
 
1. **Entered stream mode and forgot exit**
   - You sent `MS` and the board is now streaming
   - It won't respond to other commands until you `R` (reset)
2. **Baud changed mid-session**
   - You sent `SR [code]` to change baud but the host is still at the old rate
   - The board switched, but your serial port didn't
   - You're now out of sync
3. **Board crashed or reset itself**
   - Some firmware has watchdog timers that reset on error
   - Send `R` or power-cycle to resync
4. **Buffer overflowed**
   - If you're not reading serial data fast enough, the buffer fills and the board stops talking
   - This is a host-side issue; send `R` to resync
**How to fix:**
 
```
- Always send R to exit any mode before trying new commands
- Match host baud if you used SR
- If in doubt, R (reset) and start over
- Don't let serial data pile up in the buffer; read it
```
 
---
 
## Flaky Touch (Intermittent Registration)
 
**What it means:** Touch works sometimes, but drops out or requires odd pressure.
 
**Causes:**
 
1. **Sensor is dirty or partially coupled**
   - Dust on the glass reduces capacitance
   - Protective film is partially peeling off
   - Clean the glass or reseat the film
2. **Baseline is stale**
   - The board learned the idle state when nothing was coupled properly
   - Send `CLE` (clear/calibrate) to re-baseline
   - Then test again
3. **Sensitivity is too high or too low**
   - Adjust with `SEN [level]` (0-31)
   - Lower number = more sensitive, higher = less sensitive
   - Start at 15 and adjust up/down
4. **Ground is marginal**
   - Shield floating or loosely seated
   - Verify continuity from sensor shield to board GND
5. **Sensor is capacitive but edge effect**
   - Touching the very edge of the glass sometimes couples poorly
   - Try the center first to rule out geometry issues
**How to fix:**
 
```
R                (reset)
CLE              (clear/re-baseline the sensor)
FT               (format tablet)
SEN 15           (set sensitivity to mid-range)
MS               (stream mode)
(test touch in center of glass)
R                (exit)
```
 
If still flaky, try `SEN 12` (more sensitive) or `SEN 18` (less) and test again.
 
---
 
## LED Keeps Blinking (Self-Test Stuck)
 
**What it means:** After power-up, the LED never stops flashing.
 
**Causes:**
 
1. **No sensor or sensor not coupled**
   - Board power-up self-test runs continuously
   - It expects all four corners to report a certain impedance
   - With no glass, all corners read "open" and the test fails forever
2. **Sensor is resistive, not capacitive**
   - Resistive panel corners don't couple capacitively
   - Board self-test can't find a valid sensor signature
3. **Board corner is broken**
   - One corner line is open
   - Self-test can't validate the sensor, keeps looping
4. **Firmware is stuck in a loop**
   - Rare, but bad flash can do it
   - Try `RD` (restore defaults) - if the board is responsive, it may reset the state
**How to fix:**
 
```
1. Check power - is the LED actually powered?
2. Verify sensor is plugged in and capacitive (FFC flex, not resistive wires)
3. If a known-good capacitive sensor still blinks, board may be faulty
4. If the board responds to Z/R commands, it's listening; try RD to clear state
```
 
Note: A blinking LED on power-up with no sensor is **normal** if the board was configured for "self-test on power-up" and no sensor is attached. If you're just testing the board itself, this is fine.
 
---
 
## DX = 2 but Touch Actually Works (Raw Signal is Good)
 
**What it means:** Format Raw shows all four corners responding to touch, but `DX` stubbornly returns `2`.
 
**Causes:**
 
1. **Stale power-up baseline**
   - Board powered on with no sensor; DX ran and locked in "no sensor"
   - Now the sensor is plugged in, but DX is stuck on old result
   - **Fix:** Power-cycle the board with sensor already connected, then run `diag`
2. **Threshold is strict**
   - Some firmware DX checks are picky about corner impedance values
   - Raw values are healthy, but DX's threshold doesn't like them
   - **Fix:** `CLE` to re-baseline, or try a known-good sensor if available
3. **Board variant or firmware quirk**
   - OEM firmware (Aristocrat, Wincor) sometimes has different DX logic
   - Touch may work fine even with DX=2 on these boards
   - **Fix:** Trust the Format Raw meter and actual touch, not DX
**What to do:**
- If Format Raw shows good signal and touch works, you can ignore DX=2
- If you want to clear it, try `CLE` (calibrate) or power-cycle with sensor already plugged in
---
 
## Controller Identification Error
 
**What it means:** `NM` or `OI` returns garbage or an unrecognized string.
 
**Causes:**
 
1. **Baud is slightly off**
   - ASCII replies garble at wrong baud
   - Reply looks like random bytes instead of text
   - **Fix:** Try the other common bauds (if not using auto-detect)
2. **Character encoding issue**
   - Rarely, high-bit characters appear in firmware strings
   - Most tools and terminals handle this fine
   - **Fix:** Just note the part number from the visible characters
3. **Board is dead but responding weakly**
   - Responds to `Z` but firmware string is corrupted
   - Usually means the flash is bad or partially erased
   - **Fix:** Try `RD` (restore defaults); if that doesn't help, board may be unrecoverable
---
 
## Summary: Quick Diagnostics Flowchart
 
```
1. Does Z return 0?
   NO  -> No power or wrong serial setup. Check baud, power, TX/RX.
   YES -> Continue.
 
2. Does R return 0?
   NO  -> Board is responding but not to reset. Try RD (restore defaults).
   YES -> Continue.
 
3. Does DX return 0 or 2?
   0   -> Sensor is good. Proceed to FT + MS for touch.
   2   -> Check if sensor is capacitive. If yes and you know it's good,
           power-cycle with sensor connected and re-run DX.
 
4. Does touch work in stream mode (FT + MS)?
   YES -> Done. System is working.
   NO  -> If DX=0, issue is software/format. Try CLE then FT+MS again.
          If DX=2, sensor type mismatch or not coupled.
 
5. Is the signal noisy?
   YES -> Check ground, use shielded cable, confirm baud. Use raw meter for filtering.
   NO  -> You're good.
```
 
---
 
## When All Else Fails
 
1. **Power cycle** the board (full off/on, wait 2 seconds)
2. **Send R** (reset) and wait for response
3. **Try RD** (restore defaults) to clear bad config
4. **Swap the serial cable** to rule out adapter failure
5. **Try a different host computer** to rule out driver issue
6. **Read the board's silkscreen** for any clues about its origin (Aristocrat, Wincor, etc.) and firmware variant
If none of that works, the board may be genuinely faulty. Capacitive touch controllers don't often fail gracefully, so a completely unresponsive board (or one that responds but ignores all commands) is usually end-of-life.
 
---
 
## Resources
 
- See **COMMANDS.md** for the full command reference
- See **README.md** for tool usage
- See **COMMANDS.md > Protocol Notes** for frame format and timing
