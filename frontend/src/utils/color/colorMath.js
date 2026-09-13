export function clamp(v, lo, hi) {
  return Math.min(hi, Math.max(lo, v));
}

function clampInt(v) {
  return Math.round(clamp(v, 0, 255));
}

export function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim().replace(/\s/g, ""));
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function rgbToHex(rgb) {
  return "#" + rgb.map(clampInt).map((c) => c.toString(16).padStart(2, "0")).join("");
}

export function rgbToHsv(rgb) {
  const r = rgb[0] / 255;
  const g = rgb[1] / 255;
  const b = rgb[2] / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  let h = 0;
  if (d > 0) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  const s = max === 0 ? 0 : (d / max) * 100;
  return [h, s, max * 100];
}

export function hsvToRgb(hsv) {
  let h = hsv[0] % 360;
  if (h < 0) h += 360;
  const s = clamp(hsv[1], 0, 100) / 100;
  const v = clamp(hsv[2], 0, 100) / 100;
  const c = v * s;
  const hp = h / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let r = 0;
  let g = 0;
  let b = 0;
  if (hp < 1) { r = c; g = x; }
  else if (hp < 2) { r = x; g = c; }
  else if (hp < 3) { g = c; b = x; }
  else if (hp < 4) { g = x; b = c; }
  else if (hp < 5) { r = x; b = c; }
  else { r = c; b = x; }
  const m = v - c;
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255];
}

export function rgbToCmyk(rgb) {
  const r = rgb[0] / 255;
  const g = rgb[1] / 255;
  const b = rgb[2] / 255;
  const k = 1 - Math.max(r, g, b);
  if (k >= 1) return [0, 0, 0, 100];
  const denom = 1 - k;
  return [
    ((1 - r - k) / denom) * 100,
    ((1 - g - k) / denom) * 100,
    ((1 - b - k) / denom) * 100,
    k * 100,
  ];
}

export function cmykToRgb(cmyk) {
  const c = clamp(cmyk[0], 0, 100) / 100;
  const m = clamp(cmyk[1], 0, 100) / 100;
  const y = clamp(cmyk[2], 0, 100) / 100;
  const k = clamp(cmyk[3], 0, 100) / 100;
  return [(1 - c) * (1 - k) * 255, (1 - m) * (1 - k) * 255, (1 - y) * (1 - k) * 255];
}

const Xn = 0.95047;
const Yn = 1.0;
const Zn = 1.08883;
const LAB_EPS = 216 / 24389;
const LAB_KAPPA = 24389 / 27;

function labF(t) {
  return t > LAB_EPS ? Math.cbrt(t) : (LAB_KAPPA * t + 16) / 116;
}

function labFInv(t) {
  return t * t * t > LAB_EPS ? t * t * t : (116 * t - 16) / LAB_KAPPA;
}

function srgbLinear(t) {
  return t <= 0.04045 ? t / 12.92 : Math.pow((t + 0.055) / 1.055, 2.4);
}

function srgbGamma(t) {
  return t <= 0.0031308 ? 12.92 * t : 1.055 * Math.pow(t, 1 / 2.4) - 0.055;
}

export function rgbToLab(rgb) {
  const r = srgbLinear(rgb[0] / 255);
  const g = srgbLinear(rgb[1] / 255);
  const b = srgbLinear(rgb[2] / 255);
  const x = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / Xn;
  const y = (r * 0.2126729 + g * 0.7151522 + b * 0.072175) / Yn;
  const z = (r * 0.0193339 + g * 0.119192 + b * 0.9503041) / Zn;
  const fx = labF(x);
  const fy = labF(y);
  const fz = labF(z);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

export function labToRgb(lab) {
  const fy = (lab[0] + 16) / 116;
  const fx = fy + lab[1] / 500;
  const fz = fy - lab[2] / 200;
  const x = labFInv(fx) * Xn;
  const y = labFInv(fy) * Yn;
  const z = labFInv(fz) * Zn;
  const r = x * 3.2404542 + y * -1.5371385 + z * -0.4985314;
  const g = x * -0.969266 + y * 1.8760108 + z * 0.041556;
  const b = x * 0.0556434 + y * -0.2040259 + z * 1.0572252;
  return [srgbGamma(r) * 255, srgbGamma(g) * 255, srgbGamma(b) * 255];
}

export function sanitizeHexChars(text) {
  return String(text || "").replace(/[^0-9a-fA-F]/g, "").slice(0, 6);
}

export const isHexColor = (hex) => /^#[0-9a-fA-F]{6}$/.test(String(hex || ""));

export const MODE_DEFS = {
  rgb: {
    toRgb: (m) => [m[0], m[1], m[2]],
    fromRgb: (rgb) => [rgb[0], rgb[1], rgb[2]],
  },
  hsv: {
    toRgb: hsvToRgb,
    fromRgb: rgbToHsv,
  },
  lab: {
    toRgb: labToRgb,
    fromRgb: rgbToLab,
  },
  cmyk: {
    toRgb: cmykToRgb,
    fromRgb: rgbToCmyk,
  },
};