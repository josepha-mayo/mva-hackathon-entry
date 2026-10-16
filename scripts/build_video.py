"""Render the Track 2 pitch video from the committed script + storyboard.

Rebuilds ``work/pitch/track2-pitch.mp4`` — scene slides (Pillow) keyed to the
``## m:ss–m:ss`` sections of ``reports/josephmayo_track2_pitch_script.md``,
narration synthesized per scene (Windows SAPI, offline), muxed with ffmpeg.
The benchmark scene carries the committed receipt digest so the render is
provably tied to the bound evidence.

Stdlib + Pillow + ffmpeg only. Usage:

    python scripts/build_video.py .

Output: work/pitch/track2-pitch.mp4
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

SCRIPT_PATH = Path("reports/josephmayo_track2_pitch_script.md")
RECEIPT_PATH = Path("reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json")
OUT_DIR = Path("work") / "pitch"
OUT_FILE = OUT_DIR / "track2-pitch.mp4"
REPO_URL = "github.com/josepha-mayo/mva-hackathon-entry"

W, H = 1920, 1080
BG = (13, 17, 23)
FG = (230, 237, 243)
ACCENT = (88, 166, 255)
DIM = (139, 148, 158)
WARN = (248, 140, 61)
FOOTER = "Preclinical hypothesis only — no administration, dosing, efficacy, safety, or cure claim"

SCENE_SOURCES = {
    2: ["current MIPLYFFA prescribing information"],
    3: [],
    4: ["repository benchmark receipt"],
    5: ["Hanks 2004", "Suijkerbuijk 2010", "AlphaFold DB O60566", "AlphaMissense/Cheng 2023"],
}

SECTION_RE = re.compile(r"^##\s+(\d+:\d+\D\d+:\d+)\s+[-—]+\s+(.*)$", re.M)
ONSCREEN_RE = re.compile(r"\*\*On screen:\*\*\s*`([^`]+)`")
NARRATION_RE = re.compile(r"\*\*Narration:\*\*\s*\n\s*\n(.+?)(?=\n\n|\Z)", re.S)


def _tts(text: str, wav_path: Path, rate: int = 5) -> float:
    """Synthesize narration via Windows SAPI; return duration in seconds."""
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate = {rate}; "
        f"$s.SetOutputToWaveFile('{wav_path.as_posix()}'); "
        f"$s.Speak(@'\n{text}\n'@); "
        "$s.Dispose()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        check=True,
        capture_output=True,
        text=True,
    )
    with wave.open(str(wav_path), "rb") as w:
        return w.getnframes() / w.getframerate()


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, width: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _slide(scene: dict, index: int, receipt_digest: str, png_path: Path) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # scene label + rule
    d.text((96, 72), scene["when"], font=_font(44), fill=DIM)
    d.line((96, 148, W - 96, 148), fill=(48, 54, 61), width=3)

    # title
    title_font = _font(72, bold=True)
    y = 190
    for line in _wrap(d, scene["title"], title_font, W - 192):
        d.text((96, y), line, font=title_font, fill=FG)
        y += 96

    # big on-screen claim
    y += 40
    claim_font = _font(88, bold=True)
    for line in _wrap(d, scene["on_screen"], claim_font, W - 192):
        d.text((96, y), line, font=claim_font, fill=ACCENT)
        y += 116

    # narration text, muted — muted-audio viewers still get the pitch
    y += 56
    narr_font = _font(38)
    for line in _wrap(d, scene["narration"], narr_font, W - 192)[:7]:
        d.text((96, y), line, font=narr_font, fill=(121, 133, 148))
        y += 54

    # benchmark-scene provenance chip: committed receipt digest + repo
    if index == 4:
        chip = f"receipt sha256 {receipt_digest[:16]}...  |  {REPO_URL}"
        cw = int(d.textlength(chip, font=_font(36))) + 48
        d.rounded_rectangle((96, H - 320, 96 + cw, H - 244), 18, outline=(48, 54, 61), width=2)
        d.text((120, H - 300), chip, font=_font(36), fill=DIM)

    # source labels, small, lower-left above footer
    sources = SCENE_SOURCES.get(index, [])
    if sources:
        sy = H - 200
        d.text((96, sy), "sources: " + " · ".join(sources), font=_font(30), fill=DIM)

    # persistent footer (storyboard-required)
    d.line((96, H - 148, W - 96, H - 148), fill=(48, 54, 61), width=3)
    d.text((96, H - 120), FOOTER, font=_font(34), fill=WARN)
    img.save(png_path)


def _parse_scenes(script: str) -> list[dict]:
    scenes = []
    parts = SECTION_RE.split(script)
    # parts: [prelude, when1, title1, body1, when2, title2, body2, ...]
    for i in range(1, len(parts), 3):
        when, title, body = parts[i], parts[i + 1], parts[i + 2]
        on = ONSCREEN_RE.search(body)
        narr = NARRATION_RE.search(body)
        scenes.append(
            {
                "when": when.replace("\u2013", "-").replace("\u2014", "-"),
                "title": title.strip(),
                "on_screen": on.group(1) if on else title.strip(),
                "narration": re.sub(r"\s+", " ", narr.group(1)).strip().strip("“”")
                if narr
                else "",
            }
        )
    return scenes


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    rate = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    script = (root / SCRIPT_PATH).read_text(encoding="utf-8")
    scenes = _parse_scenes(script)
    if not scenes or any(not s["narration"] for s in scenes):
        print("pitch script parse failed — no complete scenes found")
        return 2

    receipt_sha = hashlib.sha256((root / RECEIPT_PATH).read_bytes()).hexdigest()
    out_dir = root / OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    narration_total = 0.0
    seg_paths: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="pitch-") as tmp:
        tmp = Path(tmp)
        for i, scene in enumerate(scenes):
            wav = tmp / f"n{i}.wav"
            secs = _tts(scene["narration"], wav, rate)
            narration_total += secs

            png = tmp / f"s{i}.png"
            _slide(scene, i, receipt_sha, png)

            seg = tmp / f"seg{i}.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loop", "1", "-framerate", "30",
                    "-i", str(png),
                    "-i", str(wav),
                    "-c:v", "libx264", "-tune", "stillimage",
                    "-c:a", "aac", "-b:a", "160k",
                    "-pix_fmt", "yuv420p",
                    "-t", f"{secs + 0.05:.2f}",
                    "-vf", f"scale={W}:{H}",
                    str(seg),
                ],
                check=True,
                capture_output=True,
            )
            seg_paths.append(seg)

        concat = tmp / "concat.txt"
        concat.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in seg_paths), encoding="utf-8"
        )
        out = root / OUT_FILE
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat), "-c", "copy", str(out),
            ],
            check=True,
            capture_output=True,
        )

    probe = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    video_secs = float(probe.stdout.strip())
    print(f"TOTAL narration {narration_total:.1f}s | video {video_secs:.2f}s -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
