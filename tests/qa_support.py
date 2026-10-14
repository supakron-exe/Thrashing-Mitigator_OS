"""Keep generated test reports and isolated profiles out of source and docs."""
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
QA_ROOT = ROOT / "build" / "qa"
for folder in (QA_ROOT, QA_ROOT / "screenshots", QA_ROOT / "insights",
               QA_ROOT / "insights_visual", QA_ROOT / "profiles"):
    folder.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(QA_ROOT / "profiles")


def qa_path(*parts):
    """Return a generated artifact path with its parent directory ready."""
    path = QA_ROOT.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
