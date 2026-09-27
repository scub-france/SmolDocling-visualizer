import sys
from pathlib import Path

# The scripts import their sibling modules (qasper, sections) the way `uv run` does.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
