# ae-video-studio

A Claude Code plugin for making polished, motion-designed videos in **Adobe After Effects**:
from footage, voice recordings and a short brief to a 4K master, with a preview you approve
before every creative or expensive step (story → design & fonts → grade → 15 s test →
key stills → review render → master).

> Status: early. The design is in [`docs/design.md`](docs/design.md). Skills are being
> generalised from a first real production; no project footage, audio, names or logos are
> kept in this repo.

## Requirements

- After Effects 2025+ with the MCP Bridge Auto panel (Auto-run on)
- after-effects-mcp with the `runJsx` command (see `bridge/runJsx.patch`)
- ffmpeg, Python 3.10+ with Pillow, mlx-whisper

## Engine quick start

```bash
python3 examples/demo/make_media.py                    # fictional demo media (needs ffmpeg)
cd engine
python3 -m unittest discover -s tests -t . -v          # unit tests (no After Effects needed)
python3 -m aestudio validate ../examples/demo/edit.json --design notebook
# with After Effects + MCP Bridge Auto panel open and a new project:
python3 -m aestudio build ../examples/demo/edit.json --design cinematic-minimal --project ../examples/demo/build/demo.aep
```

Look at footage and pick a design before building:

```bash
python3 -m aestudio log-footage ../examples/demo/media --out /tmp/demo-analysis
python3 -m aestudio design-propose --analysis /tmp/demo-analysis --out /tmp/demo-preview --mood warm
python3 -m aestudio design-preview --dir /tmp/demo-preview
```

See `docs/components.md` for the edit-plan graphics and `skills/ae-build-render/SKILL.md` for the full workflow.

## Local plugin install

```
/plugin marketplace add ~/github.com/Exotica0122/ae-video-studio
/plugin install ae-video-studio@ae-video-studio-dev
```

## Layout

```
.claude-plugin/   plugin + dev marketplace manifests
docs/design.md    flow, gates, skills, edit-plan format, lessons learned
skills/           one folder per skill (in progress); ae-build-render, footage-logging, design-system
engine/aestudio/  media.py ffprobe/ffmpeg helpers, footage.py footage logging, transcribe.py Whisper
                  import, fonts.py installed-font catalogue, designgen.py compose design drafts,
                  styleframe.py render mockup HTML, preview.py serve mockups + record the choice
lib/              shared After Effects primitives + component contracts (in progress)
designs/          saved design recipes (notebook, cinematic-minimal, …); new ones are generated per video
bridge/           runJsx patch for after-effects-mcp
examples/         fictional sample assets (e.g. sample-logo-white.png)
```
