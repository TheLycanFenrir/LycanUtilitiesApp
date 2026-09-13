export function sanitizePath(path) {
  if (typeof path !== "string") return path;
  return path
    .replace(/\//g, "\\")
    .replace(/  +/g, " ")
    .trim();
}