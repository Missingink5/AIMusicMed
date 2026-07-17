from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path


def storage_status(settings) -> dict[str, int | str | bool]:
    """Return disk pressure and persist stop-state hysteresis across processes."""
    root = Path(settings.storage_root)
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(root)
    percent = int(round((usage.used / usage.total) * 100)) if usage.total else 100
    state_path = root / ".storage-protection.json"
    state = {"uploads_blocked": False, "generation_blocked": False}
    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            state.update({
                "uploads_blocked": bool(loaded.get("uploads_blocked")),
                "generation_blocked": bool(loaded.get("generation_blocked")),
            })
    except (FileNotFoundError, OSError, ValueError):
        pass

    if percent >= settings.disk_upload_stop_percent:
        state["uploads_blocked"] = True
    if percent >= settings.disk_generation_stop_percent:
        state["generation_blocked"] = True
    if percent < settings.disk_resume_percent:
        state = {"uploads_blocked": False, "generation_blocked": False}

    try:
        handle, temporary_name = tempfile.mkstemp(
            dir=root, prefix=".storage-protection-", suffix=".tmp"
        )
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(state, stream, separators=(",", ":"))
        Path(temporary_name).replace(state_path)
    except OSError:
        try:
            Path(temporary_name).unlink(missing_ok=True)
        except (NameError, OSError):
            pass

    if state["generation_blocked"]:
        level = "generation_stop"
    elif state["uploads_blocked"]:
        level = "upload_stop"
    elif percent >= settings.disk_cleanup_percent:
        level = "cleanup"
    elif percent >= settings.disk_warning_percent:
        level = "warning"
    else:
        level = "ok"
    return {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": percent,
        "level": level,
        "uploads_allowed": not state["uploads_blocked"],
        "generation_allowed": not state["generation_blocked"],
    }
