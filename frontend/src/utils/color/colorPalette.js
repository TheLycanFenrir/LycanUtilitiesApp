import { hexToRgb, rgbToHex } from "./colorMath.js";

export const DEFAULT_PALETTE = [
  { hex: "#ff0000", name: "Red" },
  { hex: "#008000", name: "Green" },
  { hex: "#0000ff", name: "Blue" },
  { hex: "#00ffff", name: "Cyan" },
  { hex: "#ff00ff", name: "Magenta" },
  { hex: "#ffff00", name: "Yellow" },
  { hex: "#000000", name: "Black" },
  { hex: "#ffffff", name: "White" },
  { hex: "#808080", name: "Gray" },
  { hex: "#ffa500", name: "Orange" },
  { hex: "#800080", name: "Purple" },
  { hex: "#a52a2a", name: "Brown" },
  { hex: "#00ff00", name: "Lime" },
  { hex: "#ffc0cb", name: "Pink" },
  { hex: "#000080", name: "Navy" },
  { hex: "#008080", name: "Teal" },
  { hex: "#808000", name: "Olive" },
  { hex: "#c46a4d", name: "Clay" },
  { hex: "#ffbf00", name: "Amber" },
  { hex: "#708090", name: "Slate" },
];

export function newPaletteId() {
  return "p_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function normalizeHex(hex) {
  const rgb = hexToRgb(hex);
  return rgb ? rgbToHex(rgb) : null;
}

function pushParsed(colors, r, g, b, name) {
  colors.push({
    hex: rgbToHex([r, g, b]),
    name: String(name || "").trim(),
  });
}

// ---------------- serialization ----------------

export function toGpl(palette) {
  const name = palette.name || "Palette";
  const colors = palette.colors || [];
  const lines = ["GIMP Palette", "Name: " + name, "Columns: 20", "#"];
  colors.forEach((c, i) => {
    if (!c || !c.hex) return;
    const rgb = hexToRgb(c.hex);
    if (!rgb) return;
    lines.push(
      String(rgb[0]).padStart(3, " ") +
        " " + String(rgb[1]).padStart(3, " ") +
        " " + String(rgb[2]).padStart(3, " ") +
        "\t" + (c.name || "Color " + (i + 1)),
    );
  });
  return lines.join("\n") + "\n";
}

function csvCell(value) {
  const s = String(value == null ? "" : value);
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

export function toCsv(palette) {
  const colors = palette.colors || [];
  const lines = ["Name,RRGGBB"];
  colors.forEach((c, i) => {
    if (!c || !c.hex) return;
    const rgb = hexToRgb(c.hex);
    if (!rgb) return;
    lines.push(csvCell(c.name || "Color " + (i + 1)) + "," + rgbToHex(rgb));
  });
  return lines.join("\n") + "\n";
}

export function toJson(palette) {
  const colors = (palette.colors || [])
    .filter((c) => c && c.hex)
    .map((c) => ({
      name: c.name || "",
      hex: rgbToHex(hexToRgb(c.hex) || [0, 0, 0]),
    }));
  return JSON.stringify({ name: palette.name || "Palette", colors }, null, 2) + "\n";
}

export function formatPalette(palette, format) {
  if (format === "json") return toJson(palette);
  if (format === "csv") return toCsv(palette);
  return toGpl(palette);
}

// ---------------- parsing ----------------

export function parseGpl(text) {
  const lines = String(text || "").split(/\r?\n/);
  let name = "";
  const colors = [];
  let started = false;
  for (const raw of lines) {
    const trimmed = raw.trim();
    if (!started) {
      if (trimmed === "#") {
        started = true;
        continue;
      }
      const named = /^Name:\s*(.*)$/.exec(trimmed);
      if (named) name = named[1].trim();
      continue;
    }
    const m = /^\s*(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})\s+(.*)$/.exec(raw) ||
      /^\s*(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})\s*$/.exec(raw);
    if (m) pushParsed(colors, Number(m[1]), Number(m[2]), Number(m[3]), m[4] || "");
  }
  return { name, colors };
}

const HEX_CELL = /^#?([0-9a-fA-F]{6})$/;

export function parseCsv(text) {
  const colors = [];
  const lines = String(text || "").split(/\r?\n/).filter((l) => l.trim().length);
  const rows = lines.map((line) =>
    line.split(",").map((c) => c.trim().replace(/^"(.*)"$/, "$1").replace(/""/g, '"')),
  );
  for (const cells of rows) {
    if (!cells || !cells.length) continue;
    const first = cells[0].trim();
    if (HEX_CELL.test(first)) {
      const hex = normalizeHex(first);
      if (hex) colors.push({ hex, name: cells.slice(1).join(" ").trim() });
      continue;
    }
    if (cells.slice(0, 3).every((c) => /^\d{1,3}$/.test(c))) {
      const n = cells.slice(0, 3).map(Number);
      pushParsed(colors, n[0], n[1], n[2], cells.slice(3).join(" "));
      continue;
    }
    const second = (cells[1] || "").trim();
    if (HEX_CELL.test(second)) {
      const hex = normalizeHex(second);
      if (hex) colors.push({ hex, name: first });
    }
  }
  return { name: "", colors };
}

export function parseJson(text) {
  let data;
  try {
    data = JSON.parse(String(text || "").trim());
  } catch {
    return { name: "", colors: [] };
  }
  const colors = [];
  let name = "";
  if (data && typeof data === "object" && !Array.isArray(data) && typeof data.name === "string") {
    name = data.name;
  }
  const list = Array.isArray(data)
    ? data
    : (data && Array.isArray(data.colors) ? data.colors : []);
  for (const item of list) {
    if (typeof item === "string") {
      const hex = normalizeHex(item);
      if (hex) colors.push({ hex, name: "" });
    } else if (item && typeof item === "object") {
      if (typeof item.hex === "string") {
        const hex = normalizeHex(item.hex);
        if (hex) colors.push({ hex, name: String(item.name || "").trim() });
      } else if ([item.r, item.g, item.b].every((v) => typeof v === "number")) {
        pushParsed(colors, item.r, item.g, item.b, item.name || "");
      }
    }
  }
  return { name, colors };
}

export function parsePaletteFile(filename, text) {
  const ext = String(filename || "").split(".").pop().toLowerCase();
  if (ext === "gpl") return parseGpl(text);
  if (ext === "json") return parseJson(text);
  return parseCsv(text);
}

// ---------------- download helper ----------------

export function downloadText(filename, text, mime) {
  const blob = new Blob([text], { type: (mime || "text/plain") + ";charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}