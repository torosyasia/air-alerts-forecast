"""Rewrite auto-generated blocks of README.md / REPORT.md (between <!-- NAME:START --> and <!-- NAME:END -->).

Only these blocks change when the pipeline runs on new data (the forecast and the data
dates). The narrative and the result tables describe the pinned snapshot they were written
for; after `run_all.py --latest` the regenerated files in results/, reports/ and figures/
carry the new numbers.
"""
import re

from .config import ROOT


def update_blocks(blocks, path=ROOT / "README.md"):
    text = path.read_text(encoding="utf-8")
    for name, body in blocks.items():
        pat = re.compile(rf"(<!-- {name}:START -->\n).*?(<!-- {name}:END -->)", re.S)
        if not pat.search(text):
            raise KeyError(f"README has no block {name}")
        text = pat.sub(lambda m: m.group(1) + body.rstrip("\n") + "\n" + m.group(2), text)
    path.write_text(text, encoding="utf-8")
