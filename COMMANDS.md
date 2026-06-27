# EXII Serial Commands Reference

Complete command reference for 3M MicroTouch EX II serial touch controllers (EX11/EX112 ASIC).

All commands are ASCII strings wrapped in `SOH` (0x01) ... `CR` (0x0D). Replies come back framed the same way.

---

## Response Codes

| Code | Meaning |
|------|---------|
| `0` | Command accepted / success |
| `1` | Invalid or unsupported command |
| `2` | Parameter error or diagnostic failure |

---

## Core Commands

### Z - Query / Null
**Description:** Check if controller is alive. Lowest-overhead ping.

**Request:** `Z`
**Response:** `0` (success)
**Use:** Auto-detection, sanity check

---

### R - Reset
**Description:** Soft reset the controller. Clears state, resets baud to default (if applicable), re-runs power-up self-test.

**Request:** `R`
**Response:** `0` (success)
**Use:** After power-up, before running diagnostics, to clear error states
**Note:** Always reset before talking to the board in a new session

---

## Identification Commands

### NM - Name / Firmware String
**Description:** Returns the board's firmware identity and version.

**Request:** `NM`
**Response:** ASCII string (e.g., `Wincor EXII-1050SC-02 v3.1` or `Aristocrat EXII-1715SC-02 v3.1`)
**Use:** Identify the exact board and firmware variant

---

### OI - Identity / Build Info
**Description:** Returns a compact identity code.

**Request:** `OI`
**Response:** 4-character hex string (e.g., `A31005`)
  - First 2 chars: board type
  - Last 2 chars: build / variant number
**Use:** Programmatic board identification

---

### UV - Features / Capabilities
**Description:** Returns a feature string describing the board's capabilities.

**Request:** `UV`
**Response:** ASCII string (e.g., `QMV***10`)
**Use:** Determine which modes/commands are supported

---

## Diagnostic Commands

### DX - Sensor Diagnostic
**Description:** Self-test: checks all four corner electrodes for continuity and proper coupling to the sensor glass.

**Request:** `DX`
**Response:** 
  - `0` - All four corners OK, sensor healthy
  - `2` - Open corner, broken wire, no sensor attached, or wrong sensor type
**Use:** Determine if sensor is physically present and properly wired
**Note:** This is the critical test for capacitive coupling. A persistent `2` with no touch response usually means wrong sensor type (resistive vs. capacitive) or a dead corner

---

## Format Commands

### FT - Format Tablet
**Description:** Set the output format to Tablet mode (5-byte packets with X/Y coordinates).

**Request:** `FT`
**Response:** `0` (success)
**Packet format:** `[sync] [X_lo] [X_hi] [Y_lo] [Y_hi]`
  - Sync byte: bit 7 = 1, bit 6 = touch flag (0 = up, 1 = down)
  - X/Y: 14-bit values (bits 0-6 of each byte are data bits, bit 7 is framing)
**Use:** Enable coordinate streaming
**Pair with:** `MS` (Mode Stream) to actually stream data

---

### FR - Format Raw
**Description:** Set the output format to raw impedance/capacitance readings (5 bytes per corner per frame).

**Request:** `FR`
**Response:** `0` (success)
**Data:** Streaming frame-by-frame raw I/Q values from all four corners
**Use:** Debug sensor coupling, check individual corner signals, build custom signal processing
**Note:** Raw data is noisy and requires filtering. Each corner reports an I/Q pair; magnitude = sqrt(I^2 + Q^2)

---

## Mode Commands

### MS - Mode Stream
**Description:** Enter streaming mode. Controller continuously sends touch data in the current format (FT or FR).

**Request:** `MS`
**Response:** `0` (success), then streaming begins
**Stream:** Continuous until `R` (reset) or timeout
**Use:** Get live touch coordinates or raw signal stream
**Requires:** `FT` or `FR` to set format first

---

### MR - Mode Report
**Description:** Single-report mode. Controller sends one packet on touch, then waits.

**Request:** `MR`
**Response:** `0` (success)
**Use:** Polled / event-driven touch detection (older apps)

---

## Configuration Commands

### RD - Restore Defaults
**Description:** Reset all settings to factory defaults.

**Request:** `RD`
**Response:** `0` (success)
**Use:** Clear garbage state, reset baud/parity to defaults, recover from bad config
**Side effect:** May change baud rate back to hardware default

---

### SR - Set Baud Rate
**Description:** Change the RS-232 baud rate.

**Request:** `SR [baud_code]`
**Baud codes:** 
  - `0` = 300
  - `1` = 600
  - `2` = 1200
  - `3` = 2400
  - `4` = 4800
  - `5` = 9600
  - `6` = 19200
**Response:** `0` (success), then controller switches to new baud
**Use:** Match host baud to controller
**Danger:** If you set the wrong baud, you'll lose comms. Use `RD` to recover

---

### SP - Set Parity
**Description:** Set RS-232 parity.

**Request:** `SP [mode]`
**Modes:**
  - `N` = None
  - `O` = Odd
  - `E` = Even
**Response:** `0` (success)
**Default:** None (N)

---

## Touch Sensitivity Commands

### SEN - Sensitivity
**Description:** Adjust touch threshold.

**Request:** `SEN [level]`
**Level:** 0-31 (0 = most sensitive, 31 = least)
**Response:** `0` (success)
**Use:** Tune out noise or make touch easier to register

---

### CLE - Clear / Calibrate
**Description:** Clear baseline and re-learn the idle state of all four corners.

**Request:** `CLE`
**Response:** `0` (success)
**Use:** After plugging in a new sensor, to baseline the board to the new glass's idle impedance

---

## Status / State Commands

### ST - Status
**Description:** Query controller status (power, sensing, mode, etc.).

**Request:** `ST`
**Response:** Status byte(s) (format varies by firmware)
**Use:** Check controller state without disrupting operation

---

## Utility Commands

### INC - Increment
**Description:** Increment an internal counter (test/debug only).

**Request:** `INC`
**Response:** Current count

---

### DEC - Decrement
**Description:** Decrement an internal counter (test/debug only).

**Request:** `DEC`
**Response:** Current count

---

## Command Interaction Examples

### Identify a board
```
Z       -> 0 (is it alive?)
R       -> 0 (reset)
NM      -> Aristocrat EXII-1715SC-02 v3.1
OI      -> A31005
UV      -> QMV***10
```

### Check sensor health
```
R       -> 0 (reset first)
DX      -> 0 (healthy) or 2 (problem)
```

### Stream touch coordinates
```
R       -> 0 (reset)
FT      -> 0 (set format to tablet)
MS      -> 0 (enter stream mode)
(now receiving 5-byte touch packets until R is sent)
R       -> 0 (exit stream mode)
```

### Stream raw sensor data
```
R       -> 0 (reset)
FR      -> 0 (set format to raw)
(now receiving raw I/Q data per frame)
R       -> 0 (exit)
```

---

## Protocol Notes

- **Frame wrapping:** Every command and reply is wrapped as `SOH <payload> CR`
- **Baud rates:** Default is 9600 8N1, but OEM firmware may use 2400 or other rates
- **Timeouts:** No response after ~1 second usually means wrong baud or command not supported
- **Case:** Commands are case-insensitive (Z, z, nM, nm all work)
- **Parameters:** Space-separated after command (e.g., `SP N` for no parity)

---

## Unsupported or Rare Commands

Some firmware variants may support:
- `TS` - Touch suppress / hysteresis
- `CS` - Corner sense / weighting
- `PT` - Power test / diagnostics
- `RS` - Run self-test (extended)

Check your firmware's `UV` response or try commands and look for `1` (unsupported).

---

## Tips

1. **Always reset first** - `R` before sending any other command after power-up
2. **Stream format matters** - `FT` for touch coords, `FR` for raw debugging
3. **DX is your friend** - If `DX` returns `2` with no touch response, it's sensor-type mismatch (resistive panel on a capacitive board), not a cable
4. **Baseline the glass** - `CLE` after connecting a new sensor to avoid stale idle readings
5. **Timeouts** - If commands hang, the baud rate is probably wrong; try sweeping 9600, 2400, 4800, 19200

---

## Firmware Variants

Different OEM firmware (Aristocrat, Wincor, etc.) may support slightly different command sets or parameters. Always check `NM` and `UV` to confirm what you're working with.

For official 3M documentation, consult:
- 3M MicroTouch technical reference (if you have it)
- The serial connector's silkscreen labels
- Your equipment's service manual

---

## Tool Shortcut Commands (v0.02+)

These are console shortcuts in `ex11_console.py`, not raw protocol commands:

| Shortcut | Action |
|----------|--------|
| `id` | Run the identity dump (R, Z, NM, OI, UV) |
| `diag` | Run the DX sensor self-test |
| `flash N` | Decode an LED power-on flash code (e.g. flash 5) |
| `recover` | Guided Restore Defaults recovery for power-on faults |
| `report [file]` | Full diagnostic snapshot, optionally saved to a file |
| `touch` | Stream decoded X/Y touch coordinates |
| `raw` | Cleaned live signal meter with baseline subtraction |
| `mon` | Raw hex byte monitor |
| `stats` | Capture ~4s of Format Raw and print per-channel min/max/mean/stdev |
| `log FILE.csv` | Begin logging raw/touch data to CSV |
| `log stop` | Stop logging and close the file |
| `log` | Show current logging status |
| `help` | Show the shortcut list |
| `q` | Quit |

### CSV Log Format

**Raw meter rows** (`raw` while logging):
```
timestamp,c0,c1,c2,c3
2026-06-24T14:32:15.123456,22000.0,190000.0,45000.0,198000.0
```

**Touch rows** (`touch` while logging):
```
timestamp,status,touch,x,y
2026-06-24T14:32:15.123456,193,1,8042,4096
```

### Stats Output

```
ex11> stats
=== Format Raw stats === collecting ~4s
  captured 312 frames, 4 channels

  ch         min       max      mean     stdev     range
  C0       21500     23100     22000       340      1600
  C1      189000    192000    190500       620      3000
  ...
```

A channel with a tiny range that never moves under touch is a dead/disconnected corner.
