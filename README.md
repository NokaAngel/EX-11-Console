# ex11-console

An interactive serial console and diagnostic tool for 3M MicroTouch EX II touch
controllers - the surface-capacitive serial boards built around the EX11 / EX112 ASIC
(e.g. 3M P/N `5406120`, firmware identities like `EXII-1715SC` / `EXII-1050SC`).

It wakes a board that looks dead, finds its baud rate, reads its identity, runs the
on-board sensor self-test, and gives you a live signal meter for chasing down
corner/sensor problems.

> These boards are silent until commanded and frequently ship at a non-default baud
> rate (2400 has been seen in gaming/POS OEM firmware, not the usual 9600). This tool
> probes every common rate automatically.

## What it does

- **Auto-detects the baud rate** by sending Z and watching for a framed reply
- **Identifies the board** with R, Z, NM (name string), OI (identity), UV (features)
- **Sensor diagnostic** with DX self-test (0 = healthy sensor, 2 = open corner / no / wrong sensor)
- **Live touch stream** - Format Tablet + Mode Stream, decoded to X/Y
- **Cleaned Format-Raw meter** - locks frame length, folds each corner's I/Q pair into one magnitude, smooths it, and subtracts an idle baseline so a real touch stands out from the noise
- **Raw command prompt** - type any command (NM, OI, RD, ...) and it gets SOH/CR-wrapped

## Power & Wiring

**Voltage:** 5V to 12V DC. Standard external supply is **+5V regulated**.

**Current:** 85 mA typical (110 mA max). Use a quality regulated power supply, not a wall wart; capacitive sensing is sensitive to noise.

**Ripple:** max 50 mV peak-to-peak.

**Connectors:**

- **JP3 (recommended):** 2-pin Molex power header
  - Square pad = Ground (return)
  - Other pin = +5V to +12V
  
- **JP1 (serial/power combo):** 7-pin Molex connector
  - Pin 6 = +5V to +12V
  - Pin 7 = Ground

**ESD grounding:** Connect the board's mounting hole nearest the sensor connector to chassis/earth ground by the shortest route.

**Safety:** Do not apply power to both JP3 and JP1 at the same time - dual sources can damage the controller.

## Quick start

```bash
pip install -r requirements.txt
python ex11_console.py COM7              # or /dev/ttyUSB0 on Linux/macOS
python ex11_console.py COM7 -t 1.0       # slower serial adapter
python ex11_console.py COM7 -b 2400      # skip auto-detect, force baud
```

### Command-line options

| Flag | Does |
|------|------|
| `port` | Serial port (e.g. `COM7`, `/dev/ttyUSB0`). Defaults to `COM7` |
| `-t`, `--timeout` | Per-reply read timeout in seconds (default `0.7`). Raise for slow adapters |
| `-b`, `--baud` | Force a baud rate and skip auto-detection |
| `--version` | Print version and exit |

On Windows, `pip install pyreadline3` enables command history and arrow-key editing in the prompt.

### Prompt commands

At the `ex11>` prompt:

| Type   | Does                                                              |
|--------|------------------------------------------------------------------|
| `id`   | Re-run the identity dump (R/Z/NM/OI/UV)                           |
| `diag` | Sensor self-test (DX)                                             |
| `flash N` | Decode an LED power-on flash code (e.g. `flash 5`)           |
| `recover` | Guided Restore Defaults recovery for power-on faults         |
| `report [file]` | Full diagnostic snapshot, optionally saved to a file   |
| `touch`| Stream decoded touch coordinates (needs a working sensor)        |
| `raw`  | Cleaned signal meter - keep hands off about 2 seconds, then press corners|
| `mon`  | Dump the raw byte stream as hex                                   |
| `stats`| Capture ~4 s of raw data and print per-channel min/max/mean/stdev |
| `log FILE.csv` | Start logging raw/touch data to a CSV file                |
| `log stop` | Stop logging and close the file                              |
| `help` | Show the full command list                                       |
| `NM` / `OI` / `RD` / ... | Send a raw command, get the framed reply              |
| `q`    | Quit                                                              |

### Logging data for analysis

```
ex11> log session1.csv     # start logging
ex11> raw                  # capture corner data while you test (Ctrl+C to stop)
ex11> log stop             # close the file
```

The CSV gets a timestamped row per frame (`raw`) or per touch packet (`touch`), ready for Excel, pandas, or matplotlib.

## More Info

- **[RELEASE_NOTES.md](RELEASE_NOTES.md)** - What's in v0.01, what's tested, known issues
- **[COMMANDS.md](COMMANDS.md)** - Full EXII protocol reference
- **[ERRORS.md](ERRORS.md)** - Troubleshooting and diagnostics guide

## Protocol notes

Commands are ASCII wrapped in SOH (0x01) ... CR (0x0D). Replies come back framed
the same way; <SOH>0<CR> (01 30 0D) means success. 

See [COMMANDS.md](COMMANDS.md) for the complete command reference - includes Z, R, NM, OI, UV, DX, FT, MS, FR, RD, 
and more, with examples and notes on each one.

See [ERRORS.md](ERRORS.md) for a troubleshooting guide - diagnose DX=2 failures, no response, garbled output, 
flaky touch, and common mistakes.

## Disclaimer

Built for hobbyist hardware recovery and reverse engineering of your own equipment. The
Format-Raw corner/IQ decoding is empirically derived and the I/Q pairing is inferred -
map corners by touch, don't trust the channel order blindly. No affiliation with 3M.

## License

MIT - see [LICENSE](LICENSE).
