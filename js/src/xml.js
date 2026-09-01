// A small, dependency-free XML reader, scoped to what certified payroll files use.
//
// It is deliberately not a general parser. It rejects DOCTYPE outright, so entity
// expansion attacks (XXE, billion laughs) have no surface, and it resolves namespaces
// well enough to tell a correctly namespaced California file from an incorrectly
// namespaced New York one — which is the distinction both validators turn on.

const PREDEFINED = { lt: '<', gt: '>', amp: '&', quot: '"', apos: "'" };

export class XmlError extends Error {
  constructor(message, line) {
    super(line ? `${message} (line ${line})` : message);
    this.name = 'XmlError';
    this.line = line ?? null;
  }
}

function decodeEntities(text, line) {
  return text.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);/g, (match, body) => {
    if (body[0] === '#') {
      const code = body[1] === 'x' || body[1] === 'X'
        ? parseInt(body.slice(2), 16)
        : parseInt(body.slice(1), 10);
      if (!Number.isFinite(code)) throw new XmlError(`Bad character reference ${match}`, line);
      return String.fromCodePoint(code);
    }
    if (body in PREDEFINED) return PREDEFINED[body];
    throw new XmlError(`Undefined entity ${match}; this reader supports only the five predefined entities`, line);
  });
}

function splitName(qname) {
  const i = qname.indexOf(':');
  return i === -1 ? { prefix: null, local: qname } : { prefix: qname.slice(0, i), local: qname.slice(i + 1) };
}

/**
 * Parse an XML document into a tree of plain objects.
 * @param {string} source
 * @returns {{root: object, declaration: string|null}}
 */
export function parseXml(source) {
  if (typeof source !== 'string') throw new XmlError('Expected an XML string');
  if (source.charCodeAt(0) === 0xfeff) source = source.slice(1);

  let i = 0;
  let line = 1;
  let declaration = null;
  const stack = [];
  let root = null;

  const lineAt = (index) => {
    let n = 1;
    for (let k = 0; k < index; k += 1) if (source.charCodeAt(k) === 10) n += 1;
    return n;
  };
  const advance = (to) => {
    for (let k = i; k < to; k += 1) if (source.charCodeAt(k) === 10) line += 1;
    i = to;
  };

  const pushText = (raw) => {
    if (!stack.length) {
      if (raw.trim()) throw new XmlError('Text outside the document element', line);
      return;
    }
    stack[stack.length - 1].text += decodeEntities(raw, line);
  };

  while (i < source.length) {
    const lt = source.indexOf('<', i);
    if (lt === -1) { pushText(source.slice(i)); break; }
    if (lt > i) pushText(source.slice(i, lt));
    advance(lt);

    if (source.startsWith('<!--', i)) {
      const end = source.indexOf('-->', i);
      if (end === -1) throw new XmlError('Unterminated comment', line);
      advance(end + 3);
      continue;
    }
    if (source.startsWith('<![CDATA[', i)) {
      const end = source.indexOf(']]>', i);
      if (end === -1) throw new XmlError('Unterminated CDATA section', line);
      if (stack.length) stack[stack.length - 1].text += source.slice(i + 9, end);
      advance(end + 3);
      continue;
    }
    if (source.startsWith('<!DOCTYPE', i) || source.startsWith('<!doctype', i)) {
      throw new XmlError('DOCTYPE declarations are refused: no agency format uses one, and accepting them would open the door to entity expansion attacks', line);
    }
    if (source.startsWith('<?', i)) {
      const end = source.indexOf('?>', i);
      if (end === -1) throw new XmlError('Unterminated processing instruction', line);
      const body = source.slice(i + 2, end);
      if (body.startsWith('xml') && declaration === null) declaration = body;
      advance(end + 2);
      continue;
    }
    if (source.startsWith('</', i)) {
      const end = source.indexOf('>', i);
      if (end === -1) throw new XmlError('Unterminated end tag', line);
      const qname = source.slice(i + 2, end).trim();
      const open = stack.pop();
      if (!open) throw new XmlError(`End tag </${qname}> with no matching start tag`, line);
      if (open.qname !== qname) throw new XmlError(`End tag </${qname}> does not match <${open.qname}>`, line);
      advance(end + 1);
      continue;
    }

    // Start tag.
    const end = (() => {
      let k = i + 1;
      let quote = null;
      while (k < source.length) {
        const c = source[k];
        if (quote) { if (c === quote) quote = null; }
        else if (c === '"' || c === "'") quote = c;
        else if (c === '>') return k;
        k += 1;
      }
      return -1;
    })();
    if (end === -1) throw new XmlError('Unterminated start tag', line);

    let body = source.slice(i + 1, end);
    const selfClosing = body.endsWith('/');
    if (selfClosing) body = body.slice(0, -1);

    const nameMatch = /^([^\s/>]+)/.exec(body);
    if (!nameMatch) throw new XmlError('Malformed start tag', line);
    const qname = nameMatch[1];
    const attrs = {};
    const attrRe = /([^\s=/]+)\s*=\s*("([^"]*)"|'([^']*)')/g;
    let m;
    while ((m = attrRe.exec(body.slice(nameMatch[0].length))) !== null) {
      // A repeated attribute is a well-formedness error, not a last-one-wins merge.
      if (Object.prototype.hasOwnProperty.call(attrs, m[1])) {
        throw new XmlError(`Duplicate attribute ${m[1]} on <${qname}>`, lineAt(i));
      }
      attrs[m[1]] = decodeEntities(m[3] !== undefined ? m[3] : m[4], line);
    }

    const parent = stack[stack.length - 1] ?? null;
    const scope = { ...(parent ? parent.nsScope : {}) };
    for (const [key, value] of Object.entries(attrs)) {
      // xmlns="" undeclares the default namespace: the element is in no namespace,
      // which is not the same as being in a namespace whose URI is the empty string.
      if (key === 'xmlns') scope[''] = value || null;
      else if (key.startsWith('xmlns:')) scope[key.slice(6)] = value || null;
    }
    const { prefix, local } = splitName(qname);
    const node = {
      qname,
      name: local,
      prefix,
      ns: (prefix ? scope[prefix] : scope['']) ?? null,
      attrs,
      children: [],
      text: '',
      line: lineAt(i),
      nsScope: scope,
      parent,
    };
    if (parent) parent.children.push(node);
    else if (root) throw new XmlError('More than one document element', node.line);
    else root = node;

    advance(end + 1);
    if (!selfClosing) stack.push(node);
  }

  if (stack.length) throw new XmlError(`Unclosed element <${stack[stack.length - 1].qname}>`, stack[stack.length - 1].line);
  if (!root) throw new XmlError('No document element');
  return { root, declaration };
}

/** Direct children with the given local name. */
export function kids(node, name) {
  return node ? node.children.filter((c) => c.name === name) : [];
}

/** First direct child with the given local name, or null. */
export function kid(node, name) {
  return node ? node.children.find((c) => c.name === name) ?? null : null;
}

/** Follow a slash-separated path of local names from a node. */
export function at(node, path) {
  let current = node;
  for (const step of path.split('/')) {
    current = kid(current, step);
    if (!current) return null;
  }
  return current;
}

/** Trimmed text of the element at `path`, or null when the element is absent. */
export function textAt(node, path) {
  const found = at(node, path);
  return found ? found.text.trim() : null;
}

/** A slash-separated path of local names from the document element to `node`. */
export function pathOf(node) {
  const parts = [];
  for (let n = node; n; n = n.parent) parts.unshift(n.name);
  return parts.join('/');
}
