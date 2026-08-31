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
