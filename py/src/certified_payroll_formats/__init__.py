"""Machine-readable reference data and zero-dependency validators for US certified payroll.

Covers the federal WH-347 baseline and the three states that publish a machine-readable
format: California eCPR, New York's bulk upload XML, and Washington's PWIA upload.

Nothing here is legal advice. Every claim traces to an official source recorded in
``data/sources.json``; the linked sources govern.
"""

from .data import (
    conflicts, elements, format_data, jurisdiction, jurisdictions, resolve_sources,
    rule, rules, sources, wh347_data,
)
from .finding import summarize
from .validate_ca import CA_NAMESPACE, validate_ca_ecpr
from .validate_ny import validate_ny_cert_payroll
from .wh347 import check_wh347, field_map, to_wh347, total_hours
from .xml_reader import XmlError, parse_xml

__version__ = "0.1.0"

__all__ = [
    "CA_NAMESPACE", "XmlError", "check_wh347", "conflicts", "elements", "field_map",
    "format_data", "jurisdiction", "jurisdictions", "parse_xml", "resolve_sources",
    "rule", "rules", "sources", "summarize", "to_wh347", "total_hours",
    "validate_ca_ecpr", "validate_ny_cert_payroll", "wh347_data",
]
