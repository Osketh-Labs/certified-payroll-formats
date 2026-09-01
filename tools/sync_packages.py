#!/usr/bin/env python3
"""Copy the canonical dataset and the README into each package before publishing.

`data/`, `README.md` and `LICENSE` at the repository root are the single source of truth.
Neither npm nor a Python wheel can reference files above the package directory: npm packs
only what is inside `js/`, and it takes the README it renders on the package page from
there too, so without this the published page would be blank. The copies are generated,
not edited, and are not committed — the data loaders fall back to the repository root when
no packaged copy is present, which is what happens when you run from a checkout.

    python3 tools/sync_packages.py
"""

import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data"
PACKAGES = [ROOT / "js", ROOT / "py"]
DATA_TARGETS = [
    ROOT / "js" / "data",
    ROOT / "py" / "src" / "certified_payroll_formats" / "data",
]
DOCS = ["README.md", "LICENSE"]


def main() -> None:
    for target in DATA_TARGETS:
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns("*.md"))
        count = len(list(target.glob("*.json")))
        print(f"{target.relative_to(ROOT)}: {count} files")
    for package in PACKAGES:
        for name in DOCS:
            shutil.copyfile(ROOT / name, package / name)
            print(f"{(package / name).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
