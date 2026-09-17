"""Совместимость со старым импортом."""

from core.paths import dated_out_dir, rollover_day_folders
from core.service import DownloadService

__all__ = ["DownloadService", "dated_out_dir", "rollover_day_folders"]
