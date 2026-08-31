"""A small XML reader over the standard library's expat parser.

It mirrors js/src/xml.js: the same node shape, the same namespace handling, the same
refusal of DOCTYPE declarations, and line numbers on every node so findings can point
at a place in the file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional
from xml.parsers import expat

SEP = "\x01"


class XmlError(Exception):
    def __init__(self, message: str, line: Optional[int] = None):
        super().__init__(f"{message} (line {line})" if line else message)
        self.line = line


@dataclass
class Node:
    qname: str
    name: str
    prefix: Optional[str]
    ns: Optional[str]
    attrs: dict
    line: int
    children: list = field(default_factory=list)
    text: str = ""
    parent: Optional["Node"] = field(default=None, repr=False, compare=False)


def parse_xml(source: str) -> Node:
    """Parse a document and return its document element."""
    if not isinstance(source, str):
        raise XmlError("Expected an XML string")

    parser = expat.ParserCreate(namespace_separator=SEP)
    parser.namespace_prefixes = True
    # No agency format uses a DOCTYPE, and accepting one is how entity expansion
    # attacks get in. Refuse the declaration outright rather than configuring around it.
    parser.StartDoctypeDeclHandler = lambda *_: (_ for _ in ()).throw(
        XmlError("DOCTYPE declarations are refused: no agency format uses one, and accepting "
                 "them would open the door to entity expansion attacks", parser.CurrentLineNumber)
    )
    parser.EntityDeclHandler = lambda *_: (_ for _ in ()).throw(
        XmlError("Entity declarations are refused", parser.CurrentLineNumber)
    )
    parser.ExternalEntityRefHandler = lambda *_: 0

    stack: list[Node] = []
    root: list[Optional[Node]] = [None]

    def start(expanded: str, attrs: dict) -> None:
        parts = expanded.split(SEP)
        if len(parts) == 3:
            ns, local, prefix = parts
        elif len(parts) == 2:
            ns, local, prefix = parts[0], parts[1], None
        else:
            ns, local, prefix = None, parts[0], None
        clean_attrs = {}
        for key, value in attrs.items():
            pieces = key.split(SEP)
            clean_attrs[pieces[-2] if len(pieces) == 3 else pieces[-1]] = value
        node = Node(
            qname=f"{prefix}:{local}" if prefix else local,
            name=local,
            prefix=prefix,
            ns=ns or None,
            attrs=clean_attrs,
            line=parser.CurrentLineNumber,
            parent=stack[-1] if stack else None,
        )
        if stack:
            stack[-1].children.append(node)
        elif root[0] is None:
            root[0] = node
        else:
            raise XmlError("More than one document element", node.line)
        stack.append(node)

    def end(_expanded: str) -> None:
        stack.pop()

    def chars(data: str) -> None:
        if stack:
            stack[-1].text += data

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars

    try:
        parser.Parse(source, True)
    except expat.ExpatError as error:
        raise XmlError(expat.ErrorString(error.code), error.lineno) from None

    if root[0] is None:
        raise XmlError("No document element")
    return root[0]


def kids(node: Optional[Node], name: str) -> list:
    return [c for c in node.children if c.name == name] if node else []


def kid(node: Optional[Node], name: str) -> Optional[Node]:
    found = kids(node, name)
    return found[0] if found else None


def at(node: Optional[Node], path: str) -> Optional[Node]:
    current = node
    for step in path.split("/"):
        current = kid(current, step)
        if current is None:
            return None
    return current


def text_at(node: Optional[Node], path: str) -> Optional[str]:
    found = at(node, path)
    return found.text.strip() if found is not None else None


def path_of(node: Node) -> str:
    parts: list[str] = []
    current: Optional[Node] = node
    while current is not None:
        parts.append(current.name)
        current = current.parent
    return "/".join(reversed(parts))


def walk(node: Node) -> Iterator[Node]:
    yield node
    for child in node.children:
        yield from walk(child)
