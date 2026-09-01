"""certified-payroll — query the dataset, or validate a file against a published format."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import data
from .validate_ca import validate_ca_ecpr
from .validate_ny import validate_ny_cert_payroll


def _print_findings(result: dict, filename: str, as_json: bool, quiet: bool) -> None:
    if as_json:
        print(json.dumps({"file": filename, **result}, indent=2))
        return
    shown = [f for f in result["findings"] if f["severity"] == "error"] if quiet else result["findings"]
    for f in shown:
        where = " · ".join(x for x in (f"line {f['line']}" if f["line"] else None, f["path"]) if x)
        print(f'{f["severity"].upper()}  {f["message"]}')
        print(f"      {where}")
        if f["expected"] is not None:
            print(f'      expected: {f["expected"]}')
        if f["actual"] is not None:
            print(f'      actual:   {f["actual"]}')
        print(f'      rule {f["ruleId"]} — {" ".join(s["url"] for s in f["sources"])}')
        print()
    counts = result["counts"]
    print(f'{filename}: {counts["error"]} error(s), {counts["warning"]} warning(s), '
          f'{counts["advisory"]} advisory')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="certified-payroll",
        description="US certified payroll formats, as data. Not legal advice; the linked official sources govern.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate a file against a published format")
    validate.add_argument("format", choices=["ca", "ny"])
    validate.add_argument("file")
    validate.add_argument("--quiet", action="store_true", help="suppress warnings and advisories")

    sub.add_parser("jurisdictions", help="list the covered filing regimes")
    show = sub.add_parser("show", help="one jurisdiction")
    show.add_argument("id")
    rules_cmd = sub.add_parser("rules", help="documented rules for a format")
    rules_cmd.add_argument("format", choices=["ca-ecpr", "ny-certpayroll", "wa-pwia"])
    rule_cmd = sub.add_parser("rule", help="one rule, with its official sources")
    rule_cmd.add_argument("id")
    elements_cmd = sub.add_parser("elements", help="the element tree extracted from the published XSD")
    elements_cmd.add_argument("format", choices=["ca-ecpr", "ny-certpayroll"])
    sub.add_parser("conflicts", help="where a schema and its own documentation disagree")
    sub.add_parser("wh347", help="the WH-347 field map")

    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            with open(args.file, encoding="utf-8") as handle:
                xml = handle.read()
        except OSError as error:
            print(f"certified-payroll: cannot read {args.file}: {error.strerror}", file=sys.stderr)
            return 2
        filename = os.path.basename(args.file)
        result = (validate_ca_ecpr(xml, filename=filename) if args.format == "ca"
                  else validate_ny_cert_payroll(xml, filename=filename))
        _print_findings(result, filename, args.json, args.quiet)
        return 0 if result["valid"] else 1

    if args.command == "jurisdictions":
        if args.json:
            print(json.dumps(data.jurisdictions(), indent=2))
        else:
            for j in data.jurisdictions():
                print(f'{j["id"]:<6}  {j["name"]:<38} {j["filingFrequency"]["value"]}')
        return 0

    if args.command == "show":
        found = data.jurisdiction(args.id)
        if not found:
            print(f"Unknown jurisdiction: {args.id}", file=sys.stderr)
            return 2
        print(json.dumps(found, indent=2))
        return 0

    if args.command == "rules":
        listing = data.rules(args.format)
        if args.json:
            print(json.dumps(listing, indent=2))
        else:
            for r in listing:
                print(f'{r["severity"]:<9} {r["id"]}')
                print(f'          {r["statement"]}')
                print(f'          {" ".join(s["url"] for s in r["sources"])}')
                print()
        return 0

    if args.command == "rule":
        found = data.rule(args.id)
        if not found:
            print(f"Unknown rule: {args.id}", file=sys.stderr)
            return 2
        print(json.dumps(found, indent=2))
        return 0

    if args.command == "elements":
        listing = data.elements(args.format)
        if args.json:
            print(json.dumps(listing, indent=2))
        else:
            for e in listing:
                occurs = f'[{e["minOccurs"]}..{e["maxOccurs"]}]'
                suffix = f'  {e["type"]}' if e.get("type") else ""
                print(f'{occurs:<12} {e["path"]}{suffix}')
        return 0

    if args.command == "conflicts":
        listing = data.conflicts()
        if args.json:
            print(json.dumps(listing, indent=2))
        else:
            for c in listing:
                element = f' · {c["element"]}' if c.get("element") else ""
                print(f'{c["id"]}  ({c["format"]}{element})')
                print(f'  {c["resolution"]}')
                print()
        return 0

    if args.command == "wh347":
        print(json.dumps(data.wh347_data(), indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
