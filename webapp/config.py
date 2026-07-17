from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    storage_root: Path
    fernet_key: str
    worker_token: str
    admin_email: str = ""
    dev_auth_codes: bool = False
    secure_cookies: bool = True
    session_days: int = 30
    public_base_url: str = ""
    tencentcloud_secret_id: str = ""
    tencentcloud_secret_key: str = ""
    tencentcloud_region: str = "ap-hongkong"
    ses_from: str = ""
    ses_template_id: int = 0
    global_task_concurrency: int = 1

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(os.getenv("AIMUSICMED_WEB_DATA", "webapp-data")).resolve()
        fernet_key = os.getenv("AIMUSICMED_FERNET_KEY", "")
        worker_token = os.getenv("AIMUSICMED_WORKER_TOKEN", "")
        if not fernet_key:
            raise RuntimeError("AIMUSICMED_FERNET_KEY is required")
        if len(worker_token) < 24:
            raise RuntimeError("AIMUSICMED_WORKER_TOKEN must be at least 24 characters")
        global_task_concurrency = int(os.getenv("AIMUSICMED_GLOBAL_TASK_CONCURRENCY", "1"))
        if global_task_concurrency not in (1, 2):
            raise RuntimeError("AIMUSICMED_GLOBAL_TASK_CONCURRENCY must be 1 or 2")
        return cls(
            database_path=Path(os.getenv("AIMUSICMED_DB_PATH", root / "app.db")).resolve(),
            storage_root=Path(os.getenv("AIMUSICMED_STORAGE_ROOT", root / "storage")).resolve(),
            fernet_key=fernet_key,
            worker_token=worker_token,
            admin_email=os.getenv("AIMUSICMED_ADMIN_EMAIL", "").strip().lower(),
            dev_auth_codes=os.getenv("AIMUSICMED_DEV_AUTH_CODES", "false").lower() == "true",
            secure_cookies=os.getenv("AIMUSICMED_SECURE_COOKIES", "true").lower() == "true",
            public_base_url=os.getenv("AIMUSICMED_PUBLIC_BASE_URL", "").rstrip("/"),
            tencentcloud_secret_id=os.getenv("TENCENTCLOUD_SECRET_ID", "").strip(),
            tencentcloud_secret_key=os.getenv("TENCENTCLOUD_SECRET_KEY", "").strip(),
            tencentcloud_region=os.getenv("TENCENTCLOUD_REGION", "ap-hongkong").strip(),
            ses_from=os.getenv("AIMUSICMED_SES_FROM", "").strip(),
            ses_template_id=int(os.getenv("AIMUSICMED_SES_TEMPLATE_ID", "0")),
            global_task_concurrency=global_task_concurrency,
        )
