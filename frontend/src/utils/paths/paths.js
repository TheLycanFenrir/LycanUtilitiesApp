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

const ASSET_BASE = "assets/icons";

// Resolve a tool card `icon_file` to a web-servable asset URL. Module
// manifests may reference shared assets via `utils/myutils/<file>`; those
// are relayed to the same icons base (the Python scanner keeps them in sync
// on cache compilation), so we just drop the prefix and join the base.
function toolIconFile(iconFile) {
  const raw = String(iconFile || "");
  const file = raw.replace(/^utils[\\/]+myutils[\\/]+/, "").replace(/[\\/]+/g, "/");
  if (!file) return "";
  return file.startsWith(ASSET_BASE) ? file : `${ASSET_BASE}/${file}`;
}

export {
  sepOf, stripTrailingSep, fileName, dirname, dirnameWithSep,
  withTrailingSep, isFilePathLike, stripToDir, joinPath, stemOf,
  ASSET_BASE, toolIconFile,
};