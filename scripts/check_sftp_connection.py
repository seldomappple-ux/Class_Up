from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from class_up.config import UploadConfig


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    config = UploadConfig()
    host = os.environ.get(config.host_env, "").strip()
    username = os.environ.get(config.username_env, "").strip()
    key_path = os.environ.get(config.private_key_path_env, "").strip()

    missing = [
        env_name
        for env_name, value in (
            (config.host_env, host),
            (config.username_env, username),
            (config.private_key_path_env, key_path),
        )
        if not value
    ]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        return 1

    key_file = Path(key_path)
    if not key_file.exists():
        print(f"Private key file not found: {key_file}", file=sys.stderr)
        return 1

    try:
        import paramiko  # type: ignore
    except ModuleNotFoundError:
        print("paramiko is required. Install dependencies with: pip install -e .[web]", file=sys.stderr)
        return 1

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print(f"Connecting to {username}@{host}:{config.port}")
    try:
        client.connect(
            hostname=host,
            port=config.port,
            username=username,
            key_filename=str(key_file),
            timeout=30,
        )
        sftp = client.open_sftp()
        try:
            remote_dir = config.remote_dir.rstrip("/")
            attrs = sftp.stat(remote_dir)
            print("SFTP connection OK")
            print(f"Remote directory exists: {remote_dir}")
            print(f"Remote directory mode: {attrs.st_mode}")
            print(f"Public URL base: {config.public_url_base}")
        finally:
            sftp.close()
    except Exception as exc:
        print(f"SFTP check failed: {exc}", file=sys.stderr)
        return 2
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
