from __future__ import annotations

import argparse
import json
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"

HTML = r"""<!doctype html>
<meta charset="utf-8">
<title>Connect WebHID</title>
<style>
  :root { color-scheme: light; }
  html, body { margin: 0; padding: 0; background: transparent; overflow: hidden; font-family: system-ui, -apple-system, Segoe UI, sans-serif; }
  #wrap { display: flex; align-items: center; gap: 8px; height: 44px; padding: 0; }
  button { height: 36px; padding: 0 14px; border: 0; border-radius: 12px; background: #007aff; color: white; font-weight: 700; font-size: 13px; cursor: pointer; }
  button.connected { background: #34c759; }
  button.error { background: #ff3b30; }
  #state { font-size: 12px; color: #6b7280; white-space: nowrap; max-width: 150px; overflow: hidden; text-overflow: ellipsis; }
</style>
<div id="wrap">
  <button id="connect">Connect WebHID</button>
  <span id="state">not connected</span>
</div>
<script>
const VID = 0x3854;
const PID = 0x040f;
const REPORT_SIZE = 65;
const KEY_NAMES = {31:'A', 36:'H', 61:'Space', 62:'Space2', 63:'Space3'};
const MIN_DELTA = 0;
const FULL_DELTA = 1100;
const TOP_LIMIT = 80;
let device = null;
let baseline = new Map();
let latest = new Map();
let lastPost = 0;
let lastUiLog = 0;
let statusTimer = null;

function log(text, cls='') {
  const el = document.querySelector('#state');
  el.textContent = text;
  if (cls === 'bad') document.querySelector('#connect').className = 'error';
}
function setState(text, cls='') {
  const el = document.querySelector('#state');
  const btn = document.querySelector('#connect');
  el.textContent = text;
  btn.className = cls === 'ok' ? 'connected' : (cls === 'bad' ? 'error' : '');
}
function clamp01(v) { return Math.max(0, Math.min(1, v)); }
function crc16CcittFalse(bytes) {
  let crc = 0xffff;
  for (const byte of bytes) {
    crc ^= byte << 8;
    for (let i = 0; i < 8; i++) crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
  }
  return crc;
}
function makePacket(prefix, command, payload) {
  const full = new Uint8Array(REPORT_SIZE);
  full[0] = 0x00;
  full[1] = prefix;
  full[2] = command;
  full[3] = payload.length;
  const crc = crc16CcittFalse(payload);
  full[7] = crc & 0xff;
  full[8] = (crc >> 8) & 0xff;
  full.set(payload, 9);
  return full.slice(1);
}
async function send(prefix, command, payload) {
  const packet = makePacket(prefix, command, payload);
  await device.sendReport(0, packet);
}
async function initStream() {
  const packets = [
    [0x0a, 0x82, [0x01,0x32,0x32,0x01,0x00,0x20,0x01]],
    [0x0a, 0x82, [0x01,0x32,0x32,0x00,0x00,0x20,0x01]],
    [0x0a, 0x80, [0x01,0x20,0x82,0x00,0x82,0x00]],
    [0x0a, 0x80, [0x01,0x20,0x96,0x00,0x96,0x00]],
    [0x0a, 0x82, [0x01,0x32,0x32,0x00,0x00,0x20,0x00]],
    [0x0a, 0x93, [0x02]],
  ];
  let ok = 0;
  for (let i = 0; i < packets.length; i++) {
    const [prefix, command, payload] = packets[i];
    try { await send(prefix, command, new Uint8Array(payload)); ok++; }
    catch (err) { log('WARN init[' + i + '] ' + err.name + ': ' + err.message, 'bad'); }
    await new Promise(resolve => setTimeout(resolve, 25));
  }
  log('INIT sent ok=' + ok + '/' + packets.length, ok ? 'ok' : 'bad');
}
function hasRawHidCollection(candidate) {
  return (candidate.collections || []).some(c =>
    c.usagePage === 0xff60 && c.usage === 0x61 && (c.outputReports || []).some(r => r.reportId === 0)
  );
}
function decodeReport(reportId, data) {
  const bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  const raw = bytes.length === 65 ? bytes : new Uint8Array([reportId, ...bytes]);
  if (raw.length < 9 || raw[1] !== 0x08 || raw[2] !== 0x09) return null;
  const payloadLen = raw[3];
  const out = [];
  for (let offset = 9; offset + 3 < 9 + payloadLen; offset += 4) {
    const rawId = raw[offset] | (raw[offset + 1] << 8);
    const keyId = rawId & 0xff;
    const depthCode = rawId >> 8;
    const value = raw[offset + 2] | (raw[offset + 3] << 8);
    if (rawId || value) out.push({ keyId, key: KEY_NAMES[keyId] || String(keyId), value, depthCode });
  }
  return out;
}
async function postRow(row) {
  try {
    await fetch('/event', { method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(row) });
  } catch (err) {
    log('POST failed: ' + err.message, 'bad');
  }
}
function enrich(sample) {
  if (!baseline.has(sample.keyId)) baseline.set(sample.keyId, sample.value);
  sample.delta = sample.value - baseline.get(sample.keyId);
  sample.pressureValue = clamp01((-sample.delta) / FULL_DELTA);
  sample.pressureDepth = clamp01(sample.depthCode / 48);
  // Use continuous ADC-derived pressure for visuals. depthCode is useful for
  // diagnostics, but it is quantized (0..48) and creates visible trigger steps.
  sample.pressure = sample.pressureValue;
  sample.down = sample.pressure >= 0.02;
  return sample;
}
function emitStatus(force=false) {
  const ranked = Array.from(latest.values()).sort((a,b) => Math.max(Math.abs(b.delta), b.pressure*FULL_DELTA) - Math.max(Math.abs(a.delta), a.pressure*FULL_DELTA));
  const active = ranked.filter(s => Math.abs(s.delta) >= MIN_DELTA || s.pressure >= 0.001);
  const row = { ts: Date.now()/1000, type: active.length ? 'press' : 'status', active: active.slice(0, TOP_LIMIT), top: ranked.slice(0, TOP_LIMIT), all: ranked };
  postRow(row);
  const now = performance.now();
  if (force || now - lastUiLog > 1000) {
    lastUiLog = now;
    const best = active[0];
    log('frames ok, active=' + active.length + (best ? (' top=' + best.keyId + ' p=' + best.pressure.toFixed(2)) : ''));
  }
}
function handleInputReport(event) {
  const samples = decodeReport(event.reportId, event.data);
  if (!samples) return;
  for (const sample of samples) latest.set(sample.keyId, enrich(sample));
  const now = performance.now();
  if (now - lastPost >= 20) { lastPost = now; emitStatus(false); }
}
async function connect() {
  try {
    if (!('hid' in navigator)) throw new Error('WebHID is not available. Use Edge/Chrome on localhost.');
    let devices = await navigator.hid.getDevices();
    devices = devices.filter(d => d.vendorId === VID && d.productId === PID);
    if (!devices.length) {
      try {
        devices = await navigator.hid.requestDevice({ filters: [{ vendorId: VID, productId: PID }] });
      } catch (err) {
        log('VID/PID request failed, trying broad HID chooser', 'bad');
        devices = await navigator.hid.requestDevice({ filters: [] });
      }
      devices = devices.filter(d => d.vendorId === VID && d.productId === PID);
    }
    if (!devices.length) {
      const known = (await navigator.hid.getDevices()).map(d => `${d.productName || 'unknown'} vid=${d.vendorId} pid=${d.productId}`).join('; ');
      throw new Error('No MelGeek HID device selected. Known=' + known);
    }
    device = devices.find(d => hasRawHidCollection(d)) || devices[0];
    if (!device) throw new Error('No MelGeek HID device selected');
    await device.open();
    device.addEventListener('inputreport', handleInputReport);
    setState('connected: ' + device.productName, 'ok');
    await postRow({ ts: Date.now()/1000, type:'connected', productName: device.productName });
    log('OPEN ' + device.productName, 'ok');
    log('COLLECTIONS ' + JSON.stringify((device.collections || []).map(c => ({usagePage:c.usagePage, usage:c.usage, input:(c.inputReports||[]).map(r=>r.reportId), output:(c.outputReports||[]).map(r=>r.reportId)}))));
    await initStream();
    if (statusTimer) clearInterval(statusTimer);
    statusTimer = setInterval(() => {
      send(0x0a, 0x93, new Uint8Array([0x02])).catch(err => log('WARN query ' + err.name + ': ' + err.message, 'bad'));
      emitStatus(false);
    }, 1000);
  } catch (err) {
    setState('error: ' + err.message, 'bad');
    log('ERROR ' + (err.stack || err.message), 'bad');
    await postRow({ ts: Date.now()/1000, type:'error', error: String(err.stack || err.message) });
  }
}
document.querySelector('#connect').addEventListener('click', connect);
</script>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "MelGeekPressureHTTP/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/event":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length", "0") or "0")
        raw = self.rfile.read(length)
        text = raw.decode("utf-8", errors="replace").strip()
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            row = {"ts": time.time(), "type": "bad-json", "raw": text[:500]}
        self.server.log_row(row)  # type: ignore[attr-defined]
        body = b"ok"
        self.send_response(200)
        self.send_header("content-type", "text/plain")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


class PressureServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, jsonl_path: Path, log_path: Path):
        super().__init__(server_address, RequestHandlerClass)
        self.jsonl_path = jsonl_path
        self.log_path = log_path
        self.rows = 0
        self.press_rows = 0
        self.last_summary = 0.0
        self.jsonl_file = jsonl_path.open("a", encoding="utf-8")
        self.log_file = log_path.open("a", encoding="utf-8")

    def log_row(self, row: dict) -> None:
        self.rows += 1
        if row.get("type") == "press" or row.get("active"):
            self.press_rows += 1
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        self.jsonl_file.write(line + "\n")
        self.jsonl_file.flush()
        now = time.time()
        if row.get("type") == "error" or now - self.last_summary > 1.0:
            summary = {
                "ts": row.get("ts", now),
                "type": row.get("type"),
                "rows": self.rows,
                "press_rows": self.press_rows,
                "active": len(row.get("active") or []),
            }
            if row.get("error"):
                summary["error"] = row.get("error")
            text = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
            self.log_file.write(text + "\n")
            self.log_file.flush()
            print(text, flush=True)
            self.last_summary = now

    def server_close(self) -> None:
        try:
            self.jsonl_file.close()
            self.log_file.close()
        finally:
            super().server_close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--jsonl", default=str(OUTPUTS / "local_webhid_pressure.jsonl"))
    parser.add_argument("--log", default=str(OUTPUTS / "local_webhid_pressure.log"))
    args = parser.parse_args()

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    jsonl_path = Path(args.jsonl)
    log_path = Path(args.log)
    jsonl_path.write_text("", encoding="utf-8")
    log_path.write_text(f"==== {time.ctime()} ====\n", encoding="utf-8")
    server = PressureServer(("127.0.0.1", args.port), Handler, jsonl_path, log_path)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Serving WebHID pressure monitor: {url}", flush=True)
    print(f"JSONL: {jsonl_path}", flush=True)
    print(f"Log:   {log_path}", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
