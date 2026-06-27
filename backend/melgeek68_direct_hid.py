from __future__ import annotations

import argparse
import threading
import time

import hid


# 已知 MelGeek 型号（用于日志和 fallback）
KNOWN_MELGEEK = {
    (0x3854, 0x040F): "MADE68 V2 / V2 Ultra",
    (0x306F, 0x0301): "MelGeek 其他型号",
}
RAW_USAGE_PAGE = 0xFF60
RAW_USAGE = 0x61
LAMP_COUNT = 285
CHUNK_SIZE = 17
REPORT_SIZE = 65

BLACK = (0, 0, 0)


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


FRAME_BEGIN_PACKETS = [
    make_packet(0x07, 0x86, b"\x00\x00\x00\x00\x00\x00"),
    make_packet(0x0F, 0x85, b"\x01"),
    make_packet(0x0F, 0x83, b"\x07"),
]


def clamp_channel(value: int) -> int:
    return max(0, min(255, int(value)))


def _describe_dev(dev: dict) -> str:
    vid = dev.get("vendor_id", 0)
    pid = dev.get("product_id", 0)
    name = dev.get("product_string") or "Unknown"
    up = dev.get("usage_page", 0)
    us = dev.get("usage", 0)
    model = KNOWN_MELGEEK.get((vid, pid), "")
    return f"  VID=0x{vid:04X} PID=0x{pid:04X} {model} | '{name}' | usage_page=0x{up:04X} usage=0x{us:02X}"


def raw_device_path(verbose: bool = True) -> bytes:
    """扫描所有 HID 设备，自动找到 MelGeek raw HID 接口。

    优先匹配 usage_page=0xFF60 & usage=0x61，不限定 VID/PID。
    这样任何型号的 MelGeek 键盘都能自动识别。
    """
    all_devices = list(hid.enumerate())
    melgeek_devices = []
    raw_candidates = []

    for dev in all_devices:
        vid = dev.get("vendor_id", 0)
        pid = dev.get("product_id", 0)
        name = dev.get("product_string") or ""
        up = dev.get("usage_page", 0)
        us = dev.get("usage", 0)

        # 标记已知 MelGeek 设备
        if (vid, pid) in KNOWN_MELGEEK or "MelGeek" in name or "Made68" in name or "MADE68" in name:
            melgeek_devices.append(dev)

        # 优先匹配 raw HID 接口
        if up == RAW_USAGE_PAGE and us == RAW_USAGE:
            raw_candidates.append(dev)

    if verbose:
        if melgeek_devices:
            print(f"HID: found {len(melgeek_devices)} MelGeek device(s):")
            for dev in melgeek_devices:
                print(_describe_dev(dev))
        else:
            print("HID: no MelGeek-branded devices found.")
        if raw_candidates:
            print(f"HID: found {len(raw_candidates)} raw HID interface(s) (usage_page=0xFF60, usage=0x61):")
            for dev in raw_candidates:
                print(_describe_dev(dev))

    if raw_candidates:
        return raw_candidates[0]["path"]

    # fallback：已知 VID/PID 组合
    for dev in melgeek_devices:
        if dev.get("usage_page") == RAW_USAGE_PAGE and dev.get("usage") == RAW_USAGE:
            return dev["path"]

    # 详细错误信息
    lines = ["MelGeek raw HID interface not found."]
    if not all_devices:
        lines.append("No HID devices detected at all. Check USB connection and hidapi driver.")
    elif not melgeek_devices:
        lines.append("No MelGeek devices detected. Make sure keyboard is connected via USB (not Bluetooth).")
        lines.append("All detected devices:")
        for dev in all_devices[:20]:
            lines.append(_describe_dev(dev))
    else:
        lines.append("MelGeek device(s) detected but no raw HID interface (usage_page=0xFF60, usage=0x61).")
        lines.append("This usually means the keyboard is in a different mode or the driver is not exposing the interface.")
    raise RuntimeError("\n".join(lines))


def open_device() -> hid.device:
    handle = hid.device()
    handle.open_path(raw_device_path(verbose=True))
    handle.set_nonblocking(False)
    return handle


def make_control_packet(command: int, payload: bytes) -> bytes:
    return make_packet(0x0F, command, payload)


def make_frame_packets(
    colors: list[tuple[int, int, int]],
    include_begin: bool = True,
    begin_indices: list[int] | None = None,
) -> list[bytes]:
    padded = list(colors[:LAMP_COUNT])
    if len(padded) < LAMP_COUNT:
        padded.extend([BLACK] * (LAMP_COUNT - len(padded)))

    packets: list[bytes] = []
    if include_begin:
        if begin_indices is None:
            packets.extend(FRAME_BEGIN_PACKETS)
        else:
            packets.extend(FRAME_BEGIN_PACKETS[index] for index in begin_indices)
    for start in range(0, LAMP_COUNT, CHUNK_SIZE):
        chunk = padded[start : start + CHUNK_SIZE]
        payload = bytearray()
        # This leading byte is duplicated from the high byte of the start lamp in captured packets.
        payload.append((start >> 8) & 0xFF)
        payload.append(len(chunk) & 0xFF)
        payload.append(0x00)
        payload.extend(start.to_bytes(2, "little"))
        for rgb in chunk:
            payload.extend(clamp_channel(channel) for channel in rgb)
        packets.append(make_control_packet(0x86, bytes(payload)))
    return packets


def write_packets(handle: hid.device, packets: list[bytes], delay_s: float = 0.0, max_retries: int = 2) -> None:
    for packet in packets:
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                written = handle.write(packet)
                if written > 0:
                    last_error = None
                    break
                last_error = OSError("HID write returned <= 0")
            except OSError as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(0.01)
        if last_error is not None:
            raise last_error
        if delay_s > 0:
            time.sleep(delay_s)


class DirectHidSender:
    def __init__(self, delay_s: float = 0.0) -> None:
        self.delay_s = max(0.0, delay_s)
        self.handle: hid.device | None = None
        self.lock = threading.Lock()
        self._failed_writes = 0
        self._max_failures = 5
        self._last_fail_time = 0.0
        self._cooldown_s = 3.0

    def open(self) -> None:
        if self.handle is None:
            self.handle = open_device()

    def _reopen(self) -> None:
        try:
            if self.handle is not None:
                self.handle.close()
        except Exception:
            pass
        self.handle = None
        time.sleep(0.1)
        self.handle = open_device()
        self._failed_writes = 0

    def send_frame(
        self,
        colors: list[tuple[int, int, int]],
        include_begin: bool = False,
        begin_indices: list[int] | None = None,
    ) -> None:
        packets = make_frame_packets(colors, include_begin=include_begin, begin_indices=begin_indices)
        with self.lock:
            self.open()
            assert self.handle is not None
            try:
                write_packets(self.handle, packets, delay_s=self.delay_s)
                self._failed_writes = 0
            except OSError:
                self._failed_writes += 1
                now = time.time()
                if self._failed_writes >= self._max_failures and (now - self._last_fail_time) > self._cooldown_s:
                    self._last_fail_time = now
                    try:
                        self._reopen()
                        write_packets(self.handle, packets, delay_s=self.delay_s)
                        self._failed_writes = 0
                    except Exception:
                        raise
                else:
                    raise

    def send_black(self, include_begin: bool = False) -> None:
        self.send_frame([BLACK for _ in range(LAMP_COUNT)], include_begin=include_begin)

    def close(self) -> None:
        with self.lock:
            if self.handle is not None:
                try:
                    self.handle.close()
                except Exception:
                    pass
                self.handle = None


def send_frame(
    colors: list[tuple[int, int, int]],
    delay_s: float = 0.0,
    include_begin: bool = False,
    begin_indices: list[int] | None = None,
) -> None:
    handle = open_device()
    try:
        write_packets(handle, make_frame_packets(colors, include_begin=include_begin, begin_indices=begin_indices), delay_s=delay_s)
    finally:
        handle.close()


def make_single_lamp(lamp_id: int, color: tuple[int, int, int]) -> list[tuple[int, int, int]]:
    colors = [BLACK for _ in range(LAMP_COUNT)]
    if 0 <= lamp_id < LAMP_COUNT:
        colors[lamp_id] = tuple(clamp_channel(channel) for channel in color)
    return colors


def make_lamp_range(start: int, end: int, color: tuple[int, int, int]) -> list[tuple[int, int, int]]:
    colors = [BLACK for _ in range(LAMP_COUNT)]
    for lamp_id in range(max(0, start), min(LAMP_COUNT - 1, end) + 1):
        colors[lamp_id] = tuple(clamp_channel(channel) for channel in color)
    return colors


def parse_hex_payload(value: str) -> bytes:
    cleaned = value.replace(" ", "").replace(",", "").replace("0x", "")
    if len(cleaned) % 2:
        cleaned = "0" + cleaned
    return bytes.fromhex(cleaned)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lamp", type=int, default=36)
    parser.add_argument("--range", dest="lamp_range", help="light a lamp range, format start-end, for example 259-284")
    parser.add_argument("--rgb", default="0,255,255")
    parser.add_argument("--hold", type=float, default=1.5)
    parser.add_argument("--refresh-hz", type=float, default=30.0, help="keep refreshing while holding")
    parser.add_argument("--black", action="store_true", help="send only an all-black frame")
    parser.add_argument("--black-with-begin", action="store_true", help="include frame-begin control packets in --black")
    parser.add_argument("--control", help="send one raw 0x0f control packet, format command:hexpayload, for example 85:00")
    parser.add_argument("--single", action="store_true", help="send the lit frame once, then hold without refreshing")
    parser.add_argument("--no-final-black", action="store_true", help="do not send all-black after holding")
    parser.add_argument("--initial-begin", action="store_true", help="include frame-begin control packets before the first lit frame")
    parser.add_argument("--begin-index", type=int, action="append", choices=[0, 1, 2], help="with --initial-begin, send only selected begin packet index; can repeat")
    parser.add_argument("--begin-every-frame", action="store_true", help="send frame-begin control packets on every refresh")
    parser.add_argument("--delay-ms", type=float, default=0.0, help="delay between 65-byte packets")
    args = parser.parse_args()

    delay_s = max(0.0, args.delay_ms / 1000.0)
    if args.control:
        command_text, payload_text = args.control.split(":", 1)
        command = int(command_text, 16)
        payload = parse_hex_payload(payload_text)
        handle = open_device()
        try:
            write_packets(handle, [make_control_packet(command, payload)], delay_s=delay_s)
        finally:
            handle.close()
        return 0

    if args.black:
        send_frame([BLACK for _ in range(LAMP_COUNT)], delay_s=delay_s, include_begin=args.black_with_begin)
        return 0

    parts = [int(item.strip()) for item in args.rgb.split(",")]
    if len(parts) != 3:
        raise ValueError("--rgb must be R,G,B")
    handle = open_device()
    try:
        if args.lamp_range:
            start_text, end_text = args.lamp_range.split("-", 1)
            colors = make_lamp_range(int(start_text), int(end_text), tuple(parts))
        else:
            colors = make_single_lamp(args.lamp, tuple(parts))
        lit_packets = make_frame_packets(colors, include_begin=args.initial_begin, begin_indices=args.begin_index)
        lit_refresh_packets = make_frame_packets(colors, include_begin=args.begin_every_frame)
        deadline = time.perf_counter() + max(0.0, args.hold)
        interval = 1.0 / max(1.0, args.refresh_hz)
        write_packets(handle, lit_packets, delay_s=delay_s)
        if args.single:
            time.sleep(max(0.0, args.hold))
        else:
            while time.perf_counter() < deadline:
                started = time.perf_counter()
                write_packets(handle, lit_refresh_packets, delay_s=delay_s)
                time.sleep(max(0.0, interval - (time.perf_counter() - started)))
        if not args.no_final_black:
            write_packets(handle, make_frame_packets([BLACK for _ in range(LAMP_COUNT)], include_begin=False), delay_s=delay_s)
    finally:
        handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
