"""Raw data: verify the pinned snapshot, or download the newest versions (--latest).

Pinned (default): every file listed in data/raw/MANIFEST.json is downloaded if missing from
its exact-commit URL and checked against its sha256. The run reproduces the README numbers.

Latest: for GitHub sources the current head commit of the branch is resolved with
`git ls-remote` and the file is downloaded from that commit; KMDA is downloaded from
data.gov.ua as a new dated snapshot. The manifest is rewritten with the new pins, so the
refreshed state is itself reproducible once committed.
"""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone

from .config import MANIFEST, RAW, SOURCE_SPECS, TZ, pinned


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, path):
    tmp = path.with_suffix(path.suffix + ".part")
    subprocess.run(["curl", "-sSfL", "--retry", "4", "-m", "600", "-A", "Mozilla/5.0", "-o", str(tmp), url],
                   check=True)
    tmp.replace(path)


def fetch_pinned():
    RAW.mkdir(parents=True, exist_ok=True)
    for name, pin in pinned().items():
        path = RAW / pin["file"]
        if not path.exists():
            if pin.get("committed"):
                sys.exit(f"[fetch] {name}: committed snapshot {path} is missing")
            print(f"[fetch] {name}: {pin['url']}")
            download(pin["url"], path)
        digest = sha256(path)
        if digest != pin["sha256"]:
            sys.exit(f"[fetch] {name}: sha256 mismatch {digest} != pinned {pin['sha256']}")
    return pinned()


def head_commit(repo, branch):
    out = subprocess.run(["git", "ls-remote", f"https://github.com/{repo}", f"refs/heads/{branch}"],
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"cannot resolve {repo}@{branch}: {out.stderr.strip()}")
    return out.stdout.split()[0]


def fetch_latest():
    """Download the newest version of every source and rewrite the manifest."""
    RAW.mkdir(parents=True, exist_ok=True)
    old, new = pinned(), {}
    for name, spec in SOURCE_SPECS.items():
        try:
            if "repo" in spec:
                sha = head_commit(spec["repo"], spec["branch"])
                url = f"https://raw.githubusercontent.com/{spec['repo']}/{sha}/{spec['file']}"
                ver = sha[:7]
            else:
                url, ver = spec["url"], datetime.now(timezone.utc).date().isoformat()
            path = RAW / spec["local"].format(ver=ver)
            if not path.exists():
                print(f"[fetch --latest] {name}: {url}")
                download(url, path)
            digest = sha256(path)
            if digest == old[name]["sha256"] and path.name != old[name]["file"]:
                path.unlink()               # same content as the pinned file: keep the old pin
                new[name] = old[name]
                continue
            new[name] = {"url": url, "file": path.name, "sha256": digest, "version": ver}
            if spec.get("committed"):
                new[name]["committed"] = True
        except Exception as exc:  # keep the previous pin rather than failing the whole run
            print(f"[fetch --latest] {name}: FAILED ({exc}); keeping pinned version {old[name]['version']}")
            new[name] = old[name]
    MANIFEST.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if new["kmda"]["file"] != old["kmda"]["file"]:
        # Kyiv switches to alerts.in.ua at local midnight of the last (possibly partial) KMDA
        # day. Fixed here, once per pinned snapshot, so the backtest never derives it from data
        # that appeared after a forecast origin (config.kmda_to_archive_cut).
        from .sources import load_kmda
        kmda, _ = load_kmda()
        new["kmda"]["kyiv_archive_from"] = kmda.started_at.max().tz_convert(TZ).date().isoformat()
        MANIFEST.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name in new:
        print(f"[fetch --latest] {name}: {old[name]['version']} -> {new[name]['version']}")
    return new


if __name__ == "__main__":
    fetch_latest() if "--latest" in sys.argv else fetch_pinned()
