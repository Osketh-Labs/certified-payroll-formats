import test from 'node:test';
import assert from 'node:assert/strict';
import { parseXml, XmlError, kid, kids, textAt, at } from '../src/xml.js';

test('parses elements, attributes, text and predefined entities', () => {
  const { root } = parseXml('<a xmlns="urn:x"><b id="1">Jones &amp; Co</b><b/></a>');
  assert.equal(root.name, 'a');
  assert.equal(root.ns, 'urn:x');
  assert.equal(kids(root, 'b').length, 2);
  assert.equal(kid(root, 'b').attrs.id, '1');
  assert.equal(textAt(root, 'b'), 'Jones & Co');
});

test('resolves prefixed namespaces from the enclosing scope', () => {
  const { root } = parseXml('<CPR:eCPR xmlns:CPR="urn:ca"><CPR:payrollInfo/></CPR:eCPR>');
  assert.equal(root.ns, 'urn:ca');
  assert.equal(root.name, 'eCPR');
  assert.equal(kid(root, 'payrollInfo').ns, 'urn:ca');
});

test('refuses DOCTYPE rather than expanding entities', () => {
  assert.throws(() => parseXml('<!DOCTYPE a [<!ENTITY x "boom">]><a/>'), (e) => {
    assert.ok(e instanceof XmlError);
    assert.match(e.message, /DOCTYPE/);
    return true;
  });
});

test('rejects undefined entities instead of passing them through', () => {
  assert.throws(() => parseXml('<a>&nbsp;</a>'), /Undefined entity/);
});

test('reports the line of a mismatched end tag', () => {
  assert.throws(() => parseXml('<a>\n  <b>\n</a>'), (e) => {
    assert.equal(e.line, 3);
    return true;
  });
});

test('handles CDATA, comments and processing instructions', () => {
  const { root, declaration } = parseXml(
    '<?xml version="1.0"?><a><!-- note --><b><![CDATA[a < b & c]]></b><?pi go?></a>',
  );
  assert.match(declaration, /version="1.0"/);
  assert.equal(textAt(root, 'b'), 'a < b & c');
});

test('walks nested paths, including New York\'s day/day nesting', () => {
  const { root } = parseXml('<days><day><day>2026-08-02</day><h>8</h></day></days>');
  assert.equal(at(root, 'day/day').text, '2026-08-02');
  assert.equal(textAt(root, 'day/h'), '8');
});

test('rejects two document elements and unclosed elements', () => {
  assert.throws(() => parseXml('<a/><b/>'), /More than one document element/);
  assert.throws(() => parseXml('<a><b></b>'), /Unclosed element/);
});

test('xmlns="" undeclares the default namespace rather than setting an empty one', () => {
  const { root } = parseXml('<a xmlns="urn:x"><b xmlns=""><c/></b></a>');
  assert.equal(root.ns, 'urn:x');
  assert.equal(kid(root, 'b').ns, null, 'no namespace, not the empty string');
  assert.equal(kid(kid(root, 'b'), 'c').ns, null, 'and the child inherits that');
});

test('an attribute value may contain > and the tag still ends in the right place', () => {
  const { root } = parseXml('<a t="a>b"><b/></a>');
  assert.equal(root.attrs.t, 'a>b');
  assert.equal(root.children.length, 1);
});

test('an attribute value may end in a slash without looking self-closing', () => {
  const { root } = parseXml('<a href="x/"><b/></a>');
  assert.equal(root.attrs.href, 'x/');
  assert.equal(root.children.length, 1);
});

test('self-closing tags may carry whitespace and attributes', () => {
  const { root } = parseXml('<a><b x="1" /><c   /></a>');
  assert.equal(root.children.length, 2);
  assert.equal(kid(root, 'b').attrs.x, '1');
});

test('numeric character references are decoded, decimal and hexadecimal', () => {
  assert.equal(parseXml('<a>&#65;&#x42;&#x2014;</a>').root.text, 'AB—');
});

test('entities are decoded inside attribute values too', () => {
  assert.equal(parseXml('<a t="Jones &amp; Co &lt;x&gt;"/>').root.attrs.t, 'Jones & Co <x>');
});

test('a byte order mark does not become part of the document element name', () => {
  assert.equal(parseXml('﻿<a/>').root.name, 'a');
});

test('CRLF line endings do not double the line count', () => {
  const { root } = parseXml('<a>\r\n  <b/>\r\n</a>');
  assert.equal(kid(root, 'b').line, 2);
});

test('single-quoted attributes are supported, and a repeated attribute is refused', () => {
  assert.equal(parseXml("<a x='1'/>").root.attrs.x, '1');
  // XML forbids a repeated attribute; taking the last value would accept a malformed
  // document that the agency's own parser rejects.
  assert.throws(() => parseXml('<a x="1" x="2"/>'), /Duplicate attribute x/);
});

test('text outside the document element is refused, but whitespace is not', () => {
  assert.throws(() => parseXml('<a/>trailing'), /Text outside the document element/);
  assert.doesNotThrow(() => parseXml('\n  <a/>\n  '));
});

test('an empty or whitespace-only document has no document element', () => {
  assert.throws(() => parseXml(''), /No document element/);
  assert.throws(() => parseXml('   \n '), /No document element/);
  assert.throws(() => parseXml('<?xml version="1.0"?>'), /No document element/);
});

test('a comment may contain a hyphen, and a processing instruction is skipped', () => {
  const { root } = parseXml('<a><!-- a - b --><?target data?><b/></a>');
  assert.equal(root.children.length, 1);
});

test('elements may nest inside elements of the same name', () => {
  const { root } = parseXml('<a><a><a>deep</a></a></a>');
  assert.equal(root.children[0].children[0].text, 'deep');
});

test('at() and textAt() return null for a path that is not there', () => {
  const { root } = parseXml('<a><b/></a>');
  assert.equal(at(root, 'b/c'), null);
  assert.equal(textAt(root, 'nope'), null);
  assert.deepEqual(kids(root, 'nope'), []);
  assert.deepEqual(kids(null, 'b'), []);
});

test('pathOf names the route from the document element', async () => {
  const { pathOf } = await import('../src/xml.js');
  const { root } = parseXml('<a><b><c/></b></a>');
  assert.equal(pathOf(at(root, 'b/c')), 'a/b/c');
});

test('a non-string input is refused rather than coerced', () => {
  assert.throws(() => parseXml(null), /Expected an XML string/);
  assert.throws(() => parseXml(42), /Expected an XML string/);
});
