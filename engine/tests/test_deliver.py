import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from aestudio import deliver as dv
from aestudio.__main__ import main


def _clip(path, size="640x360", seconds=4):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=24:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}", "-af", "volume=0.05",
                    "-c:v", "prores_ks", "-profile:v", "0", "-c:a", "pcm_s16le", "-shortest", str(path)], check=True)


class SizesTest(unittest.TestCase):
    def test_parses_4k_heights_and_master(self):
        self.assertEqual(dv.parse_sizes("4k, 1080p,master"), [2160, 1080, None])

    def test_rejects_unknown_size(self):
        with self.assertRaisesRegex(dv.DeliverError, "unknown size 'huge'"):
            dv.parse_sizes("huge")

    def test_vertical_master_scales_its_short_side(self):
        self.assertEqual(dv._target_size(2160, 3840, 1080), (1080, 1920))

    def test_refuses_to_upscale(self):
        with self.assertRaisesRegex(dv.DeliverError, "refusing to upscale"):
            dv._target_size(1920, 1080, 2160)

    def test_audio_chain_matches_the_hand_made_delivery(self):
        self.assertEqual(dv.audio_filter(-16, -2), "loudnorm=I=-16:TP=-2:LRA=11,alimiter=limit=0.794:level=false")

    def test_encode_args_are_streamable_h264(self):
        args = dv.encode_args("m.mov", "o.mp4", 3840, 2160, 1080, True)
        for flag in ("libx264", "yuv420p", "320k", "+faststart", "scale=-2:1080"):
            self.assertIn(flag, args)


class ArchiveTest(unittest.TestCase):
    def test_moves_previous_files_into_the_next_free_folder(self):
        with tempfile.TemporaryDirectory() as d:
            final = Path(d)
            (final / "previous-v01").mkdir()
            (final / "old-4k.mp4").write_text("x")
            (final / "master.mov").write_text("x")
            dest = dv.archive_previous(final, keep=[final / "master.mov"])
            self.assertEqual(dest.name, "previous-v02")
            self.assertTrue((dest / "old-4k.mp4").exists())
            self.assertTrue((final / "master.mov").exists())

    def test_nothing_to_archive(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(dv.archive_previous(d))


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
class DeliverPipelineTest(unittest.TestCase):
    def test_encodes_normalises_archives_and_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            master = root / "master.mov"
            _clip(master)
            final = root / "exports" / "final"
            final.mkdir(parents=True)
            (final / "DEMO-360p.mp4").write_text("old")
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["deliver", "--master", str(master), "--name", "DEMO", "--sizes", "master,180",
                             "--out", str(final)])
            result = json.loads(out.getvalue())
            self.assertEqual(code, 0, result)
            self.assertTrue(result["archived"].endswith("previous-v01"))
            self.assertEqual((Path(result["archived"]) / "DEMO-360p.mp4").read_text(), "old")
            by_name = {Path(o["file"]).name: o for o in result["outputs"]}
            self.assertEqual(sorted(by_name), ["DEMO-180p.mp4", "DEMO-360p.mp4"])
            self.assertEqual((by_name["DEMO-180p.mp4"]["width"], by_name["DEMO-180p.mp4"]["height"]), (320, 180))
            for o in result["outputs"]:
                self.assertAlmostEqual(o["lufs"], -16.0, delta=1.0)
                self.assertLessEqual(o["true_peak"], -1.5)
                self.assertAlmostEqual(o["duration"], 4.0, delta=0.1)

    def test_needs_a_master_or_a_comp_to_render(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(dv.DeliverError, "--project and --comp"):
                dv.deliver(d, "X", [1080])


if __name__ == "__main__":
    unittest.main()
