export function highlight(text, q) {
  if (!text || !q) return text;
  const hay = String(text);
  const needle = String(q).toLowerCase();
  if (!needle) return hay;
  const parts = [];
  let cursor = 0;
  const lowerHay = hay.toLowerCase();
  while (true) {
    const idx = lowerHay.indexOf(needle, cursor);
    if (idx === -1) break;
    if (idx > cursor) parts.push(hay.slice(cursor, idx));
    parts.push(<mark key={idx}>{hay.slice(idx, idx + needle.length)}</mark>);
    cursor = idx + needle.length;
  }
  if (!parts.length) return hay;
  if (cursor < hay.length) parts.push(hay.slice(cursor));
  return parts;
}