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
## Quick start
 
```bash
pip install -r requirements.txt
python ex11_console.py COM7      # or /dev/ttyUSB0 on Linux/macOS
```
 
At the `ex11>` prompt:
 
| Type   | Does                                                              |
|--------|------------------------------------------------------------------|
| `id`   | Re-run the identity dump                                          |
| `diag` | Sensor self-test (DX)                                             |
| `touch`| Stream decoded touch coordinates (needs a working sensor)        |
| `mon`  | Dump the raw byte stream as hex                                   |
| `raw`  | Cleaned signal meter - keep hands off about 2 seconds, then press corners|
| `NM` / `OI` / `RD` / ... | Send a raw command, get the framed reply              |
| `q`    | Quit                                                              |
 
In the `raw` meter, each bar is one corner's deviation from rest. Press a corner; if its
bar jumps, that corner is sensing. A bar that never moves is an open/broken/unconnected
corner - or the panel is the wrong type for this controller (these boards are
capacitive-only; a resistive panel reports values but never responds to touch).
On Windows, press `b` to re-learn the baseline, `q` to quit.
 
## Protocol notes
 
Commands are ASCII wrapped in SOH (0x01) ... CR (0x0D). Replies come back framed
the same way; <SOH>0<CR> (01 30 0D) means success. Useful commands: R reset,
Z null/query, NM name, OI identity, UV features, DX diagnostic, FT format
tablet, MS mode stream, FR format raw, RD restore defaults.
 
## Disclaimer
 
Built for hobbyist hardware recovery and reverse engineering of your own equipment. The
Format-Raw corner/IQ decoding is empirically derived and the I/Q pairing is inferred -
map corners by touch, don't trust the channel order blindly. No affiliation with 3M.
 
## License
 
MIT - see [LICENSE](LICENSE).
