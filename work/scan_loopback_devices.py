from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "outputs" / "loopback_scan.log"


def rms(data) -> float:  # noqa: ANN001
    try:
        import numpy as np
        arr = data.astype(float)
        if getattr(arr, "ndim", 1) > 1:
            arr = np.mean(arr, axis=1)
        return float(np.sqrt(np.mean(arr * arr))) if len(arr) else 0.0
    except Exception:
        return 0.0


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    try:
        import soundcard as sc
    except Exception as exc:
        print(f"soundcard import failed: {exc}")
        return 2

    speakers = sc.all_speakers()
    microphones = sc.all_microphones(include_loopback=True)
    default_speaker = sc.default_speaker()
    default_mic = sc.default_microphone()
    lines.append(f"default speaker: {default_speaker}")
    lines.append(f"default microphone: {default_mic}")
    lines.append(f"speaker count: {len(speakers)}")
    lines.append(f"microphone+loopback count: {len(microphones)}")
    lines.append("speakers:")
    for idx, speaker in enumerate(speakers):
        lines.append(f"  speaker[{idx}]: {getattr(speaker, 'name', str(speaker))}")
    print("请保持音乐播放。开始扫描 loopback microphone 设备...")
    for idx, mic in enumerate(microphones):
        name = getattr(mic, "name", str(mic))
        is_loopback = "loopback" in name.lower() or "stereo mix" in name.lower() or "what u hear" in name.lower()
        print(f"[{idx}] testing {name} ...")
        value = 0.0
        err = ""
        try:
            with mic.recorder(samplerate=44100, channels=2, blocksize=2048) as rec:
                best = 0.0
                for _ in range(10):
                    data = rec.record(numframes=2048)
                    best = max(best, rms(data))
                value = best
        except Exception as exc:
            err = repr(exc)
        line = f"[{idx}] rms={value:.6f} loopback_guess={is_loopback} name={name} error={err}"
        lines.append(line)
        print(line)
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"log: {LOG}")
    print("如果某个 rms 明显大于 0.005，那个就是可用的系统音频回录设备。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
