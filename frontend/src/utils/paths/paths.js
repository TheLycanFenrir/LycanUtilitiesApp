function sepOf(path) {
  const p = String(path || "");
  if (p.includes("\\") && !p.includes("/")) return "\\";
  return "/";
}

function stripTrailingSep(path) {
  return String(path || "").replace(/[\\/]+$/, "");
}

function fileName(path) {
  const s = stripTrailingSep(String(path || ""));
  const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
  return i >= 0 ? s.slice(i + 1) : s;
}

function dirname(path) {
  const s = stripTrailingSep(String(path || ""));
  const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
  if (i < 0) return "";
  return s.slice(0, i);
}

function dirnameWithSep(path) {
  const d = dirname(path);
  if (!d) return "";
  return d + sepOf(path);
}

function withTrailingSep(path) {
  const s = String(path || "");
  if (!s) return "";
  return /[\\/]$/.test(s) ? s : s + sepOf(s);
}

function isFilePathLike(path) {
  const s = String(path || "");
  if (/[\\/]$/.test(s)) return false;
  const name = fileName(s);
  return name.lastIndexOf(".") > 0;
}

function stripToDir(path) {
  const s = String(path || "");
  if (!s || /[\\/]$/.test(s) || !isFilePathLike(s)) return s;
  return dirnameWithSep(s);
}

function joinPath(dir, name) {
  const d = stripTrailingSep(String(dir || ""));
  if (!d) return String(name || "");
  return d + sepOf(d) + String(name || "");
}

function stemOf(name) {
  const n = fileName(name);
  const dot = n.lastIndexOf(".");
  return dot > 0 ? n.slice(0, dot) : n;
}

export {
  sepOf, stripTrailingSep, fileName, dirname, dirnameWithSep,
  withTrailingSep, isFilePathLike, stripToDir, joinPath, stemOf,
};