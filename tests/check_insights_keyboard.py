"""Keyboard and focus regression checks for the inline Insights design."""
import subprocess
import sys
from pathlib import Path
raise SystemExit(subprocess.call([sys.executable,str(Path(__file__).with_name('check_insights_visual.py')),'--theme','light','--language','th','--exercise']))
