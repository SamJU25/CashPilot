"""Adds a narrated voice-over to CashPilot_Demo.mp4 (pip install edge-tts imageio-ffmpeg; needs internet for TTS).

Run from the repository root after record_demo.py:  python submission/03-demo-video/add_voiceover.py
Scene start times were measured from the recorded video; re-measure them if record_demo.py changes.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts
import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
VIDEO = HERE / "CashPilot_Demo.mp4"
VOICE = "en-US-AndrewNeural"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# (scene start in seconds, narration)
SCRIPT = [
    (0.5, "This is CashPilot, a finance copilot for small-business owners."),
    (5.5, "The owner starts with the bank statements they already download. There is no bank login and no accounting software."),
    (15.5, "Here is our sample coffee roaster. Payroll on October twenty-eighth takes the balance below zero, nine days from now. "
           "CashPilot shows the gap and has already drafted a fix. Below that sit the working-capital ratios."),
    (29.0, "Funding offers are ranked by fit, and each one is converted to a true APR. "
           "This advance is quoted as a factor rate of one point three five. That is really seventy-one percent a year, so it is flagged as predatory."),
    (43.0, "Receivables shows who owes money and how late they are."),
    (50.5, "In the assistant, the owner asks a question in plain words. Every figure comes from exact calculations. "
           "The model running on this computer only writes the sentences, and an answer that invents a number is thrown away."),
    (72.5, "The agent can draft a credit-line draw, but only the owner can act on it. There is no execute button."),
    (80.0, "Now an attack: a prompt injection asking the agent to wire fifty thousand dollars. It is blocked before routing, and nothing is staged."),
    (93.0, "Last, live mode. A real three-month statement goes to the backend. It parses ninety-four transactions, scores them for funding, "
           "and the overview switches to the live forecast: this account runs short on June twenty-eighth."),
    (116.5, "Nine hundred sixty-three tests pass, and every attack in our sandbox replay was refused. CashPilot never moves the owner's money."),
]


def duration(path: Path) -> float:
    out = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


async def synthesize(workdir: Path) -> list[Path]:
    clips = []
    for i, (_, text) in enumerate(SCRIPT):
        clip = workdir / f"line{i:02d}.mp3"
        await edge_tts.Communicate(text, VOICE, rate="+4%").save(str(clip))
        clips.append(clip)
    return clips


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="cashpilot_vo_"))
    clips = asyncio.run(synthesize(workdir))
    total = duration(VIDEO)
    starts = [start for start, _ in SCRIPT]
    for i, clip in enumerate(clips):
        end = starts[i] + duration(clip)
        limit = starts[i + 1] if i + 1 < len(starts) else total
        print(f"line {i}: {starts[i]:6.1f}s -> {end:6.1f}s (next at {limit:6.1f}s)")
        if end > limit + 0.05:
            raise SystemExit(f"line {i} overruns the next scene by {end - limit:.1f}s; shorten it")

    inputs, filters = [], []
    for i, clip in enumerate(clips):
        inputs += ["-i", str(clip)]
        ms = int(starts[i] * 1000)
        filters.append(f"[{i + 1}:a]adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(clips)))
    filters.append(f"{mix}amix=inputs={len(clips)}:normalize=0:duration=longest[aout]")
    out = workdir / "narrated.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(VIDEO), *inputs, "-filter_complex", ";".join(filters),
                    "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}",
                    "-movflags", "+faststart", str(out)], check=True)
    shutil.move(str(out), str(VIDEO))  # temp dir may be on another drive
    print("narrated video:", VIDEO, f"{VIDEO.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
