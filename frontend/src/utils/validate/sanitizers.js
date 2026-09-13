export function sanitizeFps(value) {
  return String(value == null ? "" : value)
    .trim()
    .replace(/,/g, ".")
    .replace(/[^0-9.]/g, "")
    .replace(/(\..*)\./g, "$1");
}

export function sanitizeInt(value) {
  return String(value == null ? "" : value).trim().replace(/[^0-9]/g, "");
}

export function sanitizeFloat(value) {
  return String(value == null ? "" : value)
    .trim()
    .replace(/,/g, ".")
    .replace(/[^0-9.]/g, "")
    .replace(/(\..*)\./g, "$1");
}