"""Generate fictional demo media for ae-video-studio (needs ffmpeg). Output is git-ignored."""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEDIA, TRANSCRIPTS = HERE / "media", HERE / "transcripts"

VOICES = {
    "narration-1": "모든 여정은 작은 한 걸음에서 시작됩니다.",
    "interview-1": "처음에는 망설였지만 함께하니 용기가 생겼어요.",
    "narration-2": "이번 가을, 당신의 첫 걸음을 기다립니다.",
}
SHOTS = {"shot_a": ("0x2b4162", "0xfa9f42"), "shot_b": ("0x0b6e4f", "0xf2e8cf"),
         "shot_c": ("0x6a4c93", "0xffca3a"), "shot_d": ("0x1d3557", "0xe63946")}


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def word_timings(text, lead=0.15):
    t, words = lead, []
    for w in text.split():
        dur = round(0.12 * len(w) + 0.1, 3)
        words.append([w, round(t, 3), round(t + dur, 3)])
        t += dur + 0.08
    return words


def main():
    MEDIA.mkdir(exist_ok=True)
    TRANSCRIPTS.mkdir(exist_ok=True)
    for name, (c0, c1) in SHOTS.items():
        ffmpeg("-f", "lavfi", "-i", f"gradients=s=1920x1080:r=24:d=14:c0={c0}:c1={c1}:speed=0.015",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", str(MEDIA / f"{name}.mp4"))
    for name, text in VOICES.items():
        words = word_timings(text)
        gate = "+".join(f"between(t,{s},{e})" for _, s, e in words)
        total = words[-1][2] + 0.4
        ffmpeg("-f", "lavfi", "-i", f"aevalsrc='0.35*({gate})*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*6*t))':s=48000:d={total}",
               "-ac", "2", str(MEDIA / f"{name}.wav"))
        (TRANSCRIPTS / f"{name}.json").write_text(
            json.dumps({"onset": words[0][1], "offset": words[-1][2], "words": words}, ensure_ascii=False, indent=1), encoding="utf-8")
    ffmpeg("-f", "lavfi", "-i", "aevalsrc='0.08*sin(2*PI*220*t)+0.06*sin(2*PI*277.18*t)+0.05*sin(2*PI*329.63*t)':s=48000:d=45",
           "-af", "afade=t=in:d=2,afade=t=out:st=42:d=3", "-ac", "2", str(MEDIA / "music.wav"))
    ffmpeg("-f", "lavfi", "-i", "anoisesrc=color=pink:d=0.8:a=0.4", "-af", "lowpass=f=1800,afade=t=in:d=0.3,afade=t=out:st=0.4:d=0.4",
           "-ac", "2", "-ar", "48000", str(MEDIA / "whoosh.wav"))
    print(f"demo media written to {MEDIA}")


if __name__ == "__main__":
    main()
