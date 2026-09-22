import os
from pathlib import Path

# Tests see the catalogue fonts as installed on every machine, CI included.
os.environ["AESTUDIO_FONT_DIRS"] = str(Path(__file__).resolve().parent / "fixtures" / "fonts")
