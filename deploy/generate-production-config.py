from __future__ import annotations

import argparse
import csv
import json
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet


def read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def required(value: str | None, name: str) -> str:
    normalized = (value or "").strip()
    if not normalized or "CHANGE_ME" in normalized or "YOUR_" in normalized.upper():
        raise RuntimeError(f"Missing usable {name}")
    if "\n" in normalized or "\r" in normalized:
        raise RuntimeError(f"{name} must be a single line")
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--project-env", type=Path, required=True)
    parser.add_argument("--project-config", type=Path, required=True)
    parser.add_argument("--cam-csv", type=Path, required=True)
    parser.add_argument("--output-env", type=Path, required=True)
    args = parser.parse_args()

    dotenv = read_dotenv(args.project_env)
    config = json.loads(args.project_config.read_text(encoding="utf-8-sig"))
    api_keys = config.get("api_keys", {})
    with args.cam_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        cam = next(csv.DictReader(handle), None)
    if not cam:
        raise RuntimeError("CAM CSV has no credential row")

    deepseek = required(dotenv.get("DEEPSEEK_API_KEY") or api_keys.get("deepseek_api_key"), "DeepSeek API key")
    minimax = required(dotenv.get("MINIMAX_API_KEY") or api_keys.get("minimax_api_key"), "MiniMax API key")
    elevenlabs = (dotenv.get("ELEVENLABS_API_KEY") or api_keys.get("elevenlabs_api_key") or "").strip()
    cam_id = required(cam.get("SecretId"), "Tencent CAM SecretId")
    cam_key = required(cam.get("SecretKey"), "Tencent CAM SecretKey")

    admin_email = required(args.admin_email, "admin email").lower()
    if admin_email.count("@") != 1:
        raise RuntimeError("Admin email is invalid")
    values = {
        "AIMUSICMED_DOMAIN": "aimusicmed.cn",
        "AIMUSICMED_ACME_EMAIL": admin_email,
        "AIMUSICMED_FERNET_KEY": Fernet.generate_key().decode("ascii"),
        "AIMUSICMED_WORKER_TOKEN": secrets.token_hex(32),
        "AIMUSICMED_ADMIN_EMAIL": admin_email,
        "AIMUSICMED_DEV_AUTH_CODES": "false",
        "AIMUSICMED_SECURE_COOKIES": "true",
        "AIMUSICMED_PUBLIC_BASE_URL": "https://aimusicmed.cn",
        "TENCENTCLOUD_SECRET_ID": cam_id,
        "TENCENTCLOUD_SECRET_KEY": cam_key,
        "TENCENTCLOUD_REGION": "ap-hongkong",
        "AIMUSICMED_SES_FROM": "AIMusicMed <no-reply@mail.aimusicmed.cn>",
        "AIMUSICMED_SES_TEMPLATE_ID": "208565",
        "AIMUSICMED_GLOBAL_TASK_CONCURRENCY": "1",
        "DEEPSEEK_API_KEY": deepseek,
        "MINIMAX_API_KEY": minimax,
        "ELEVENLABS_API_KEY": elevenlabs,
        "AIMUSICMED_BACKUP_PASSPHRASE": secrets.token_urlsafe(48),
        "AIMUSICMED_BACKUP_KEEP_DAILY": "7",
        "AIMUSICMED_BACKUP_KEEP_WEEKLY": "4",
        "AIMUSICMED_BACKUP_KEEP_MONTHLY": "3",
        "AIMUSICMED_BACKUP_MAX_REPO_MB": "12288",
        "AIMUSICMED_BACKUP_MIN_FREE_MB": "6144",
    }

    args.output_env.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    # Create the file atomically with private permissions (owner read/write only).
    # The file contains every production secret — never let umask weaken this.
    import tempfile as _tmp
    fd, tmp_name = _tmp.mkstemp(
        dir=str(args.output_env.parent), prefix=".env.", suffix=".tmp", text=True,
    )
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp_name, 0o600)
    os.replace(tmp_name, str(args.output_env))
if __name__ == "__main__":
    main()
