#!/usr/bin/env python3
"""Check that the JavaScript and Python validators agree on every mutation of a fixture.

The two implementations are written independently and must stay interchangeable. Unit
tests catch what someone thought to test; this walks every element in each fixture and
mutates it four ways — drop it, duplicate it, blank it, corrupt it — then asserts that
both implementations report exactly the same set of rule ids for every mutant.

    python3 tools/differential.py           # exits non-zero on any divergence or crash
    python3 tools/differential.py --verbose # also list the mutations that agreed

Requires node on PATH. No other dependencies.
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py" / "src"))

from certified_payroll_formats import validate_ca_ecpr, validate_ny_cert_payroll  # noqa: E402

FIXTURES = [("ca", "fixtures/ca/valid.xml"), ("ny", "fixtures/ny/valid.xml")]
VALIDATORS = {"ca": validate_ca_ecpr, "ny": validate_ny_cert_payroll}


def run_js(fmt, path):
    result = subprocess.run(
        ["node", str(ROOT / "js" / "src" / "cli.js"), "validate", fmt, path, "--json"],
        capture_output=True, text=True, cwd=ROOT,
    )
    if not result.stdout.strip():
        tail = result.stderr.strip().splitlines()
        return "CRASH", tail[-1] if tail else "no output"
    return "OK", sorted(f["ruleId"] for f in json.loads(result.stdout)["findings"])


def run_py(fmt, path, filename):
    try:
        result = VALIDATORS[fmt](pathlib.Path(path).read_text(encoding="utf-8"), filename=filename)
        return "OK", sorted(f["ruleId"] for f in result["findings"])
    except Exception as error:  # noqa: BLE001 - a crash is exactly what we are looking for
        return "CRASH", f"{type(error).__name__}: {error}"


def mutations(source):
    """One edit at a time: drop an element, duplicate it, blank it, or corrupt its text."""
    names = []
    for match in re.finditer(r"<((?:CPR:)?[A-Za-z0-9]+)(?:\s[^>]*)?>", source):
        if match.group(1) not in names:
            names.append(match.group(1))
    for name in names:
        block_re = re.compile(
            r"[ \t]*<" + re.escape(name) + r"(\s[^>]*)?>.*?</" + re.escape(name) + r">\n?", re.S)
        block = block_re.search(source)
        if not block:
            continue
        text = block.group(0)
        yield f"drop:{name}", source[:block.start()] + source[block.end():]
        yield f"dup:{name}", source[:block.end()] + text + source[block.end():]
        inner = re.compile(
            r"(<" + re.escape(name) + r"(?:\s[^>]*)?>)(.*?)(</" + re.escape(name) + r">)", re.S)
        found = inner.search(source)
        if found and "<" not in found.group(2):
            head, tail = source[:found.start()], source[found.end():]
            yield f"blank:{name}", head + found.group(1) + found.group(3) + tail
            yield f"junk:{name}", head + found.group(1) + "ZZ~9" + found.group(3) + tail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    total = divergences = crashes = 0
    for fmt, fixture in FIXTURES:
        source = (ROOT / fixture).read_text(encoding="utf-8")
        for label, mutant in mutations(source):
            total += 1
            handle = tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False,
                                                 encoding="utf-8")
            handle.write(mutant)
            handle.close()
            try:
                js = run_js(fmt, handle.name)
                py = run_py(fmt, handle.name, os.path.basename(handle.name))
            finally:
                os.unlink(handle.name)

            if js[0] == "CRASH" or py[0] == "CRASH":
                crashes += 1
                print(f"CRASH  {fmt} {label}\n    js: {js}\n    py: {py}")
            elif js[1] != py[1]:
                divergences += 1
                print(f"DIFF   {fmt} {label}\n    js: {js[1]}\n    py: {py[1]}")
            elif args.verbose:
                print(f"ok     {fmt} {label}: {js[1]}")

    print(f"\n{total} mutations, {divergences} divergences, {crashes} crashes")
    return 1 if (divergences or crashes) else 0


if __name__ == "__main__":
    sys.exit(main())
