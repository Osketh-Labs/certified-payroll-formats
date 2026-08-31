#!/usr/bin/env python3
"""Copy the canonical dataset into each package so published artifacts are self-contained.

`data/` at the repository root is the single source of truth. Neither npm nor a Python
wheel can reference files above the package directory, so both packages get a copy at
publish time. The copies are generated, not edited, and are not committed — the loaders
fall back to the repository root when no packaged copy is present, which is what happens
when you run from a checkout.

    python3 tools/sync_packages.py
"""

import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data"
TARGETS = [
    ROOT / "js" / "data",
    ROOT / "py" / "src" / "certified_payroll_formats" / "data",
]


def main() -> None:
    for target in TARGETS:
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns("*.md"))
        count = len(list(target.glob("*.json")))
        print(f"{target.relative_to(ROOT)}: {count} files")


if __name__ == "__main__":
    main()
