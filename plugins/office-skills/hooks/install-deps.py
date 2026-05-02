#!/usr/bin/env python3
"""SessionStart hook for office-skills plugin.

Идемпотентно ставит pip-зависимости из requirements.txt и проверяет наличие .env.
Запускается на каждый SessionStart, но отрабатывает реальную установку только если
содержимое requirements.txt изменилось (хэш + маркер `.installed`).

Никогда не валит сессию — все исключения проглатываются и логируются в stderr.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path


def _plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env)
    # fallback: hooks/ → plugin root
    return Path(__file__).resolve().parent.parent


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _ensure_deps(plugin_root: Path) -> None:
    req = plugin_root / "requirements.txt"
    if not req.exists():
        return
    marker = plugin_root / ".installed"
    cur_hash = _hash_file(req)
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == cur_hash:
        return
    print(f"[office-skills] installing pip deps from {req} ...", file=sys.stderr)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "--quiet", "-r", str(req)],
            check=True,
        )
        marker.write_text(cur_hash, encoding="utf-8")
        print("[office-skills] pip deps installed", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"[office-skills] pip install failed: {exc}", file=sys.stderr)


def _walk_for_env(start: Path, depth: int = 8) -> Path | None:
    cur = start.resolve()
    for _ in range(depth):
        cand = cur / ".env"
        if cand.exists():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _check_env(plugin_root: Path) -> None:
    env_path = _walk_for_env(Path.cwd())
    has_token = bool(os.environ.get("YANDEX_TOKEN"))
    if env_path is not None:
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("YANDEX_TOKEN=") and line.split("=", 1)[1].strip():
                    has_token = True
                    break
        except Exception:
            pass
    if not has_token:
        example = plugin_root / ".env.example"
        msg = (
            "[office-skills] YANDEX_TOKEN не найден. "
            f"Скопируй {example} в корень рабочего проекта как .env и заполни токены."
        )
        print(msg, file=sys.stderr)


def main() -> int:
    try:
        root = _plugin_root()
        _ensure_deps(root)
        _check_env(root)
    except Exception as exc:  # noqa: BLE001
        print(f"[office-skills] hook error (ignored): {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
