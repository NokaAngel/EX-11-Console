#!/usr/bin/env python3
"""
ex11_console.py - interactive console for 3M MicroTouch EX II serial controllers.

Target hardware: 3M P/N 5406120 (EX11 / EX112 ASIC), RS-232 surface-capacitive
controller. Default link is 9600 8N1, but OEM firmware may run at 2400 etc.

Protocol in one paragraph:
  * Commands you SEND are ASCII wrapped in SOH (0x01) ... CR (0x0D).
  * Replies you GET back are framed the same way: SOH <payload> CR.
  * <SOH>0<CR> (01 30 0D) means "success" for most commands.

Usage:
    python ex11_console.py                      # auto-detect on default port
    python ex11_console.py COM7                 # pick a port
    python ex11_console.py /dev/ttyUSB0 -t 1.0  # slower serial adapter
    python ex11_console.py COM7 -b 2400         # skip auto-detect, force baud
    python ex11_console.py --version

Requires: pyserial  ->  pip install pyserial
Optional: pyreadline3 on Windows for command history / arrow keys
          ->  pip install pyreadline3
"""

import sys
import os
import time
import math
import csv
import argparse
from datetime import datetime
from collections import Counter

__version__ = "0.02"

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed. Run:  pip install pyserial")

# Optional command history / arrow-key editing. Built in on Unix; pyreadline3 on Windows.
try:
    import readline
    HAVE_READLINE = True
except ImportError:
    HAVE_READLINE = False

PORT = "COM7"                       # default port if none given
SOH = 0x01
CR = 0x0D
BAUDS = [9600, 19200, 4800, 2400, 1200]   # 9600 is the EX II default; rest are fallbacks
READ_TIMEOUT = 0.7                  # default per-reply timeout (override with --timeout)
HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".ex11_console_history")


# ============================================================ CSV logging
class CsvLogger:
    """Lazily-headered CSV logger. write() takes a dict; header is set from the
       first row's keys, so raw-meter rows and touch rows can have different schemas."""
    def __init__(self):
        self.fh = None
        self.writer = None
        self.path = None
        self.rows = 0

    def start(self, path):
        if self.fh:
            self.stop()
        self.fh = open(path, "w", newline="")
        self.writer = None
        self.path = path
        self.rows = 0

    def write(self, row):
        if not self.fh:
            return
        if self.writer is None:
            self.writer = csv.DictWriter(self.fh, fieldnames=list(row.keys()))
            self.writer.writeheader()
        self.writer.writerow(row)
        self.rows += 1

    def stop(self):
        path, rows = self.path, self.rows
        if self.fh:
            try:
                self.fh.flush()
                self.fh.close()
            except Exception:
                pass
        self.fh = self.writer = self.path = None
        self.rows = 0
        return path, rows

    @property
    def active(self):
        return self.fh is not None


LOG = CsvLogger()
_HINTS_SHOWN = set()


def hint(key, msg):
    """Print an actionable hint once per session (deduped by key)."""
    if key in _HINTS_SHOWN:
        return
    _HINTS_SHOWN.add(key)
    print(f"  >> hint: {msg}")


# ============================================================ serial helpers
def open_port(port, baud):
    return serial.Serial(
        port, baudrate=baud, bytesize=8, parity="N", stopbits=1,
        timeout=0.2, rtscts=False, dsrdtr=False,
    )


def send(ser, cmd):
    """Frame an ASCII command as SOH<cmd>CR and write it."""
    frame = bytes([SOH]) + cmd.encode("ascii", "ignore") + bytes([CR])
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()


def read_response(ser, timeout=None):
    """Read one SOH..CR framed reply. Returns payload bytes (between SOH and CR), or None."""
    if timeout is None:
        timeout = READ_TIMEOUT
    end = time.time() + timeout
    buf = bytearray()
    started = False
    while time.time() < end:
        b = ser.read(1)
        if not b:
            continue
        v = b[0]
        if v == SOH:
            buf.clear()
            started = True
            continue
        if v == CR and started:
            return bytes(buf)
        if started:
            buf.append(v)
    return bytes(buf) if started else None


def command(ser, cmd, timeout=None):
    send(ser, cmd)
    return read_response(ser, timeout)


def show(label, payload):
    if payload is None:
        print(f"  {label:<14} (no response)")
    else:
        hexs = " ".join(f"{b:02X}" for b in payload)
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in payload)
        print(f"  {label:<14} HEX[{hexs}]  ASCII[{txt}]")


# ============================================================ frame decoding
def _decode_frame(frame):
    """Each channel reading is a 5-byte slot. Magnitude comes from the low 3 bytes,
       per the 3M Format Raw packing (bits 11-17 / 4-10 / 0-3)."""
    vals = []
    for i in range(0, len(frame) - 4, 5):
        b2 = frame[i + 2] & 0x7F
        b3 = frame[i + 3] & 0x7F
        b4 = frame[i + 4] & 0x0F
        vals.append((b2 << 11) | (b3 << 4) | b4)
    return vals


def _corner_magnitudes(frame):
    """Fold consecutive I/Q pairs into one magnitude per corner: sqrt(I^2 + Q^2).
       Pairing is inferred, so map corners empirically by touch."""
    vals = _decode_frame(frame)
    corners = []
    for i in range(0, len(vals) - 1, 2):
        corners.append(math.hypot(vals[i], vals[i + 1]))
    return corners


def _iter_frames(buf, gaps):
    """Yield (corners) for each complete, modal-length frame in buf.
       Returns leftover buffer. gaps is a Counter tracking the locked frame length."""
    syncs = [i for i, b in enumerate(buf) if b & 0x80]
    out = []
    if len(syncs) >= 2:
        for a, b in zip(syncs, syncs[1:]):
            gaps[b - a] += 1
        modal = gaps.most_common(1)[0][0]
        for a, b in zip(syncs, syncs[1:]):
            if b - a != modal:
                continue
            c = _corner_magnitudes(bytes(buf[a + 1:b]))
            if c:
                out.append(c)
        buf = bytearray(buf[syncs[-1]:])
    return out, buf


# ============================================================ routines
def autodetect(port, force_baud=None):
    """Find the baud rate by sending Z and watching for any framed reply.
       If force_baud is given, skip the sweep and just open at that rate."""
    bauds = [force_baud] if force_baud else BAUDS
    print(f"Probing {port} for an EX II controller...")
    for baud in bauds:
        try:
            ser = open_port(port, baud)
        except Exception as e:
            print(f"  cannot open {port} @ {baud}: {e}")
            hint("openport", "port busy or missing - close other terminals, check the COM number.")
            return None, None
        command(ser, "R", timeout=0.5)
        resp = command(ser, "Z", timeout=0.5)
        if resp is not None:
            print(f"  [OK] answered at {baud} baud  (Z -> {resp!r})")
            return ser, baud
        print(f"  ...nothing at {baud}")
        ser.close()
    return None, None


def identify(ser):
    print("\n=== Identity ===")
    show("Reset (R)",    command(ser, "R"))
    show("Query (Z)",    command(ser, "Z"))
    show("Name (NM)",    command(ser, "NM", timeout=1.2))
    show("Identity (OI)", command(ser, "OI", timeout=1.0))
    show("Features (UV)", command(ser, "UV", timeout=1.0))


def diagnostic(ser):
    """DX asks the controller to self-check the sensor (broken corners/wires)."""
    print("\n=== Sensor diagnostic (DX) ===")
    resp = command(ser, "DX", timeout=2.0)
    if resp is None:
        print("  No response (controller busy or DX unsupported).")
        hint("dxnone", "if you were just streaming, send 'R' first, then 'diag'.")
        return
    code = chr(resp[0]) if resp else "?"
    meaning = {
        "0": "OK - controller reports a healthy sensor.",
        "1": "Command not supported on this firmware.",
        "2": "FAILURE - broken corner/wire, no sensor, or wrong sensor type.",
    }.get(code, f"Unexpected response payload: {resp!r}")
    print(f"  DX -> '{code}'  =>  {meaning}")
    if code == "2":
        hint("dx2", "run 'raw' and press each corner. If bars move, it's sensing - "
                    "try 'CLE' to re-baseline or power-cycle with the sensor connected.")
        hint("dx2flash", "if the board LED is also flashing at power-up, that's a separate "
                         "controller self-test fault - count the flashes and run 'flash <count>'.")


# LED power-on flash codes, from 3M's EX II Serial Controllers Reference Guide (TSD-29087,
# "Table 2 LED Diagnostic Codes for EX II Controllers"). The controller flashes the LED
# at power-up if its self-test fails. Tuple = (name, what-to-do, nonrecoverable?).
POC_CODES = {
    1:  ("Reserved", "Reserved code - recount the flashes between pauses.", False),
    2:  ("Reserved", "Reserved code - recount the flashes between pauses.", False),
    3:  ("Setup error", "Could not establish operating range at power-up. Nonrecoverable - "
         "replace the controller. If it recurs on a new board, suspect the touch screen.", True),
    4:  ("Controller NOVRAM error", "Operating parameters in NOVRAM are invalid; running on "
         "defaults. Run 'recover' (Restore Defaults). If it persists, replace the controller "
         "(could also be a touch screen or cable problem).", False),
    5:  ("Hardware (HDW) error", "Controller hardware failed - it could not initialize or load "
         "its program. Nonrecoverable per 3M; replace the controller.", True),
    6:  ("Reserved", "Reserved code - recount the flashes between pauses.", False),
    7:  ("Cable NOVRAM error", "Linearization data in the CABLE NOVRAM is invalid. The LED "
         "flashes until the controller receives any valid command from the host - which this "
         "tool sends, so it may stop once you connect. Re-linearize / replace the cable.", False),
    8:  ("Controller linearization error", "Controller linearization data in NOVRAM is invalid. "
         "Replace the touch screen or perform a 25-point linearization; contact 3M support.", True),
    9:  ("Reserved", "Reserved code - recount the flashes between pauses.", False),
    10: ("EEPROM not formatted", "Controller EEPROM is not formatted. Reload program code.", True),
    11: ("Invalid controller block 5", "Not applicable to serial controllers.", False),
    12: ("Invalid controller block 6", "Restore Defaults if possible, otherwise replace the controller.", False),
}


def interpret_flash(n):
    """Decode an observed LED power-on flash count using 3M's EX II Table 2."""
    print(f"\n=== LED power-on flash code: {n} ===")
    if n <= 0:
        print("  Steady dim / no flashing = self-test passed (normal).")
        return
    if n in POC_CODES:
        name, action, fatal = POC_CODES[n]
        print(f"  {n} flashes  ->  {name}")
        print(f"  Fix      : {action}")
        print(f"  Severity : {'NONRECOVERABLE per 3M - replace controller' if fatal else 'recoverable - try the fix above'}")
    else:
        print(f"  {n} is outside the EX II table (codes 1-12). Recount between the pauses.")
    print("  (This is the CONTROLLER power-on self-test - separate from the DX sensor test.)")
    if n == 5:
        print("  NOTE: code 5 means 'could not load program', yet if your board still answers")
        print("        NM/OI it clearly DID load - so recount; adjacent code 4 (NOVRAM) is")
        print("        recoverable with 'recover' and fits a board that still communicates.")


def recover(ser):
    """3M-documented recovery for configuration/NOVRAM power-on faults:
       Restore Defaults, reset, then re-run the sensor diagnostic."""
    print("\n=== Guided recovery (Restore Defaults) ===")
    print("  Documented fix for config/NOVRAM power-on faults. Won't fix true hardware faults.")
    show("Reset (R)",        command(ser, "R", timeout=1.0))
    show("Restore Defaults", command(ser, "RD", timeout=2.0))
    time.sleep(0.3)
    show("Reset (R)",        command(ser, "R", timeout=1.0))
    diagnostic(ser)
    print("\n  Next: power-cycle the board and recount the LED flashes.")
    print("  If the same flash code returns after Restore Defaults AND a power-cycle,")
    print("  the fault is in hardware (NOVRAM/analog) - the board itself is bad.")


def report(ser, path=None):
    """Collect a full diagnostic snapshot; optionally save it to a text file."""
    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    out("=== ex11-console diagnostic report ===")
    out(f"time: {datetime.now().isoformat()}")
    for label, cmd, to in [("name (NM)", "NM", 1.2), ("identity (OI)", "OI", 1.0),
                           ("features (UV)", "UV", 1.0)]:
        r = command(ser, cmd, timeout=to)
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in r) if r else "(no response)"
        out(f"{label}: {txt}")
    dxr = command(ser, "DX", timeout=2.0)
    dxc = chr(dxr[0]) if dxr else "?"
    dxmean = {"0": "sensor OK", "1": "DX unsupported", "2": "sensor FAIL / wrong type"}.get(dxc, "?")
    out(f"DX: {dxc} ({dxmean})")
    out("")
    out("If the board LED is flashing at power-up, count the flashes and run:  flash <count>")
    out("Recommended next step if DX=2 or the LED is flashing: run 'recover'.")
    if path:
        try:
            with open(path, "w") as f:
                f.write("\n".join(lines) + "\n")
            print(f"\n  saved report -> {path}")
        except Exception as e:
            print(f"\n  could not save report: {e}")


def touch_monitor(ser):
    """Format Tablet + Mode Stream: decode 5-byte touch packets (needs a real sensor)."""
    print("\n=== Touch stream (Format Tablet / Mode Stream) ===")
    if LOG.active:
        print(f"  (logging to {LOG.path})")
    command(ser, "R")
    time.sleep(0.1)
    command(ser, "FT")
    command(ser, "MS")
    print("Touch the sensor. Ctrl+C to stop.\n")
    try:
        while True:
            b = ser.read(1)
            if not b:
                continue
            status = b[0]
            if not (status & 0x80):
                continue
            rest = ser.read(4)
            if len(rest) < 4:
                continue
            xlo, xhi, ylo, yhi = rest[0], rest[1], rest[2], rest[3]
            x = (xlo & 0x7F) | ((xhi & 0x7F) << 7)
            y = (ylo & 0x7F) | ((yhi & 0x7F) << 7)
            touch = bool(status & 0x40)
            state = "DOWN" if touch else "up  "
            print(f"  status={status:02X} [{state}]  X={x:5d}  Y={y:5d}")
            if LOG.active:
                LOG.write({"timestamp": datetime.now().isoformat(),
                           "status": status, "touch": int(touch), "x": x, "y": y})
    except KeyboardInterrupt:
        command(ser, "R")
        print("\n  stopped, controller reset.")


def raw_monitor(ser):
    """Dumb live view of whatever bytes arrive. Good 'is it alive' check."""
    print("\n=== Raw byte monitor === (Ctrl+C to stop)\n")
    try:
        while True:
            data = ser.read(64)
            if not data:
                continue
            bar = "#" * min(len(data), 50)
            hexs = " ".join(f"{b:02X}" for b in data[:16])
            print(f"  {len(data):3d} bytes |{bar:<50}| {hexs}")
    except KeyboardInterrupt:
        print("\n  stopped.")


def raw_meter(ser):
    """Cleaned Format Raw meter: frame-length lock, I/Q fold, EMA smoothing,
       idle-baseline subtraction. Optionally logs each frame to CSV."""
    os.system("")                      # enable ANSI escapes on Win10+ terminals
    try:
        import msvcrt
    except ImportError:
        msvcrt = None

    ALPHA = 0.30
    BASE_SECS = 2.0
    WIDTH = 46

    print("\n=== Format Raw meter (cleaned) ===  Ctrl+C to stop")
    if LOG.active:
        print(f"  (logging to {LOG.path})")
    print("Keep hands OFF the glass while it learns the baseline...")
    command(ser, "R")
    time.sleep(0.2)
    send(ser, "FR")
    time.sleep(0.2)
    ser.reset_input_buffer()

    buf = bytearray()
    gaps = Counter()
    ema = None
    baseline = None
    base_acc = []
    span = 1.0
    last_draw = 0.0
    t0 = time.time()

    def reset_baseline():
        nonlocal baseline, base_acc, t0
        baseline, base_acc, t0 = None, [], time.time()
        print("\n(relearning baseline - hands off)")

    try:
        while True:
            chunk = ser.read(256)
            if chunk:
                buf.extend(chunk)

            frames, buf = _iter_frames(buf, gaps)
            for corners in frames:
                ema = corners if ema is None else \
                    [ALPHA * c + (1 - ALPHA) * e for c, e in zip(corners, ema)]
                if baseline is None and (time.time() - t0) < BASE_SECS:
                    base_acc.append(ema[:])
                elif baseline is None and base_acc:
                    n = len(base_acc)
                    baseline = [sum(col) / n for col in zip(*base_acc)]
                if LOG.active:
                    row = {"timestamp": datetime.now().isoformat()}
                    for i, c in enumerate(corners):
                        row[f"c{i}"] = round(c, 1)
                    LOG.write(row)

            if msvcrt and msvcrt.kbhit():
                k = msvcrt.getch().lower()
                if k == b"q":
                    break
                if k == b"b":
                    reset_baseline()

            now = time.time()
            if ema and (now - last_draw) > 0.12:
                last_draw = now
                out = []
                if baseline is None:
                    out.append("learning baseline... keep hands off\n")
                    deltas = [0.0] * len(ema)
                else:
                    out.append("Touch each corner. Bar = change from rest.  [b]=rebaseline [q]=quit\n")
                    deltas = [e - b for e, b in zip(ema, baseline)]
                span = max(span * 0.995, max((abs(d) for d in deltas), default=1.0), 1.0)
                for idx, (e, d) in enumerate(zip(ema, deltas)):
                    n = int(WIDTH * min(abs(d) / span, 1.0))
                    sign = "+" if d >= 0 else "-"
                    tag = "  <== TOUCH" if abs(d) > span * 0.35 and baseline else ""
                    out.append(f"C{idx}  {sign}{abs(d):7.0f}  |{'#' * n:<{WIDTH}}|{tag}")
                logline = f"  [logging {LOG.rows} rows]" if LOG.active else ""
                out.append(f"\nbaseline {'set' if baseline else '...'}{logline}   abs: " +
                           " ".join(f"{v:.0f}" for v in ema))
                sys.stdout.write("\033[H\033[J" + "\n".join(out) + "\n")
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        command(ser, "R")
        print("\n  reset out of raw mode.")


def stats(ser, seconds=4.0):
    """Capture Format Raw for a few seconds and print per-channel min/max/mean/stdev.
       Hold still for a baseline read, or touch a corner to see its range jump."""
    print(f"\n=== Format Raw stats === collecting ~{seconds:.0f}s (Ctrl+C to cut short)")
    command(ser, "R")
    time.sleep(0.2)
    send(ser, "FR")
    time.sleep(0.2)
    ser.reset_input_buffer()

    buf = bytearray()
    gaps = Counter()
    samples = []
    t0 = time.time()
    try:
        while time.time() - t0 < seconds:
            chunk = ser.read(256)
            if chunk:
                buf.extend(chunk)
            frames, buf = _iter_frames(buf, gaps)
            samples.extend(frames)
    except KeyboardInterrupt:
        pass
    command(ser, "R")

    if not samples:
        print("  no frames captured (wrong baud, or no FR data).")
        return
    nch = min(len(s) for s in samples)
    print(f"  captured {len(samples)} frames, {nch} channels\n")
    print(f"  {'ch':<5}{'min':>10}{'max':>10}{'mean':>10}{'stdev':>10}{'range':>10}")
    for ci in range(nch):
        col = [s[ci] for s in samples]
        mn, mx = min(col), max(col)
        mean = sum(col) / len(col)
        sd = (sum((x - mean) ** 2 for x in col) / len(col)) ** 0.5
        print(f"  C{ci:<4}{mn:>10.0f}{mx:>10.0f}{mean:>10.0f}{sd:>10.0f}{mx - mn:>10.0f}")
    print("\n  Tip: a flat channel (tiny range) that never moves on touch is a dead corner.")


# ============================================================ REPL
HELP = """
Commands (anything else is sent raw, SOH/CR-wrapped):
  id            re-run the identity dump (R/Z/NM/OI/UV)
  diag          sensor self-test (DX)
  flash N       decode an LED power-on flash code (e.g. 'flash 5')
  recover       guided Restore Defaults recovery for power-on faults
  report [file] full diagnostic snapshot, optionally saved to a text file
  touch         stream decoded X/Y touch coordinates
  raw           cleaned live signal meter (press corners)
  mon           dump the raw byte stream as hex
  stats         capture ~4s of raw data, print per-channel min/max/mean/stdev
  log FILE.csv  start logging raw/touch data to a CSV file
  log stop      stop logging and close the file
  log           show current logging status
  help          show this help
  q             quit
Raw commands: Z R NM OI UV DX FT MS FR RD CLE SEN ...
"""


def handle_log(line):
    parts = line.split(maxsplit=1)
    if len(parts) == 1:
        print(f"  logging: {LOG.path} ({LOG.rows} rows)" if LOG.active else "  logging: off")
        return
    arg = parts[1].strip()
    if arg.lower() == "stop":
        path, rows = LOG.stop()
        print(f"  stopped logging -> {path} ({rows} rows)" if path else "  not currently logging")
        return
    try:
        LOG.start(arg)
        print(f"  logging to {arg}  (run 'raw' or 'touch' to capture; 'log stop' to end)")
    except Exception as e:
        print(f"  cannot open log file: {e}")


def repl(ser):
    print("\n=== Interactive console ===  (type 'help' for commands)")
    print("  Shortcuts:  id | diag | flash N | recover | report | touch | raw | stats | log | q")
    if not HAVE_READLINE:
        print("  (tip: pip install pyreadline3 for command history / arrow keys on Windows)")
    while True:
        try:
            line = input("ex11> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        low = line.lower()
        if low in ("q", "quit", "exit"):
            break
        if low in ("help", "?"):
            print(HELP); continue
        if low == "id":
            identify(ser); continue
        if low == "diag":
            diagnostic(ser); continue
        if low.startswith("flash"):
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit():
                interpret_flash(int(parts[1]))
            else:
                print("  usage: flash <count>   (e.g. 'flash 5' for a 5-blink code)")
            continue
        if low == "recover":
            recover(ser); continue
        if low.startswith("report"):
            parts = line.split(maxsplit=1)
            report(ser, parts[1].strip() if len(parts) > 1 else None); continue
        if low == "touch":
            touch_monitor(ser); continue
        if low == "mon":
            raw_monitor(ser); continue
        if low == "raw":
            raw_meter(ser); continue
        if low == "stats":
            stats(ser); continue
        if low.startswith("log"):
            handle_log(line); continue
        resp = command(ser, line.upper())
        show(line.upper(), resp)
        if resp is None:
            hint("noreply", "no reply - wrong baud, or the board is mid-stream. "
                            "Send 'R', or restart with -t 1.0 for a slow adapter.")
        elif resp == b"1":
            hint("unsupported", "'1' means this firmware doesn't support that command.")


# ============================================================ main
def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="ex11_console",
        description="Interactive serial console for 3M MicroTouch EX II touch controllers.")
    p.add_argument("port", nargs="?", default=PORT,
                   help=f"serial port (default: {PORT})")
    p.add_argument("-t", "--timeout", type=float, default=READ_TIMEOUT,
                   help=f"per-reply read timeout in seconds (default: {READ_TIMEOUT})")
    p.add_argument("-b", "--baud", type=int, default=None,
                   help="force a baud rate and skip auto-detection")
    p.add_argument("--version", action="version",
                   version=f"ex11-console {__version__}")
    return p.parse_args(argv)


def main(argv=None):
    global READ_TIMEOUT
    args = parse_args(argv if argv is not None else sys.argv[1:])
    READ_TIMEOUT = args.timeout

    if HAVE_READLINE:
        try:
            readline.read_history_file(HISTORY_FILE)
        except (FileNotFoundError, OSError):
            pass

    ser, baud = autodetect(args.port, force_baud=args.baud)
    if ser is None:
        print("\nNo controller found.")
        print("Check, in order:")
        print("  1. Is the board actually powered? (separate +5V/+12V pins, not just TX/RX/GND)")
        print("  2. TX<->RX swapped? Try crossing data lines.")
        print("  3. Correct port / not held open by another program?")
        print("  4. Slow USB-serial adapter? Try:  --timeout 1.0")
        return 1

    try:
        identify(ser)
        diagnostic(ser)
        print("\n  If the board's LED is flashing at power-up, count the flashes and run "
              "'flash <count>' to decode the controller self-test fault.")
        repl(ser)
    finally:
        if LOG.active:
            path, rows = LOG.stop()
            print(f"  (closed log {path}, {rows} rows)")
        ser.close()
        if HAVE_READLINE:
            try:
                readline.set_history_length(1000)
                readline.write_history_file(HISTORY_FILE)
            except OSError:
                pass
        print("Port closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
