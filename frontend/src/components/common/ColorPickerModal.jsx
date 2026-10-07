import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import EmojiText from "./EmojiText.jsx";
import { MODE_DEFS, hexToRgb, rgbToHex, rgbToCmyk, sanitizeHexChars } from "../../utils/color/colorMath.js";
import {
  DEFAULT_PALETTE,
  newPaletteId,
  parsePaletteFile,
  formatPalette,
  downloadText,
} from "../../utils/color/colorPalette.js";
import {
  PROFILE_OPTIONS,
  GAMUT_OPTIONS,
  EMULATION_OPTIONS,
  convertProfile,
  renderCmyk,
  clampCmykTac,
  tacLimit,
  cmykInkTotal,
} from "../../utils/color/colorProfiles.js";
import styles from "./ColorPickerModal.module.scss";
import { Icon } from "./SvgIcon.jsx";
import ColorLibrariesModal from "./ColorLibrariesModal.jsx";

const SLOTS = 20;
const DEFAULT_RECENT_SLOTS = 25;
const DEFAULT_PALETTE_ID = "default";

const K_RECENT = "lycan.color.recents";
const K_PALETTES = "lycan.color.palettes";
const K_ACTIVE = "lycan.color.activePalette";
const K_LEGACY_BOOKMARKS = "lycan.color.bookmarks";
const K_MAX_RECENTS = "lycan.color.maxRecents";
const K_DEFAULT_FORMAT = "lycan.color.defaultFormat";

export const MODES = ["rgb", "hsv", "lab", "cmyk"];

const MODE_CHANNELS = {
  rgb: [
    { key: "R", min: 0, max: 255 },
    { key: "G", min: 0, max: 255 },
    { key: "B", min: 0, max: 255 },
  ],
  hsv: [
    { key: "H", min: 0, max: 360 },
    { key: "S", min: 0, max: 100 },
    { key: "V", min: 0, max: 100 },
  ],
  lab: [
    { key: "L", min: 0, max: 100 },
    { key: "a", min: -128, max: 127 },
    { key: "b", min: -128, max: 127 },
  ],
  cmyk: [
    { key: "C", min: 0, max: 100 },
    { key: "M", min: 0, max: 100 },
    { key: "Y", min: 0, max: 100 },
    { key: "K", min: 0, max: 100 },
  ],
};

const EXPORT_FORMATS = [
  { value: "gpl", label: ".gpl", mime: "text/plain", ext: "gpl" },
  { value: "csv", label: ".csv", mime: "text/csv", ext: "csv" },
  { value: "json", label: ".json", mime: "application/json", ext: "json" },
];

const HEX_OK = /^#[0-9a-f]{6}$/i;

function jsonRead(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function jsonWrite(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage unavailable; ignore
  }
}

// Overridable by the Settings panel via lycan.color.* keys.
function readRecentSlots() {
  try {
    const n = parseInt(localStorage.getItem(K_MAX_RECENTS) || String(DEFAULT_RECENT_SLOTS), 10);
    return Number.isFinite(n) ? Math.max(1, Math.min(200, n)) : DEFAULT_RECENT_SLOTS;
  } catch {
    return DEFAULT_RECENT_SLOTS;
  }
}

function readDefaultFormat() {
  try {
    return localStorage.getItem(K_DEFAULT_FORMAT) === "hsv" ? "hsv" : "rgb";
  } catch {
    return "rgb";
  }
}

function padRecent(arr, slots) {
  const out = [];
  for (let i = 0; i < slots; i++) {
    const c = arr[i];
    out.push(typeof c === "string" && HEX_OK.test(c) ? c : "#000000");
  }
  return out;
}

let legacyBookmarksMigrated = false;

function loadPalettes() {
  const stored = jsonRead(K_PALETTES, {});
  if (!legacyBookmarksMigrated) {
    legacyBookmarksMigrated = true;
    const legacy = jsonRead(K_LEGACY_BOOKMARKS, null);
    if (Array.isArray(legacy)) {
      try {
        localStorage.removeItem(K_LEGACY_BOOKMARKS);
      } catch {
        // ignore
      }
      const colors = legacy
        .filter((c) => typeof c === "string" && HEX_OK.test(c))
        .map((hex) => ({ hex, name: "" }));
      if (colors.length) {
        const id = newPaletteId();
        stored[id] = { id, name: "My Saved Colors", colors };
        jsonWrite(K_PALETTES, stored);
        jsonWrite(K_ACTIVE, id);
      }
    }
  }
  return stored;
}

// Which two remaining channels drive the 2D box, in ascending index order.
function boxAxes(channelCount, activeIdx) {
  const rest = [];
  for (let i = 0; i < channelCount; i++) {
    if (i !== activeIdx) rest.push(i);
  }
  return [rest[0], rest[1]];
}

function activePaletteData(id, palettes) {
  if (id === DEFAULT_PALETTE_ID) return { name: "Default Palette", colors: DEFAULT_PALETTE, custom: false };
  const p = palettes[id];
  if (p) return { name: p.name, colors: p.colors || [], custom: true };
  return { name: "Default Palette", colors: DEFAULT_PALETTE, custom: false };
}

function slugify(name) {
  return String(name || "palette").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export default function ColorPickerModal({ initial = "#000000", onCommit, onClose }) {
  const [rgb, setRgb] = useState(() => hexToRgb(initial) || [0, 0, 0]);
  const [mode, setMode] = useState(() => (readDefaultFormat() === "hsv" ? "hsv" : "rgb"));
  const [profile, setProfile] = useState("srgb");
  const [gamut, setGamut] = useState("full");
  const [emulation, setEmulation] = useState("swop");
  const [activeIdx, setActiveIdx] = useState(0);
  const [drag, setDrag] = useState(null);
  const [hexText, setHexText] = useState("");
  const [hexFocused, setHexFocused] = useState(false);
  const [numDrafts, setNumDrafts] = useState({});
  const [numFocusIdx, setNumFocusIdx] = useState(-1);

  const [recents, setRecents] = useState(() => padRecent(jsonRead(K_RECENT, []), readRecentSlots()));
  const [palettes, setPalettes] = useState(loadPalettes);
  const [activePaletteId, setActivePaletteId] = useState(() => jsonRead(K_ACTIVE, DEFAULT_PALETTE_ID));
  const [exportFormat, setExportFormat] = useState("gpl");
  const [editor, setEditor] = useState(null);      // null | { mode: 'add'|'rename', id?: string }
  const [palName, setPalName] = useState("");
  const [importError, setImportError] = useState("");
  const [libOpen, setLibOpen] = useState(false);
  const [picking, setPicking] = useState(false);

  const boxRef = useRef(null);
  const fileInputRef = useRef(null);
  const drawRafRef = useRef(null);
  const draggingRef = useRef(false);
  const lastCommittedRef = useRef(initial);

  const rgbRef = useRef(rgb);
  const recentsRef = useRef(recents);
  const palettesRef = useRef(palettes);
  const modeRef = useRef(mode);
  const profileRef = useRef(profile);
  const gamutRef = useRef(gamut);
  const emulationRef = useRef(emulation);
  const activeIdxRef = useRef(activeIdx);
  const activePaletteIdRef = useRef(activePaletteId);
  const exportFormatRef = useRef(exportFormat);
  const libOpenRef = useRef(libOpen);

  useEffect(() => { rgbRef.current = rgb; }, [rgb]);
  useEffect(() => { recentsRef.current = recents; }, [recents]);
  useEffect(() => { palettesRef.current = palettes; }, [palettes]);
  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { profileRef.current = profile; }, [profile]);
  useEffect(() => { gamutRef.current = gamut; }, [gamut]);
  useEffect(() => { emulationRef.current = emulation; }, [emulation]);
  useEffect(() => { activeIdxRef.current = activeIdx; }, [activeIdx]);
  useEffect(() => { activePaletteIdRef.current = activePaletteId; }, [activePaletteId]);
  useEffect(() => { exportFormatRef.current = exportFormat; }, [exportFormat]);
  useEffect(() => { libOpenRef.current = libOpen; }, [libOpen]);

  const modeValues = useMemo(() => MODE_DEFS[mode].fromRgb(rgb), [mode, rgb]);
  const modeValuesRef = useRef(modeValues);
  useEffect(() => { modeValuesRef.current = modeValues; }, [modeValues]);

  // Dynamic mode->RGB renderer honoring the CMYK print engine.
  // Used in callbacks (via ref) and at render time (activeRender) so neither
  // the canvas gradient nor the sliders can go stale after a render.
  const activeRender = useMemo(
    () =>
      mode === "cmyk"
        ? (tuple) => renderCmyk(tuple, gamut, emulation)
        : MODE_DEFS[mode].toRgb,
    [mode, gamut, emulation],
  );
  const activeRenderRef = useRef(activeRender);
  useEffect(() => { activeRenderRef.current = activeRender; }, [activeRender]);

  const channels = MODE_CHANNELS[mode];
  const fixedValue = modeValues[activeIdx];
  const hex = rgbToHex(rgb);

  // ---------------- box rendering (canvas, square) ----------------

  const drawBox = useCallback(() => {
    const canvas = boxRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const n = canvas.height;
    const ch = MODE_CHANNELS[modeRef.current];
    const [xIdx, yIdx] = boxAxes(ch.length, activeIdxRef.current);
    const xch = ch[xIdx];
    const ych = ch[yIdx];
    // In a constrained CMYK gamut the analytic ink coverage decides which
    // pixels are selectable: anything exceeding the TAC limit is out of gamut
    // and gets rendered as a masked (hatched) region.
    const constrained = modeRef.current === "cmyk" && gamutRef.current !== "full";
    const tac = constrained ? tacLimit(gamutRef.current, emulationRef.current) : 0;
    const img = ctx.createImageData(n, n);
    const data = img.data;
    const tuple = Array(ch.length).fill(0);
    tuple[activeIdxRef.current] = modeValuesRef.current[activeIdxRef.current];
    for (let py = 0; py < n; py++) {
      tuple[yIdx] = ych.min + (1 - py / (n - 1)) * (ych.max - ych.min);
      for (let px = 0; px < n; px++) {
        tuple[xIdx] = xch.min + (px / (n - 1)) * (xch.max - xch.min);
        const out = activeRenderRef.current(tuple);
        const o = (py * n + px) * 4;
        let r = out[0] < 0 ? 0 : out[0] > 255 ? 255 : out[0];
        let g = out[1] < 0 ? 0 : out[1] > 255 ? 255 : out[1];
        let b = out[2] < 0 ? 0 : out[2] > 255 ? 255 : out[2];
        if (constrained && cmykInkTotal(tuple) > tac) {
          const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
          const masked = lum * 0.28 + 136 * 0.72;
          r = r * 0.3 + masked * 0.7;
          g = g * 0.3 + masked * 0.7;
          b = b * 0.3 + masked * 0.7;
          if (((px + py) & 7) < 3) {
            r *= 0.8;
            g *= 0.8;
            b *= 0.8;
          }
        }
        data[o] = r;
        data[o + 1] = g;
        data[o + 2] = b;
        data[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, []);

  const scheduleDraw = useCallback(() => {
    if (drawRafRef.current) return;
    drawRafRef.current = requestAnimationFrame(() => {
      drawRafRef.current = null;
      drawBox();
    });
  }, [drawBox]);

  useEffect(() => {
    scheduleDraw();
  }, [scheduleDraw, fixedValue, mode, profile, gamut, emulation]);

  useEffect(() => () => {
    if (drawRafRef.current) {
      cancelAnimationFrame(drawRafRef.current);
      drawRafRef.current = null;
    }
  }, []);

  // ---------------- pointer handling on the 2D box ----------------

const applyBox = useCallback((clientX, clientY) => {
    const canvas = boxRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const px = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    const py = Math.min(1, Math.max(0, (clientY - rect.top) / rect.height));
    setDrag({ x: px, y: py });
    const ch = MODE_CHANNELS[modeRef.current];
    const [xIdx, yIdx] = boxAxes(ch.length, activeIdxRef.current);
    const xch = ch[xIdx];
    const ych = ch[yIdx];
    const tuple = modeValuesRef.current.slice();
    tuple[xIdx] = xch.min + px * (xch.max - xch.min);
    tuple[yIdx] = ych.min + (1 - py) * (ych.max - ych.min);
    // In a constrained CMYK gamut the pick snaps to the nearest printable
    // point: walk along the line from the click toward the lowest-ink corner
    // (x=min, y=max) until the total ink no longer exceeds the TAC limit.
    const constrained = modeRef.current === "cmyk" && gamutRef.current !== "full";
    let sx = px;
    let sy = py;
    if (constrained) {
      const tac = tacLimit(gamutRef.current, emulationRef.current);
      const make = (t) => {
        const cpx = px * (1 - t);
        const cpy = py + (1 - py) * t;
        const tpl = modeValuesRef.current.slice();
        tpl[xIdx] = xch.min + cpx * (xch.max - xch.min);
        tpl[yIdx] = ych.min + (1 - cpy) * (ych.max - ych.min);
        return tpl;
      };
      if (cmykInkTotal(make(1)) <= tac) {
        let lo = 0;
        let hi = 1;
        for (let it = 0; it < 24; it++) {
          const mid = (lo + hi) / 2;
          if (cmykInkTotal(make(mid)) <= tac) hi = mid;
          else lo = mid;
        }
        sx = px * (1 - hi);
        sy = py + (1 - py) * hi;
        setDrag({ x: sx, y: sy });
        const bound = make(hi);
        for (let i = 0; i < bound.length; i++) tuple[i] = bound[i];
      }
    }
    setRgb(activeRenderRef.current(tuple));
  }, []);

  const handleBoxDown = (e) => {
    if (e.button != null && e.button !== 0) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    draggingRef.current = true;
    applyBox(e.clientX, e.clientY);
  };

  const handleBoxMove = (e) => {
    if (draggingRef.current) applyBox(e.clientX, e.clientY);
  };

  const handleBoxUp = (e) => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // already released
    }
    setDrag(null);
    pushRecentIfChanged();
  };

  // ---------------- channel setters ----------------

  const setChannel = useCallback((idx, value) => {
    const ch = MODE_CHANNELS[modeRef.current];
    const lo = ch[idx].min;
    const hi = ch[idx].max;
    const clamped = Math.min(hi, Math.max(lo, value));
    const tuple = modeValuesRef.current.slice();
    tuple[idx] = clamped;
    setRgb(activeRenderRef.current(tuple));
  }, []);

  // ---------------- history ----------------

  const pushRecent = useCallback((hexNorm) => {
    const list = recentsRef.current;
    const slots = readRecentSlots();
    const next = [hexNorm, ...list.filter((c) => c.toLowerCase() !== hexNorm.toLowerCase())].slice(0, slots);
    const padded = padRecent(next, slots);
    setRecents(padded);
    jsonWrite(K_RECENT, padded);
    lastCommittedRef.current = hexNorm;
  }, []);

  const pushRecentIfChanged = useCallback(() => {
    const current = rgbToHex(rgbRef.current);
    if (current.toLowerCase() === lastCommittedRef.current.toLowerCase()) return;
    pushRecent(current);
  }, [pushRecent]);

  const selectSwatch = useCallback((hexColor) => {
    setRgb(hexToRgb(hexColor) || [0, 0, 0]);
    pushRecent(hexColor);
    setDrag(null);
  }, [pushRecent]);

  // ---------------- unified palette manager ----------------

  const setPalettesPersist = useCallback((next) => {
    setPalettes(next);
    jsonWrite(K_PALETTES, next);
  }, []);

  const setActivePersist = useCallback((id) => {
    setActivePaletteId(id);
    jsonWrite(K_ACTIVE, id);
  }, []);

  const addSwatch = useCallback(() => {
    const id = activePaletteIdRef.current;
    if (id === DEFAULT_PALETTE_ID) return;
    const cur = palettesRef.current[id];
    if (!cur) return;
    const nextHex = rgbToHex(rgbRef.current).toLowerCase();
    const colors = cur.colors.filter(
      (c) => !c || String(c.hex).toLowerCase() !== nextHex,
    );
    colors.push({ hex: nextHex, name: "" });
    setPalettesPersist({
      ...palettesRef.current,
      [id]: { ...cur, colors },
    });
  }, [setPalettesPersist]);

  const removeSwatch = useCallback((palId, idx) => {
    const cur = palettesRef.current[palId];
    if (!cur) return;
    const colors = cur.colors.filter((_, i) => i !== idx);
    setPalettesPersist({
      ...palettesRef.current,
      [palId]: { ...cur, colors },
    });
  }, [setPalettesPersist]);

  const addPalette = useCallback((name) => {
    const id = newPaletteId();
    const palette = { id, name: name || "New Palette", colors: [] };
    setPalettesPersist({ ...palettesRef.current, [id]: palette });
    setActivePersist(id);
  }, [setPalettesPersist, setActivePersist]);

  const renamePalette = useCallback((id, name) => {
    const cur = palettesRef.current[id];
    if (!cur || !String(name || "").trim()) return;
    setPalettesPersist({
      ...palettesRef.current,
      [id]: { ...cur, name: name.trim() },
    });
  }, [setPalettesPersist]);

  const deletePalette = useCallback((id) => {
    if (!window.confirm("Delete this palette?")) return;
    const next = { ...palettesRef.current };
    delete next[id];
    setPalettesPersist(next);
    setActivePersist(DEFAULT_PALETTE_ID);
  }, [setPalettesPersist, setActivePersist]);

  const selectPalette = useCallback((id) => {
    if (id === activePaletteIdRef.current) return;
    setActivePersist(id);
  }, [setActivePersist]);

  const handleImportFile = useCallback((e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const parsed = parsePaletteFile(file.name, String(reader.result || ""));
      const colors = parsed.colors || [];
      if (!colors.length) {
        setImportError("No colors found in \"'" + file.name + "'\".");
        return;
      }
      let name = String(parsed.name || "").trim() ||
        String(file.name.replace(/\.[^.]+$/, "")).trim() ||
        "Imported Palette";
      const clash = Object.values(palettesRef.current).some(
        (p) => String(p.name).toLowerCase() === name.toLowerCase(),
      );
      if (clash) name = name + " (imported)";
      const id = newPaletteId();
      setPalettesPersist({ ...palettesRef.current, [id]: { id, name, colors } });
      setActivePersist(id);
      setImportError("");
    };
    reader.onerror = () => setImportError("Failed to read the file.");
    reader.readAsText(file);
  }, [setPalettesPersist, setActivePersist]);

  const exportActivePalette = useCallback(() => {
    const info = activePaletteData(activePaletteIdRef.current, palettesRef.current);
    const fmt = EXPORT_FORMATS.find((f) => f.value === exportFormatRef.current) || EXPORT_FORMATS[0];
    const text = formatPalette(info, fmt.value);
    downloadText(slugify(info.name) + "." + fmt.ext, text, fmt.mime);
  }, []);

  const confirmEditor = useCallback(() => {
    const name = palNameRef.current.trim();
    if (!name) {
      setEditor(null);
      setPalName("");
      return;
    }
    if (editorRef.current.mode === "add") {
      addPalette(name);
    } else {
      renamePalette(editorRef.current.id, name);
    }
    setEditor(null);
    setPalName("");
  }, [addPalette, renamePalette]);
  const palNameRef = useRef(palName);
  useEffect(() => { palNameRef.current = palName; }, [palName]);
  const editorRef = useRef(editor);
  useEffect(() => { editorRef.current = editor; }, [editor]);

  // ---------------- mode switching ----------------

  const switchMode = useCallback((nextMode) => {
    setMode(nextMode);
    setActiveIdx(0);
    setDrag(null);
    setNumFocusIdx(-1);
    setNumDrafts({});
  }, []);

  // ---------------- color-space profile / gamut / emulation ----------------

  const switchProfile = useCallback((next) => {
    if (next === profileRef.current) return;
    const prev = profileRef.current;
    setProfile(next);
    setRgb(convertProfile(prev, next, rgbRef.current));
    setDrag(null);
  }, []);

  const applyGamut = useCallback((next) => {
    setGamut(next);
    if (next === "full") return;
    const t = tacLimit(next, emulationRef.current);
    const cur = rgbToCmyk(rgbRef.current);
    if (cmykInkTotal(cur) > t) {
      const clamped = clampCmykTac(cur, t);
      setRgb(renderCmyk(clamped, next, emulationRef.current));
    }
  }, []);

  const switchGamut = useCallback((next) => {
    if (next === gamutRef.current) return;
    applyGamut(next);
  }, [applyGamut]);

  const switchEmulation = useCallback((next) => {
    if (next === emulationRef.current) return;
    setEmulation(next);
  }, []);

  // ---------------- gamut warnings ----------------

  const inkWarning = useMemo(() => {
    if (mode !== "cmyk" || gamut === "full") return null;
    const total = cmykInkTotal(rgbToCmyk(rgb));
    const limit = tacLimit(gamut, emulation);
    if (total <= limit) return null;
    return Math.round(limit);
  }, [mode, gamut, emulation, rgb]);

  // ---------------- hex field ----------------

  const handleHexChange = (e) => {
    const clean = sanitizeHexChars(e.target.value);
    setHexText(clean);
    if (clean.length === 6) {
      const parsed = hexToRgb("#" + clean);
      if (parsed) setRgb(parsed);
    }
  };

  const handleHexFocus = () => {
    setHexText(rgbToHex(rgbRef.current));
    setHexFocused(true);
  };

  // ---------------- cursor position on the box ----------------

  const cursor = useMemo(() => {
    if (drag) return drag;
    const ch = MODE_CHANNELS[mode];
    const [xIdx, yIdx] = boxAxes(ch.length, activeIdx);
    const vx = modeValues[xIdx];
    const vy = modeValues[yIdx];
    const x = (vx - ch[xIdx].min) / (ch[xIdx].max - ch[xIdx].min);
    const y = (ch[yIdx].max - vy) / (ch[yIdx].max - ch[yIdx].min);
    return {
      x: Math.min(1, Math.max(0, x)),
      y: Math.min(1, Math.max(0, y)),
    };
  }, [mode, activeIdx, modeValues, drag]);

  // ---------------- slider gradients ----------------

  const channelGradient = (i) => {
    const ch = MODE_CHANNELS[mode];
    const chan = ch[i];
    const steps = 13;
    const stops = [];
    for (let s = 0; s < steps; s++) {
      const v = chan.min + (chan.max - chan.min) * (s / (steps - 1));
      const tuple = modeValues.slice();
      tuple[i] = v;
      const out = activeRender(tuple);
      const c = (x) => Math.round(Math.min(255, Math.max(0, x)));
      stops.push("rgb(" + c(out[0]) + "," + c(out[1]) + "," + c(out[2]) + ") " + Math.round((s / (steps - 1)) * 100) + "%");
    }
    return "linear-gradient(to right, " + stops.join(", ") + ")";
  };

  // ---------------- palette display ----------------

  const paletteData = useMemo(
    () => activePaletteData(activePaletteId, palettes),
    [activePaletteId, palettes],
  );

  const paletteCells = useMemo(() => {
    const out = paletteData.colors.map((color, idx) => ({ color, idx }));
    for (let i = out.length; i < SLOTS; i++) out.push(null);
    return out;
  }, [paletteData]);

  const customPalettes = useMemo(
    () => Object.values(palettes).sort((a, b) => String(a.name).localeCompare(String(b.name))),
    [palettes],
  );

  // ---------------- actions ----------------

  const close = useCallback(() => {
    draggingRef.current = false;
    if (onClose) onClose();
  }, [onClose]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape" && !libOpenRef.current) close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const handleApply = () => {
    const finalHex = rgbToHex(rgbRef.current);
    pushRecent(finalHex);
    if (onCommit) onCommit(finalHex);
  };

  // ---------------- OS-level screen color picking ----------------
  // The desktop build reads the exact pixel under the cursor on the next left
  // click anywhere on screen (the window is never hidden, so the app never
  // appears to close). Falls back to the browser's in-window EyeDropper only
  // when the native bridge is unavailable.

  // The native pick resolves while the very same click that ended it is still
  // being delivered to the browser. Keep the input shield mounted for a short
  // grace period so that click (and any trailing events) land on the shield
  // and can never reach the UI underneath, then restore normal interaction.
  const graceTimerRef = useRef(null);
  const endPickLater = useCallback(() => {
    if (graceTimerRef.current) clearTimeout(graceTimerRef.current);
    graceTimerRef.current = setTimeout(() => setPicking(false), 400);
  }, []);
  useEffect(() => () => {
    if (graceTimerRef.current) clearTimeout(graceTimerRef.current);
  }, []);

  const pickScreenColor = useCallback(async () => {
    const api = window.pywebview && window.pywebview.api;
    const hasNative = !!(api && typeof api.screen_pick === "function");
    const usingFallback = !hasNative;
    if (hasNative) {
      setPicking(true);
      let res = null;
      try {
        res = await api.screen_pick(8);
      } catch (err) {
        console.error("[ColorPickerModal] screen_pick failed:", err);
        res = null;
      }
      const picked = res && res.ok && typeof res.hex === "string" && HEX_OK.test(res.hex)
        ? res.hex.toLowerCase()
        : null;
      if (picked) {
        setRgb(hexToRgb(picked) || [0, 0, 0]);
        pushRecent(picked);
        setDrag(null);
      }
      endPickLater();
      return;
    }
    // No native bridge (plain browser preview): fall back to the browser's
    // in-window eye dropper. In the desktop build it only samples the page
    // itself, so it is never used there.
    if (usingFallback && typeof window.EyeDropper !== "undefined") {
      try {
        const result = await new window.EyeDropper().open();
        const hexPicked = result && typeof result.sRGBHex === "string" && HEX_OK.test(result.sRGBHex)
          ? result.sRGBHex.toLowerCase()
          : null;
        if (hexPicked) {
          setRgb(hexToRgb(hexPicked) || [0, 0, 0]);
          pushRecent(hexPicked);
          setDrag(null);
        }
      } catch {
        // picker dismissed by the user
      }
    }
  }, [pushRecent]);

  // While a pick is in progress, swallow EVERY mouse/pointer/touch/key event in
  // the capture phase so no part of the UI can react — not even fixed chrome
  // that stacks above this modal. Esc / clicks are handled by the native hook.
  useEffect(() => {
    if (!picking) return;
    const noop = (e) => {
      e.preventDefault();
      e.stopPropagation();
    };
    const events = [
      "keydown",
      "mousedown",
      "mouseup",
      "click",
      "dblclick",
      "contextmenu",
      "wheel",
      "pointerdown",
      "pointerup",
      "pointermove",
      "touchstart",
      "touchmove",
      "touchend",
      "dragstart",
      "drop",
    ];
    for (const ev of events) window.addEventListener(ev, noop, true);
    return () => {
      for (const ev of events) window.removeEventListener(ev, noop, true);
    };
  }, [picking]);

  const channelDisplay = (i, raw) =>
    numFocusIdx === i ? (numDrafts[i] !== undefined ? numDrafts[i] : "") : String(Math.round(raw));

  return (
    <div className="modal-overlay" onClick={close}>
      <div
        className={"modal " + styles.picker}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.pickerHead}>
          <span className={styles.pickerTitle}>Advanced Color Picker</span>
          <button type="button" className="modal-close" aria-label="Close" onClick={close}>
            <Icon name="x" />
          </button>
        </div>

        <div className={styles.stage}>
          {/* left: sticky square canvas */}
          <div className={styles.boxCol}>
            <div className={styles.boxFrame}>
              <canvas
                ref={boxRef}
                className={styles.box}
                width="256"
                height="256"
                onPointerDown={handleBoxDown}
                onPointerMove={handleBoxMove}
                onPointerUp={handleBoxUp}
              />
              <span className={styles.cursor} style={{ left: cursor.x * 100 + "%", top: cursor.y * 100 + "%" }} />
            </div>
            {mode === "cmyk" && gamut !== "full" && (
              <div className={styles.boxLegend}>
                Hatched zones are <strong>out of print gamut</strong> — picking there selects the nearest
                printable color (ink clamped to {tacLimit(gamut, emulation)}%).
              </div>
            )}
          </div>

          {/* right: independently scrollable controls */}
          <div className={styles.side}>
            <div className={styles.modeTabs}>
              {MODES.map((m) => (
                <button
                  key={m}
                  type="button"
                  className={styles.modeTab + (mode === m ? " " + styles.modeTabActive : "")}
                  onClick={() => switchMode(m)}
                >
                  {m.toUpperCase()}
                </button>
              ))}
            </div>

            <div className={styles.profileBar}>
              {mode === "cmyk" ? (
                <>
                  <select
                    className={styles.profileSelect}
                    value={gamut}
                    onChange={(e) => switchGamut(e.target.value)}
                    aria-label="Color gamut"
                    title="Color gamut / ink coverage"
                  >
                    {GAMUT_OPTIONS.map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  <select
                    className={styles.profileSelect}
                    value={emulation}
                    onChange={(e) => switchEmulation(e.target.value)}
                    disabled={gamut === "full"}
                    aria-label="CMYK emulation profile"
                    title="Print emulation profile"
                  >
                    {EMULATION_OPTIONS.map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </>
              ) : (
                <select
                  className={styles.profileSelect}
                  value={profile}
                  onChange={(e) => switchProfile(e.target.value)}
                  aria-label="RGB color profile"
                  title="Working color profile"
                >
                  {PROFILE_OPTIONS.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              )}
            </div>

            {inkWarning != null && (
              <div className={styles.gamutWarn}>
                Out of print gamut — total ink exceeds {inkWarning}%
              </div>
            )}

            <div className={styles.channels}>
              {channels.map((ch, i) => (
                <div
                  key={ch.key}
                  className={styles.channel + (i === activeIdx ? " " + styles.channelActive : "")}
                >
                  <label className={styles.channelRadioLbl} title={"Set " + ch.key + " as active channel"}>
                    <input
                      type="radio"
                      name="cp-chan"
                      className={styles.channelRadio}
                      checked={i === activeIdx}
                      onChange={() => {
                        setActiveIdx(i);
                        setDrag(null);
                        setNumFocusIdx(-1);
                      }}
                    />
                    <span className={styles.channelKey}>{ch.key}</span>
                  </label>
                  <input
                    type="range"
                    className={styles.channelRange}
                    min={ch.min}
                    max={ch.max}
                    step="1"
                    value={Math.round(modeValues[i])}
                    onChange={(e) => setChannel(i, Number(e.target.value))}
                    onPointerUp={pushRecentIfChanged}
                    style={{ background: channelGradient(i) }}
                    aria-label={"Channel " + ch.key}
                  />
                  <input
                    type="number"
                    className={styles.channelNum}
                    value={channelDisplay(i, modeValues[i])}
                    min={ch.min}
                    max={ch.max}
                    step="1"
                    onChange={(e) => {
                      setNumDrafts((d) => ({ ...d, [i]: e.target.value }));
                      const v = parseFloat(e.target.value);
                      if (Number.isFinite(v)) setChannel(i, v);
                    }}
                    onFocus={(e) => {
                      setNumFocusIdx(i);
                      setNumDrafts((d) => ({ ...d, [i]: String(Math.round(modeValues[i])) }));
                      e.target.select();
                    }}
                    onBlur={() => {
                      setNumFocusIdx(-1);
                      setNumDrafts((d) => {
                        const next = { ...d };
                        delete next[i];
                        return next;
                      });
                    }}
                  />
                </div>
              ))}
            </div>

            <div className={styles.hexRow}>
              <label className={styles.hex}>
                <span>HEX</span>
                <input
                  type="text"
                  spellCheck="false"
                  value={hexFocused ? hexText : hex}
                  onChange={handleHexChange}
                  onFocus={handleHexFocus}
                  onBlur={() => setHexFocused(false)}
                  placeholder="RRGGBB"
                />
              </label>
              <div className={styles.preview}>
                <div className={styles.previewCell}>
                  <span className={styles.swatchOld} style={{ background: initial }} />
                  <span className={styles.caption}>Current</span>
                </div>
                <div className={styles.previewCell}>
                  <span className={styles.swatchNew} style={{ background: hex }} />
                  <span className={styles.caption}>New</span>
                </div>
              </div>
            </div>

            <div className={styles.section}>
              <div className={styles.sectionHead}>
                <span className={styles.sectionLabel}>Recent</span>
                <span className={styles.sectionMeta}>last {readRecentSlots()} · FIFO · solid black = empty</span>
              </div>
              <div className={styles.recentRow}>
                {recents.map((c, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className={styles.slot}
                    style={{ background: c }}
                    title={c}
                    onClick={() => selectSwatch(c)}
                  />
                ))}
              </div>
            </div>

            <div className={styles.section}>
              <div className={styles.toolbar}>
                <select
                  className={styles.paletteSelect}
                  value={activePaletteId}
                  onChange={(e) => selectPalette(e.target.value)}
                  aria-label="Active palette"
                >
                  <option value={DEFAULT_PALETTE_ID}>Default Palette</option>
                  {customPalettes.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
                {paletteData.custom && (
                  <>
                    <button
                      type="button"
                      className={styles.iconBtn}
                      title="Rename palette"
                      onClick={() => {
                        setEditor({ mode: "rename", id: activePaletteId });
                        setPalName(paletteData.name);
                      }}
                    >
                      ✎
                    </button>
                    <button
                      type="button"
                      className={styles.iconBtn}
                      title="Delete palette"
                      onClick={() => deletePalette(activePaletteId)}
                    >
                      <EmojiText text="🗑" />
                    </button>
                  </>
                )}
                <span className={styles.spacer} />
                <select
                  className={styles.exportSelect}
                  value={exportFormat}
                  onChange={(e) => setExportFormat(e.target.value)}
                  aria-label="Export format"
                >
                  {EXPORT_FORMATS.map((f) => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </select>
                <button type="button" className={"btn " + styles.toolBtn} onClick={exportActivePalette}>Export</button>
                <button type="button" className={"btn " + styles.toolBtn} onClick={() => fileInputRef.current.click()}>Import</button>
                <button
                  type="button"
                  className={"btn " + styles.toolBtn + " " + styles.accent}
                  onClick={() => {
                    setEditor({ mode: "add" });
                    setPalName("");
                  }}
                >
                  + Palette
                </button>
              </div>

              {editor && (
                <div className={styles.editorRow}>
                  <input
                    type="text"
                    className={styles.editorInput}
                    value={palName}
                    onChange={(e) => setPalName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") confirmEditor();
                      if (e.key === "Escape") {
                        setEditor(null);
                        setPalName("");
                      }
                    }}
                    placeholder={editor.mode === "add" ? "Palette name" : "New palette name"}
                    autoFocus
                  />
                  <button type="button" className={"btn " + styles.toolBtn + " " + styles.accent} onClick={confirmEditor}>
                    {editor.mode === "add" ? "Create" : "Save"}
                  </button>
                  <button
                    type="button"
                    className={"btn " + styles.toolBtn}
                    onClick={() => {
                      setEditor(null);
                      setPalName("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              )}

              {importError && <div className={styles.error}>{importError}</div>}

              <div className={styles.swatchGrid}>
                <button
                  type="button"
                  className={styles.addTile}
                  title={paletteData.custom ? "Add current color" : "Read-only palette — create a custom palette first"}
                  disabled={!paletteData.custom}
                  onClick={addSwatch}
                >
                  +
                </button>
                {paletteCells.map((cell, idx) =>
                  cell ? (
                    <span key={idx} className={styles.slotWrap}>
                      <button
                        type="button"
                        className={styles.slot}
                        style={{ background: cell.color.hex }}
                        title={cell.color.name || cell.color.hex}
                        onClick={() => selectSwatch(cell.color.hex)}
                      />
                      {paletteData.custom && (
                        <button
                          type="button"
                          className={styles.slotX}
                          title="Remove color"
                          onClick={() => removeSwatch(activePaletteId, cell.idx)}
                        >
                          x
                        </button>
                      )}
                    </span>
                  ) : (
                    <span key={idx} className={styles.emptyCell} />
                  ),
                )}
              </div>
            </div>
          </div>
        </div>

        {picking && (
          <div className={styles.pickHint}>
            Left-click anywhere on the screen to pick a color — right-click or press Esc to cancel.
          </div>
        )}

        <div className={styles.actions}>
          <span className={styles.grow} />
          <button
            type="button"
            className="btn"
            title="Pick a color from anywhere on the screen"
            onClick={pickScreenColor}
            disabled={picking}
          >
            <Icon name="eyedropper" />
            Color pick
          </button>
          <button type="button" className="btn" onClick={() => setLibOpen(true)}>Color Libraries</button>
          <button type="button" className="btn" onClick={close}>Cancel</button>
          <button type="button" className="btn accent" onClick={handleApply}>Apply</button>
        </div>

        {picking &&
          createPortal(
            <div
              className={styles.pickBlock}
              style={{
                position: "fixed",
                inset: 0,
                zIndex: 2147483647,
                cursor: "crosshair",
              }}
              title="Left-click to pick — right-click or Esc to cancel"
            />,
            document.body,
          )}

        <input
          ref={fileInputRef}
          type="file"
          accept=".gpl,.csv,.json"
          className="hidden"
          onChange={handleImportFile}
        />
      </div>
      {libOpen && (
        <ColorLibrariesModal
          initial={hex}
          onCommit={(h) => {
            setRgb(hexToRgb(h) || [0, 0, 0]);
            setLibOpen(false);
          }}
          onCancel={() => setLibOpen(false)}
          onPicker={() => {
            setLibOpen(false);
            setHexFocused(false);
          }}
        />
      )}
    </div>
  );
}