"""Run from the project root: python scripts/generate_samples.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.sample_data import generate_samples

print(generate_samples())
