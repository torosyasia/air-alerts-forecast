"""Download the pinned raw sources (if not cached) and record their sha256 in MANIFEST.json."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone

from .config import RAW, SOURCES


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_all(force=False):
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for name, src in SOURCES.items():
        path = src["path"]
        if force or not path.exists():
            print(f"[fetch] {name}: {src['url']}")
            subprocess.run(["curl", "-sSfL", "--retry", "4", "-m", "600", "-o", str(path), src["url"]],
                           check=True)
            manifest.setdefault(name, {})["downloaded_at"] = datetime.now(timezone.utc).isoformat()
        digest = sha256(path)
        if src["sha256"] and digest != src["sha256"]:
            sys.exit(f"[fetch] {name}: sha256 mismatch {digest} != pinned {src['sha256']}")
        manifest.setdefault(name, {}).update({"url": src["url"], "file": path.name, "sha256": digest})
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


if __name__ == "__main__":
    fetch_all(force="--force" in sys.argv)
