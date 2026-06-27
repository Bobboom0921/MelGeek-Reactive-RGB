from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
OUTPUTS = ROOT / "outputs"
BRIDGE = WORK / "melgeek_webhid_bridge.html"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DEFAULT_BRIDGE_URL = "https://hive.melgeek.cn/melgeek-webhid-bridge"
EDGE_DEFAULT_PREFS = Path.home() / r"AppData\Local\Microsoft\Edge\User Data\Default\Preferences"


def seed_hive_hid_permission(profile_root: Path) -> None:
    if not EDGE_DEFAULT_PREFS.exists():
        return
    source = json.loads(EDGE_DEFAULT_PREFS.read_text(encoding="utf-8"))
    chooser = (
        source.get("profile", {})
        .get("content_settings", {})
        .get("exceptions", {})
        .get("hid_chooser_data", {})
    )
    if not chooser:
        return
    default_dir = profile_root / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    prefs_path = default_dir / "Preferences"
    prefs = {}
    if prefs_path.exists():
        try:
            prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
        except Exception:
            prefs = {}
    exceptions = prefs.setdefault("profile", {}).setdefault("content_settings", {}).setdefault("exceptions", {})
    exceptions["hid_chooser_data"] = chooser
    prefs_path.write_text(json.dumps(prefs, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read MelGeek MADE68V2 Hall/magnetic key pressure data via WebHID.")
    parser.add_argument("--seconds", type=float, default=0.0, help="Run duration. 0 means keep running until Ctrl+C.")
    parser.add_argument("--url", default=DEFAULT_BRIDGE_URL, help="Hive-origin bridge URL used for stored WebHID permission.")
    parser.add_argument("--profile", default=str(WORK / "edge_hive_bridge_profile"))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--min-delta", type=float, default=18.0, help="Minimum absolute baseline delta to emit a press event.")
    parser.add_argument("--min-interval-ms", type=float, default=20.0, help="Minimum interval between emitted rows.")
    parser.add_argument("--status-interval-ms", type=float, default=0.0, help="Emit idle status rows this often. 0 disables idle rows.")
    parser.add_argument("--full-delta", type=float, default=1100.0, help="Raw value delta treated as full pressure for normalized pressure output.")
    parser.add_argument("--top", type=int, default=8, help="Number of strongest keys included in each row.")
    parser.add_argument("--watch", action="append", default=[], help="Key IDs to always include. Accepts repeated values or comma lists.")
    parser.add_argument("--quiet", action="store_true", help="Only print JSONL event rows to stdout.")
    parser.add_argument("--require-events", action="store_true", help="Return a non-zero exit code when no press events are captured.")
    args = parser.parse_args()

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    profile_root = Path(args.profile)
    seed_hive_hid_permission(profile_root)
    watch_ids: list[str] = []
    for item in args.watch:
        watch_ids.extend(part.strip() for part in item.split(",") if part.strip())
    if not watch_ids:
        watch_ids = ["31", "36", "61"]

    query = urllib.parse.urlencode(
        {
            "minDelta": args.min_delta,
            "minIntervalMs": args.min_interval_ms,
            "statusIntervalMs": args.status_interval_ms,
            "fullDelta": args.full_delta,
            "top": args.top,
            "watch": ",".join(watch_ids),
        }
    )
    url = args.url + ("&" if "?" in args.url else "?") + query
    out = Path(args.out) if args.out else None
    out_file = out.open("w", encoding="utf-8") if out else None
    got = 0

    def log(text: str) -> None:
        if not args.quiet:
            print(text, flush=True, file=sys.stderr)

    log(f"bridge: {url}")
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                str(profile_root),
                executable_path=EDGE,
                headless=args.headless,
                args=["--enable-features=WebHID"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            bridge_html = BRIDGE.read_text(encoding="utf-8")
            context.route(url, lambda route: route.fulfill(status=200, content_type="text/html", body=bridge_html))

            def on_console(msg):
                nonlocal got
                text = msg.text
                if text.startswith("HALL "):
                    payload = text[5:]
                    try:
                        row = json.loads(payload)
                    except json.JSONDecodeError:
                        log(f"WARN bad json: {payload}")
                        return
                    if row.get("type") == "press":
                        got += 1
                    print(json.dumps(row, ensure_ascii=False, separators=(",", ":")), flush=True)
                    if out_file:
                        out_file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                        out_file.flush()
                elif (
                    "ERROR" in text
                    or text.startswith("OPEN")
                    or text.startswith("INIT")
                    or text.startswith("WARN")
                    or text.startswith("COLLECTIONS")
                ):
                    log(text)

            page.on("console", on_console)
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_selector("#connect", timeout=10000)
            try:
                page.click("#connect", timeout=5000)
            except PlaywrightTimeoutError:
                page.evaluate("window.__melgeekConnect && window.__melgeekConnect()")

            deadline = None if args.seconds <= 0 else time.time() + max(1.0, args.seconds)
            while deadline is None or time.time() < deadline:
                time.sleep(0.1)

            context.close()
    except KeyboardInterrupt:
        log("stopped by user")
    finally:
        if out_file:
            out_file.close()

    log(f"done press_events={got}")
    return 0 if got or not args.require_events else 2


if __name__ == "__main__":
    raise SystemExit(main())
