import { cmykToRgb, clamp } from "./colorMath.js";

// ---------------- RGB <-> XYZ matrices (linear) ----------------

const M_SRGB = [
  [0.4124564, 0.3575761, 0.1804375],
  [0.2126729, 0.7151522, 0.0721750],
  [0.0193339, 0.1191920, 0.9503041],
];
const INV_SRGB = [
  [3.2404542, -1.5371385, -0.4985314],
  [-0.9692660, 1.8760108, 0.0415560],
  [0.0556434, -0.2040259, 1.0572252],
];

const M_ADOBE = [
  [0.5767309, 0.1855540, 0.1881852],
  [0.2973769, 0.6273491, 0.0752741],
  [0.0270343, 0.0706872, 0.9911085],
];
const INV_ADOBE = [
  [2.0413690, -0.5649464, -0.3446944],
  [-0.9692660, 1.8760108, 0.0415560],
  [0.0134474, -0.1183897, 1.0154096],
];

const M_NTSC = [
  [0.6068909, 0.1735011, 0.2003480],
  [0.2989164, 0.5865990, 0.1144845],
  [0.0000000, 0.0660957, 1.1162243],
];
const INV_NTSC = [
  [1.9099961, -0.5324542, -0.2882091],
  [-0.9846663, 1.9991710, -0.0283082],
  [0.0583056, -0.1183785, 0.8975536],
];

const M_P3 = [
  [0.48657095, 0.26566769, 0.19821729],
  [0.22897456, 0.69173852, 0.07928691],
  [0.00000000, 0.04511338, 1.04394437],
];
const INV_P3 = [
  [2.49349691, -0.93138362, -0.40271078],
  [-0.82948897, 1.76266406, 0.02362469],
  [0.03584583, -0.07617239, 0.95688452],
];

// ---------------- transfer functions ----------------

const LIN = (c) => c;

function srgbDecode(c) {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}
function srgbEncode(c) {
  return c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
}
function makePow(gammaIn, gammaOut) {
  return { decode: (c) => Math.pow(c, gammaIn), encode: (c) => Math.pow(c, gammaOut) };
}

export const RGB_PROFILES = {
  raw: { label: "RAW", m: M_SRGB, inv: INV_SRGB, decode: LIN, encode: LIN },
  linear: { label: "Linear RGB", m: M_SRGB, inv: INV_SRGB, decode: LIN, encode: LIN },
  srgb: { label: "sRGB", m: M_SRGB, inv: INV_SRGB, decode: srgbDecode, encode: srgbEncode },
  adobe: { label: "Adobe RGB", m: M_ADOBE, inv: INV_ADOBE, ...makePow(2.19921875, 1 / 2.19921875) },
  ntsc: { label: "NTSC", m: M_NTSC, inv: INV_NTSC, ...makePow(2.2, 1 / 2.2) },
  p3: { label: "DCI-P3", m: M_P3, inv: INV_P3, ...makePow(2.6, 1 / 2.6) },
};

export const PROFILE_OPTIONS = Object.entries(RGB_PROFILES).map(([value, p]) => [value, p.label]);

export function convertProfile(from, to, rgb) {
  if (from === to) return rgb;
  const a = RGB_PROFILES[from] || RGB_PROFILES.srgb;
  const b = RGB_PROFILES[to] || RGB_PROFILES.srgb;
  const lin = rgb.map((v) => a.decode(clamp(v, 0, 255) / 255));
  const xyz = [
    a.m[0][0] * lin[0] + a.m[0][1] * lin[1] + a.m[0][2] * lin[2],
    a.m[1][0] * lin[0] + a.m[1][1] * lin[1] + a.m[1][2] * lin[2],
    a.m[2][0] * lin[0] + a.m[2][1] * lin[1] + a.m[2][2] * lin[2],
  ];
  const outLin = [
    b.inv[0][0] * xyz[0] + b.inv[0][1] * xyz[1] + b.inv[0][2] * xyz[2],
    b.inv[1][0] * xyz[0] + b.inv[1][1] * xyz[1] + b.inv[1][2] * xyz[2],
    b.inv[2][0] * xyz[0] + b.inv[2][1] * xyz[1] + b.inv[2][2] * xyz[2],
  ];
  return [
    Math.round(b.encode(clamp(outLin[0], 0, 1)) * 255),
    Math.round(b.encode(clamp(outLin[1], 0, 1)) * 255),
    Math.round(b.encode(clamp(outLin[2], 0, 1)) * 255),
  ];
}

// ---------------- CMYK print emulation ----------------

export const CMYK_EMULATIONS = {
  swop: { label: "US Web Coated (SWOP) v2", tac: 300, paper: [248, 248, 245], mix: 0.08 },
  gracol: { label: "GRACoL 2006 Coated", tac: 310, paper: [252, 247, 242], mix: 0.08 },
  fogra39: { label: "FOGRA39 (Euro Coated)", tac: 320, paper: [251, 246, 241], mix: 0.08 },
  japan: { label: "Japan Color 2001", tac: 330, paper: [252, 248, 241], mix: 0.08 },
};

export const GAMUT_MODES = {
  full: { label: "Full Gamut (0-100%)" },
  print: { label: "Print Gamut (ISO Coated v2 / SWOP)" },
  limited: { label: "Limited Print Gamut (TAC 280%)" },
};

export const GAMUT_OPTIONS = Object.entries(GAMUT_MODES).map(([value, g]) => [value, g.label]);
export const EMULATION_OPTIONS = Object.entries(CMYK_EMULATIONS).map(([value, e]) => [value, e.label]);

export const GAMUT_LIMITED_TAC = 280;

export function cmykInkTotal([c, m, y, k]) {
  return c + m + y + k;
}

export function tacLimit(gamut, emuId) {
  if (gamut === "limited") return GAMUT_LIMITED_TAC;
  if (gamut === "print") return (CMYK_EMULATIONS[emuId] || CMYK_EMULATIONS.swop).tac;
  return 400;
}

export function clampCmykTac(cmyk, tac) {
  let [c, m, y, k] = cmyk.map((v) => clamp(v, 0, 100));
  const total = c + m + y + k;
  if (total > tac) {
    const over = total - tac;
    let k2 = over > k ? 0 : k - over;
    let t2 = c + m + y + k2;
    if (t2 > tac) {
      const f = tac / t2;
      c *= f;
      m *= f;
      y *= f;
      k = k2;
    } else {
      k = k2;
    }
  }
  return [c, m, y, k];
}

export function renderCmyk(cmyk, gamut, emuId) {
  const emu = CMYK_EMULATIONS[emuId] || CMYK_EMULATIONS.swop;
  const tac = gamut === "full" ? Infinity : gamut === "limited" ? GAMUT_LIMITED_TAC : emu.tac;
  const [c, m, y, k] = clampCmykTac(cmyk, tac);
  const rgb = cmykToRgb([c, m, y, k]);
  if (gamut === "full") return rgb;
  const cover = (c + m + y + k) / 400;
  const w = emu.mix * cover;
  return [
    rgb[0] + (emu.paper[0] - rgb[0]) * w,
    rgb[1] + (emu.paper[1] - rgb[1]) * w,
    rgb[2] + (emu.paper[2] - rgb[2]) * w,
  ];
}