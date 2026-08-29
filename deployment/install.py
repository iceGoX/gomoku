#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import time
from pathlib import Path

NGINX_SNIPPET = Path("/etc/nginx/snippets/gomoku.conf")
SERVICE_FILE = Path("/etc/systemd/system/gomoku.service")
APP_ROOT = Path("/opt/gomoku")
WEB_ROOT = Path("/var/www/html/wuziqi")
INCLUDE_LINE = "    include /etc/nginx/snippets/gomoku.conf;\n"
DOMAIN_PATTERN = re.compile(r"^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$")


def copy_file(source: Path, target: Path, mode: int = 0o644) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(mode)


def install(source: Path, domain: str) -> None:
    nginx_site = Path("/etc/nginx/sites-available") / domain
    required = [
        source / "index.html",
        source / "styles.css",
        source / "game.js",
        source / "server" / "app.py",
        source / "server" / "game_engine.py",
        source / "deployment" / "gomoku.service",
        source / "deployment" / "nginx-gomoku.conf",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing release files: {', '.join(missing)}")

    for relative in ("server/app.py", "server/game_engine.py", "server/__init__.py"):
        copy_file(source / relative, APP_ROOT / relative)
    for relative in ("index.html", "styles.css", "game.js"):
        copy_file(source / relative, WEB_ROOT / relative)
    copy_file(source / "deployment" / "gomoku.service", SERVICE_FILE)
    copy_file(source / "deployment" / "nginx-gomoku.conf", NGINX_SNIPPET)

    original = nginx_site.read_text(encoding="utf-8")
    backup = nginx_site.with_name(f"{nginx_site.name}.bak-{int(time.time())}")
    if INCLUDE_LINE.strip() not in original:
        marker = "    location / {\n"
        if marker not in original:
            raise SystemExit("Could not locate the nginx root location block")
        backup.write_text(original, encoding="utf-8")
        nginx_site.write_text(original.replace(marker, INCLUDE_LINE + "\n" + marker, 1), encoding="utf-8")

    try:
        subprocess.run(["nginx", "-t"], check=True)
    except subprocess.CalledProcessError:
        if backup.exists():
            shutil.copy2(backup, nginx_site)
        raise

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "gomoku.service"], check=True)
    subprocess.run(["systemctl", "restart", "gomoku.service"], check=True)
    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    print(f"Gomoku installed at https://{domain}/wuziqi/")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--domain", required=True, help="nginx server name and public host")
    args = parser.parse_args()
    if not DOMAIN_PATTERN.fullmatch(args.domain):
        parser.error("--domain must be a valid DNS host name without a scheme, port, or path")
    install(args.source.resolve(), args.domain)


if __name__ == "__main__":
    main()
