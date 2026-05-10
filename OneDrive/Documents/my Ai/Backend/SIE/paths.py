"""Paths for Society Intelligence Engine — isolated under Data/SIE."""

from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
PROJECT_ROOT = _BACKEND.parent
SIE_DATA_DIR = PROJECT_ROOT / "Data" / "SIE"
SIE_DB_PATH = SIE_DATA_DIR / "sie_memory.db"
