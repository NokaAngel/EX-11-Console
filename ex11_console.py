#!/usr/bin/env python3
"""
ex11_console.py - interactive console for 3M MicroTouch EX II serial controllers.

Target hardware: 3M P/N 5406120 = EXII-1050SC (EX11 / EX112 ASIC),
                 RS-232 surface-capacitive controller. Default = 9600 8N1.

Protocol in one paragraph:
  * Commands you SEND are ASCII wrapped in SOH (0x01) ... CR (0x0D).
  * Replies you GET back are framed the same way: SOH <payload> CR.
  * <SOH>0<CR> (01 30 0D) means "success" for most commands.

Usage:
    python ex11_console.py            # uses PORT below
    python ex11_console.py COM7       # or pass a port explicitly
    python ex11_console.py /dev/ttyUSB0

Requires: pyserial  ->  pip install pyserial
"""

import sys
import time
import math
from collections import Counter

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed. Run:  pip install pyserial")

PORT = "COM7"                       # <-- change to your port
SOH = 0x01
CR = 0x0D
BAUDS = [9600, 19200, 4800, 2400, 1200]   # 9600 is the EX II default; rest are fallbacks


# ----------------------------------------------------------------------------- helpers
def open_port(port, baud):
    return serial.Serial(
        port, baudrate=baud, bytesize=8, parity="N", stopbits=1,
        timeout=0.3, rtscts=False, dsrdtr=False,
    )


def send(ser, cmd):
    """Frame an ASCII command as SOH<cmd>CR and write it."""
    frame = bytes([SOH]) + cmd.encode("ascii", "ignore") + bytes([CR])
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()


def read_response(ser, timeout=0.7):
    """Read one SOH..CR framed reply. Returns payload bytes (between SOH and CR), or None."""
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


def command(ser, cmd, timeout=0.7):
    send(ser, cmd)
    return read_response(ser, timeout)


def show(label, payload):
    if payload is None:
        print(f"  {label:<14} (no response)")
    else:
        hexs = " ".join(f"{b:02X}" for b in payload)
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in payload)
        print(f"  {label:<14} HEX[{hexs}]  ASCII[{txt}]")


# ----------------------------------------------------------------------------- routines
def autodetect(port):
    """Find the baud rate by sending Z (null/query) and watching for any framed reply."""
    print(f"Probing {port} for an EX II controller...")
    for baud in BAUDS:
        try:
            ser = open_port(port, baud)
        except Exception as e:
            print(f"  cannot open {port} @ {baud}: {e}")
            return None, None
        # send Reset first (3M recommends it on power-up), then Z to confirm comms
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
        return
    code = chr(resp[0]) if resp else "?"
    meaning = {
        "0": "OK - controller reports a healthy sensor.",
        "1": "Command not supported on this firmware.",
        "2": "FAILURE - broken corner/wire or NO SENSOR attached.",
    }.get(code, f"Unexpected response payload: {resp!r}")
    print(f"  DX -> '{code}'  =>  {meaning}")


def touch_monitor(ser):
    """Format Tablet + Mode Stream: decode the 5-byte touch packets (needs a real sensor)."""
    print("\n=== Touch stream (Format Tablet / Mode Stream) ===")
    command(ser, "R")
    time.sleep(0.1)
    command(ser, "FT")   # 5-byte packets
    command(ser, "MS")   # stream while touched
    print("Touch the sensor. Ctrl+C to stop.\n")
    try:
        while True:
            b = ser.read(1)
            if not b:
                continue
            status = b[0]
            if not (status & 0x80):          # sync byte has bit7 = 1
                continue
            rest = ser.read(4)
            if len(rest) < 4:
                continue
            xlo, xhi, ylo, yhi = rest[0], rest[1], rest[2], rest[3]
            x = (xlo & 0x7F) | ((xhi & 0x7F) << 7)   # 14-bit X
            y = (ylo & 0x7F) | ((yhi & 0x7F) << 7)   # 14-bit Y
            touch = bool(status & 0x40)              # proximity bit (best-effort)
            state = "DOWN" if touch else "up  "
            print(f"  status={status:02X} [{state}]  X={x:5d}  Y={y:5d}")
    except KeyboardInterrupt:
        command(ser, "R")
        print("\n  stopped, controller reset.")


def raw_monitor(ser):
    """Dumb live view of whatever bytes arrive, with a crude activity bar. Good 'is it alive' check."""
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


def _split_frames(buf):
    """Split the FR byte stream on sync bytes (high bit set). Data bytes are < 0x80;
       the controller emits a sync byte (e.g. 0x80) at each frame boundary.
       Returns (list_of_frames, leftover_buffer)."""
    syncs = [i for i, b in enumerate(buf) if b & 0x80]
    if len(syncs) < 2:
        return [], buf
    frames = [bytes(buf[a + 1:b]) for a, b in zip(syncs, syncs[1:])]
    return frames, bytearray(buf[syncs[-1]:])   # keep last partial frame


def _decode_frame(frame):
    """Each channel reading is a 5-byte slot. Magnitude comes from the low 3 bytes,
       per the 3M Format Raw packing (bits 11-17 / 4-10 / 0-3). The first 2 bytes of
       each slot are high/sign bytes that tend to sit near a rail; we ignore them for
       the magnitude bar so opens/shorts don't hide behind I/Q artifacts."""
    vals = []
    for i in range(0, len(frame) - 4, 5):
        b2 = frame[i + 2] & 0x7F
        b3 = frame[i + 3] & 0x7F
        b4 = frame[i + 4] & 0x0F
        vals.append((b2 << 11) | (b3 << 4) | b4)
    return vals


def _corner_magnitudes(frame):
    """Decode a frame's channels and fold consecutive I/Q pairs into one stable
       magnitude per corner: mag = sqrt(I**2 + Q**2). Pairing is inferred from the
       observed low/high alternation, so map corners empirically by touch."""
    vals = _decode_frame(frame)
    corners = []
    for i in range(0, len(vals) - 1, 2):
        corners.append(math.hypot(vals[i], vals[i + 1]))
    return corners


def raw_meter(ser):
    """Cleaned Format Raw meter.

    Noise handling, in order:
      1. Lock onto the modal frame length and DROP frames that don't match
         (kills the wild values from mis-aligned/corrupt frames).
      2. Fold each corner's I/Q pair into a single magnitude (steadier than raw I or Q).
      3. Exponential moving average to smooth frame-to-frame jitter.
      4. Subtract an idle baseline so a touch reads as a clear deviation instead of
         being lost under the resting offset.

    Keep hands off the glass for the ~2 s baseline grab, then press each corner.
    On Windows you can press 'b' to re-learn the baseline, 'q' to quit.
    """
    import os
    os.system("")                      # enable ANSI escapes on Win10+ terminals
    try:
        import msvcrt                  # optional live keys on Windows
    except ImportError:
        msvcrt = None

    ALPHA = 0.30                       # EMA smoothing (lower = smoother/slower)
    BASE_SECS = 2.0                    # how long to average the idle baseline
    WIDTH = 46

    print("\n=== Format Raw meter (cleaned) ===  Ctrl+C to stop")
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

            syncs = [i for i, b in enumerate(buf) if b & 0x80]
            if len(syncs) >= 2:
                for a, b in zip(syncs, syncs[1:]):
                    gaps[b - a] += 1
                modal = gaps.most_common(1)[0][0]          # locked frame length
                for a, b in zip(syncs, syncs[1:]):
                    if b - a != modal:
                        continue                            # drop off-length frames
                    corners = _corner_magnitudes(bytes(buf[a + 1:b]))
                    if not corners:
                        continue
                    ema = corners if ema is None else \
                        [ALPHA * c + (1 - ALPHA) * e for c, e in zip(corners, ema)]
                    if baseline is None and (time.time() - t0) < BASE_SECS:
                        base_acc.append(ema[:])
                    elif baseline is None and base_acc:
                        n = len(base_acc)
                        baseline = [sum(col) / n for col in zip(*base_acc)]
                buf = bytearray(buf[syncs[-1]:])

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
                out.append(f"\nbaseline {'set' if baseline else '...'}   abs: " +
                           " ".join(f"{v:.0f}" for v in ema))
                sys.stdout.write("\033[H\033[J" + "\n".join(out) + "\n")
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        command(ser, "R")
        print("\n  reset out of raw mode.")


def repl(ser):
    print("\n=== Interactive console ===")
    print("  Type a raw command (Z R NM OI UV DX FT MS FR RD ...) and it gets SOH/CR-wrapped.")
    print("  Shortcuts:  id  |  diag  |  touch  |  mon  |  raw  |  q")
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
        if low == "id":
            identify(ser); continue
        if low == "diag":
            diagnostic(ser); continue
        if low == "touch":
            touch_monitor(ser); continue
        if low == "mon":
            raw_monitor(ser); continue
        if low == "raw":
            raw_meter(ser); continue
        show(line.upper(), command(ser, line.upper()))


# ----------------------------------------------------------------------------- main
def main():
    port = sys.argv[1] if len(sys.argv) > 1 else PORT
    ser, baud = autodetect(port)
    if ser is None:
        print("\nNo controller found on any baud rate.")
        print("Check, in order:")
        print("  1. Is the board actually powered? (separate +5V/+12V pins, not just TX/RX/GND)")
        print("  2. TX<->RX swapped? Try crossing data lines.")
        print("  3. Correct COM port / not held open by another program?")
        return
    identify(ser)
    diagnostic(ser)
    repl(ser)
    ser.close()
    print("Port closed.")


if __name__ == "__main__":
    main()
