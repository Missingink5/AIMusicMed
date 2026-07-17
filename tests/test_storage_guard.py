from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from webapp.storage_guard import storage_status


class StorageGuardTests(unittest.TestCase):
    def settings(self, root: Path):
        return SimpleNamespace(
            storage_root=root,
            disk_warning_percent=70,
            disk_cleanup_percent=80,
            disk_upload_stop_percent=85,
            disk_generation_stop_percent=90,
            disk_resume_percent=75,
        )

    def usage(self, percent: int):
        total = 1000
        used = percent * 10
        return SimpleNamespace(total=total, used=used, free=total - used)

    def test_stop_states_resume_only_below_seventy_five_percent(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = self.settings(Path(folder))
            with patch(
                "webapp.storage_guard.shutil.disk_usage",
                return_value=self.usage(91),
            ):
                critical = storage_status(settings)
            self.assertFalse(critical["uploads_allowed"])
            self.assertFalse(critical["generation_allowed"])

            with patch(
                "webapp.storage_guard.shutil.disk_usage",
                return_value=self.usage(76),
            ):
                still_blocked = storage_status(settings)
            self.assertFalse(still_blocked["uploads_allowed"])
            self.assertFalse(still_blocked["generation_allowed"])

            with patch(
                "webapp.storage_guard.shutil.disk_usage",
                return_value=self.usage(74),
            ):
                resumed = storage_status(settings)
            self.assertTrue(resumed["uploads_allowed"])
            self.assertTrue(resumed["generation_allowed"])

    def test_warning_cleanup_and_upload_thresholds(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = self.settings(Path(folder))
            for percent, level in ((70, "warning"), (80, "cleanup"), (85, "upload_stop")):
                with self.subTest(percent=percent), patch(
                    "webapp.storage_guard.shutil.disk_usage",
                    return_value=self.usage(percent),
                ):
                    result = storage_status(settings)
                    self.assertEqual(result["level"], level)


if __name__ == "__main__":
    unittest.main()
