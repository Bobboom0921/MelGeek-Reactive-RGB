from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Iterable

import hid


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"

VID = 0x3854
PID = 0x040F
RAW_USAGE_PAGE = 0xFF60
RAW_USAGE = 0x61
REPORT_SIZE = 65
KEY_NAMES = {31: "A", 36: "H", 61: "Space", 62: "Space2", 63: "Space3"}

INIT_PACKETS: tuple[tuple[int, int, bytes], ...] = (
    (0x0A, 0x82, bytes([0x01, 0x32, 0x32, 0x01, 0x00, 0x20, 0x01])),
    (0x0A, 0x82, bytes([0x01, 0x32, 0x32, 0x00, 0x00, 0x20, 0x01])),
    (0x0A, 0x80, bytes([0x01, 0x20, 0x82, 0x00, 0x82, 0x00])),
    (0x0A, 0x80, bytes([0x01, 0x20, 0x96, 0x00, 0x96, 0x00])),
    (0x0A, 0x82, bytes([0x01, 0x32, 0x32, 0x00, 0x00, 0x20, 0x00])),
    (0x0A, 0x93, bytes([0x02])),
)
QUERY_PACKET = (0x0A, 0x93, bytes([0x02]))


def crc16_ccitt_false(data: bytes, init: int = 0xFFFF) -> int:
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def make_packet(report_prefix: int, command: int, payload: bytes) -> bytes:
    if len(payload) > 56:
        raise ValueError("payload too long")
    packet = bytearray(REPORT_SIZE)
    packet[0] = 0x00
    packet[1] = report_prefix
    packet[2] = command
    packet[3] = len(payload)
    packet[9 : 9 + len(payload)] = payload
    crc = crc16_ccitt_false(payload)
    packet[7:9] = crc.to_bytes(2, "little")
    return bytes(packet)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def melgeek_devices() -> list[dict]:
    return list(hid.enumerate(VID, PID))


def describe_device(index: int, dev: dict) -> str:
    return (
        f"#{index} product={dev.get('product_string')!r} "
        f"usage_page=0x{int(dev.get('usage_page') or 0):04X} "
        f"usage=0x{int(dev.get('usage') or 0):04X} "
        f"interface={dev.get('interface_number')} path={dev.get('path')!r}"
    )


def choose_device(index: int | None = None) -> dict:
    devices = melgeek_devices()
    if not devices:
        raise RuntimeError("No MelGeek HID device found")
    if index is not None:
        try:
            return devices[index]
        except IndexError as exc:
            raise RuntimeError(f"Device index out of range: {index}") from exc
    for dev in devices:
        if dev.get("usage_page") == RAW_USAGE_PAGE and dev.get("usage") == RAW_USAGE:
            return dev
    raise RuntimeError("MelGeek raw HID pressure interface not found")


def open_device(dev_info: dict) -> hid.device:
    handle = hid.device()
    handle.open_path(dev_info["path"])
    handle.set_nonblocking(False)
    return handle


def write_command(handle: hid.device, report_prefix: int, command: int, payload: bytes) -> bool:
    packet = make_packet(report_prefix, command, payload)
    return handle.write(packet) > 0


def send_init(handle: hid.device, delay_s: float) -> tuple[int, int]:
    ok = 0
    for report_prefix, command, payload in INIT_PACKETS:
        try:
            if write_command(handle, report_prefix, command, payload):
                ok += 1
        except OSError as exc:
            print(f"WARN init command 0x{command:02X} failed: {exc}", flush=True)
        time.sleep(delay_s)
    return ok, len(INIT_PACKETS)


def with_report_id(report: Iterable[int]) -> bytes:
    raw = bytes(report)
    if not raw:
        return raw
    # hidapi on Windows commonly returns the report ID as byte 0. If it returns
    # only the WebHID data bytes, prepend report ID 0 so the decoder has one shape.
    if len(raw) >= 9 and raw[1] in (0x08, 0x0A, 0x0F):
        return raw
    if len(raw) >= 8 and raw[0] in (0x08, 0x0A, 0x0F):
        return bytes([0x00]) + raw
    return raw


def decode_pressure_report(report: Iterable[int], full_delta: float) -> list[dict] | None:
    raw = with_report_id(report)
    if len(raw) < 9 or raw[1] != 0x08 or raw[2] != 0x09:
        return None
    payload_len = raw[3]
    out: list[dict] = []
    for offset in range(9, min(len(raw), 9 + payload_len) - 3, 4):
        raw_id = raw[offset] | (raw[offset + 1] << 8)
        key_id = raw_id & 0xFF
        depth_code = raw_id >> 8
        value = raw[offset + 2] | (raw[offset + 3] << 8)
        if raw_id or value:
            out.append(
                {
                    "keyId": key_id,
                    "key": KEY_NAMES.get(key_id, str(key_id)),
                    "value": value,
                    "depthCode": depth_code,
                    "pressureDepth": clamp01(depth_code / 48.0),
                }
            )
    return out


class PressureNormalizer:
    def __init__(self, full_delta: float) -> None:
        self.full_delta = max(1.0, full_delta)
        self.baseline: dict[int, int] = {}
        self.latest: dict[int, dict] = {}

    def enrich(self, samples: list[dict]) -> list[dict]:
        changed: list[dict] = []
        for sample in samples:
            key_id = int(sample["keyId"])
            value = int(sample["value"])
            self.baseline.setdefault(key_id, value)
            delta = value - self.baseline[key_id]
            sample["delta"] = delta
            sample["pressureValue"] = clamp01((-delta) / self.full_delta)
            sample["pressure"] = sample["pressureValue"]
            sample["down"] = sample["pressure"] >= 0.02
            self.latest[key_id] = sample
            changed.append(sample)
        return changed

    def ranked(self) -> list[dict]:
        return sorted(
            self.latest.values(),
            key=lambda item: max(abs(float(item.get("delta", 0))), float(item.get("pressure", 0.0)) * self.full_delta),
            reverse=True,
        )


def write_jsonl(handle, row: dict) -> None:  # noqa: ANN001
    line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
    print(line, flush=True)
    if handle is not None:
        handle.write(line + "\n")
        handle.flush()


def run_probe(args: argparse.Namespace) -> int:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    dev_info = choose_device(args.device_index)
    print("Using " + describe_device(melgeek_devices().index(dev_info), dev_info), flush=True)

    jsonl_path = Path(args.jsonl)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_file = jsonl_path.open("w", encoding="utf-8") if args.jsonl else None
    normalizer = PressureNormalizer(args.full_delta)
    rows = 0
    press_rows = 0
    last_emit = 0.0
    last_query = 0.0
    last_status = 0.0
    deadline = None if args.seconds <= 0 else time.time() + args.seconds

    try:
        handle = open_device(dev_info)
    except OSError as exc:
        raise RuntimeError(f"Failed to open raw HID device: {exc}") from exc

    try:
        if not args.no_init:
            ok, total = send_init(handle, max(0.0, args.init_delay_ms / 1000.0))
            print(f"INIT sent ok={ok}/{total}", flush=True)
        while deadline is None or time.time() < deadline:
            now = time.time()
            if now - last_query >= max(0.05, args.query_interval_ms / 1000.0):
                try:
                    write_command(handle, *QUERY_PACKET)
                except OSError as exc:
                    print(f"WARN query failed: {exc}", flush=True)
                last_query = now

            try:
                report = handle.read(args.read_size, max(1, int(args.read_timeout_ms)))
            except OSError as exc:
                print(f"WARN read failed: {exc}", flush=True)
                time.sleep(0.05)
                continue
            if not report:
                if args.status_interval_ms > 0 and now - last_status >= args.status_interval_ms / 1000.0:
                    ranked = normalizer.ranked()[: args.top]
                    row = {"ts": now, "type": "status", "active": [], "top": ranked, "all": normalizer.ranked()}
                    write_jsonl(jsonl_file, row)
                    rows += 1
                    last_status = now
                continue
            if args.dump_raw:
                raw = with_report_id(report)
                print("RAW " + raw.hex(" "), flush=True)
            samples = decode_pressure_report(report, args.full_delta)
            if samples is None:
                continue
            normalizer.enrich(samples)
            if now - last_emit < args.min_interval_ms / 1000.0:
                continue
            ranked = normalizer.ranked()
            active = [item for item in ranked if abs(float(item.get("delta", 0))) >= args.min_delta or float(item.get("pressure", 0.0)) >= 0.001]
            row = {
                "ts": now,
                "type": "press" if active else "status",
                "active": active[: args.top],
                "top": ranked[: args.top],
                "all": ranked,
            }
            write_jsonl(jsonl_file, row)
            rows += 1
            if active:
                press_rows += 1
            last_emit = now
    finally:
        try:
            handle.close()
        finally:
            if jsonl_file is not None:
                jsonl_file.close()
    print(f"done rows={rows} press_rows={press_rows} jsonl={jsonl_path}", flush=True)
    return 0 if press_rows or not args.require_events else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe MelGeek MADE68 V2 pressure reports through native hidapi.")
    parser.add_argument("--list", action="store_true", help="List MelGeek HID interfaces and exit.")
    parser.add_argument("--device-index", type=int, default=None, help="Use a specific hid.enumerate index instead of the raw HID interface.")
    parser.add_argument("--seconds", type=float, default=20.0, help="Run duration. 0 means until Ctrl+C.")
    parser.add_argument("--jsonl", default=str(OUTPUTS / "native_pressure_probe.jsonl"))
    parser.add_argument("--full-delta", type=float, default=1100.0)
    parser.add_argument("--min-delta", type=float, default=1.0)
    parser.add_argument("--min-interval-ms", type=float, default=20.0)
    parser.add_argument("--status-interval-ms", type=float, default=1000.0)
    parser.add_argument("--query-interval-ms", type=float, default=1000.0)
    parser.add_argument("--init-delay-ms", type=float, default=25.0)
    parser.add_argument("--read-timeout-ms", type=float, default=50.0)
    parser.add_argument("--read-size", type=int, default=65)
    parser.add_argument("--top", type=int, default=80)
    parser.add_argument("--no-init", action="store_true")
    parser.add_argument("--dump-raw", action="store_true")
    parser.add_argument("--require-events", action="store_true")
    args = parser.parse_args()

    if args.list:
        for index, dev in enumerate(melgeek_devices()):
            print(describe_device(index, dev), flush=True)
        return 0
    try:
        return run_probe(args)
    except KeyboardInterrupt:
        print("stopped", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
