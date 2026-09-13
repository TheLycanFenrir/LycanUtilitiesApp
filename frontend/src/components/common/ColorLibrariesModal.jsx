import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { hexToRgb, rgbToCmyk } from "../../utils/color/colorMath.js";
import { DEFAULT_PALETTE } from "../../utils/color/colorPalette.js";
import { Icon } from "./SvgIcon.jsx";
import styles from "./ColorLibrariesModal.module.scss";

const ROW = 30;
const WARN_TAC = 300;

const WEB_COLORS = Object.entries({
  "Alice Blue": "f0f8ff",
  "Antique White": "faebd7",
  Aqua: "00ffff",
  Aquamarine: "7fffd4",
  Azure: "f0ffff",
  Beige: "f5f5dc",
  Bisque: "ffe4c4",
  Black: "000000",
  "Blanched Almond": "ffebcd",
  Blue: "0000ff",
  "Blue Violet": "8a2be2",
  Brown: "a52a2a",
  "Burly Wood": "deb887",
  "Cadet Blue": "5f9ea0",
  Chartreuse: "7fff00",
  Chocolate: "d2691e",
  Coral: "ff7f50",
  "Cornflower Blue": "6495ed",
  Cornsilk: "fff8dc",
  Crimson: "dc143c",
  Cyan: "00ffff",
  "Dark Blue": "00008b",
  "Dark Cyan": "008b8b",
  "Dark Goldenrod": "b8860b",
  "Dark Gray": "a9a9a9",
  "Dark Green": "006400",
  "Dark Grey": "a9a9a9",
  "Dark Khaki": "bdb76b",
  "Dark Magenta": "8b008b",
  "Dark Olive Green": "556b2f",
  "Dark Orange": "ff8c00",
  "Dark Orchid": "9932cc",
  "Dark Red": "8b0000",
  "Dark Salmon": "e9967a",
  "Dark Sea Green": "8fbc8f",
  "Dark Slate Blue": "483d8b",
  "Dark Slate Gray": "2f4f4f",
  "Dark Slate Grey": "2f4f4f",
  "Dark Turquoise": "00ced1",
  "Dark Violet": "9400d3",
  "Deep Pink": "ff1493",
  "Deep Sky Blue": "00bfff",
  "Dim Gray": "696969",
  "Dim Grey": "696969",
  "Dodger Blue": "1e90ff",
  Firebrick: "b22222",
  "Floral White": "fffaf0",
  "Forest Green": "228b22",
  Fuchsia: "ff00ff",
  Gainsboro: "dcdcdc",
  "Ghost White": "f8f8ff",
  Gold: "ffd700",
  Goldenrod: "daa520",
  Gray: "808080",
  Green: "008000",
  "Green Yellow": "adff2f",
  Grey: "808080",
  Honeydew: "f0fff0",
  "Hot Pink": "ff69b4",
  "Indian Red": "cd5c5c",
  Indigo: "4b0082",
  Ivory: "fffff0",
  Khaki: "f0e68c",
  Lavender: "e6e6fa",
  "Lavender Blush": "fff0f5",
  "Lawn Green": "7cfc00",
  "Lemon Chiffon": "fffacd",
  "Light Blue": "add8e6",
  "Light Coral": "f08080",
  "Light Cyan": "e0ffff",
  "Light Goldenrod Yellow": "fafad2",
  "Light Gray": "d3d3d3",
  "Light Green": "90ee90",
  "Light Grey": "d3d3d3",
  "Light Pink": "ffb6c1",
  "Light Salmon": "ffa07a",
  "Light Sea Green": "20b2aa",
  "Light Sky Blue": "87cefa",
  "Light Slate Gray": "778899",
  "Light Slate Grey": "778899",
  "Light Steel Blue": "b0c4de",
  "Light Yellow": "ffffe0",
  Lime: "00ff00",
  "Lime Green": "32cd32",
  Linen: "faf0e6",
  Magenta: "ff00ff",
  Maroon: "800000",
  "Medium Aquamarine": "66cdaa",
  "Medium Blue": "0000cd",
  "Medium Orchid": "ba55d3",
  "Medium Purple": "9370db",
  "Medium Sea Green": "3cb371",
  "Medium Slate Blue": "7b68ee",
  "Medium Spring Green": "00fa9a",
  "Medium Turquoise": "48d1cc",
  "Medium Violet Red": "c71585",
  "Midnight Blue": "191970",
  "Mint Cream": "f5fffa",
  "Misty Rose": "ffe4e1",
  Moccasin: "ffe4b5",
  "Navajo White": "ffdead",
  Navy: "000080",
  "Old Lace": "fdf5e6",
  Olive: "808000",
  "Olive Drab": "6b8e23",
  Orange: "ffa500",
  "Orange Red": "ff4500",
  Orchid: "da70d6",
  "Pale Goldenrod": "eee8aa",
  "Pale Green": "98fb98",
  "Pale Turquoise": "afeeee",
  "Pale Violet Red": "db7093",
  "Papaya Whip": "ffefd5",
  "Peach Puff": "ffdab9",
  Peru: "cd853f",
  Pink: "ffc0cb",
  Plum: "dda0dd",
  "Powder Blue": "b0e0e6",
  Purple: "800080",
  "Rebecca Purple": "663399",
  Red: "ff0000",
  "Rosy Brown": "bc8f8f",
  "Royal Blue": "4169e1",
  "Saddle Brown": "8b4513",
  Salmon: "fa8072",
  "Sandy Brown": "f4a460",
  "Sea Green": "2e8b57",
  "Sea Shell": "fff5ee",
  Sienna: "a0522d",
  Silver: "c0c0c0",
  "Sky Blue": "87ceeb",
  "Slate Blue": "6a5acd",
  "Slate Gray": "708090",
  "Slate Grey": "708090",
  Snow: "fffafa",
  "Spring Green": "00ff7f",
  "Steel Blue": "4682b4",
  Tan: "d2b48c",
  Teal: "008080",
  Thistle: "d8bfd8",
  Tomato: "ff6347",
  Turquoise: "40e0d0",
  Violet: "ee82ee",
  Wheat: "f5deb3",
  White: "ffffff",
  "White Smoke": "f5f5f5",
  Yellow: "ffff00",
  "Yellow Green": "9acd32",
}).map(([name, hex]) => ({ name, hex: "#" + hex }));

const BOOKS = [
  { id: "system", label: "Default System Palette" },
  { id: "web", label: "HTML / Web Colors" },
];

function fgStyle(hex) {
  const [r, g, b] = hexToRgb(hex) || [0, 0, 0];
  const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  if (lum > 0.6) {
    return { color: "#111111", textShadow: "0 1px 0 rgba(255,255,255,.5)" };
  }
  return { color: "#f4f6f8", textShadow: "0 1px 2px rgba(0,0,0,.65)" };
}

export default function ColorLibrariesModal({
  initial = "#000000",
  onCommit,
  onCancel = () => {},
  onPicker = () => {},
}) {
  const initialHex = String(initial || "").toLowerCase();

  const [bookId, setBookId] = useState("web");
  const items = useMemo(() => (bookId === "system" ? DEFAULT_PALETTE : WEB_COLORS), [bookId]);

  const [selectedIdx, setSelectedIdx] = useState(() => {
    const i = WEB_COLORS.findIndex((c) => c.hex.toLowerCase() === initialHex);
    return i >= 0 ? i : 0;
  });
  const [scrollTop, setScrollTop] = useState(0);
  const [viewH, setViewH] = useState(300);
  const [query, setQuery] = useState("");
  const [noMatch, setNoMatch] = useState(false);

  const listRef = useRef(null);
  const trackRef = useRef(null);
  const spectRef = useRef(null);
  const itemsRef = useRef(items);
  const draggingRef = useRef(false);

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  useLayoutEffect(() => {
    const k = initialHex;
    const i = items.findIndex((c) => c.hex.toLowerCase() === k);
    setSelectedIdx(i >= 0 ? i : 0);
    if (listRef.current) {
      listRef.current.scrollTop = 0;
      setScrollTop(0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId]);

  const selected = items[selectedIdx] || items[0] || { name: "", hex: "#000000" };

  const scrollToIndex = useCallback((idx) => {
    const el = listRef.current;
    if (!el) return;
    const n = itemsRef.current.length;
    if (n <= 0) return;
    const total = n * ROW - el.clientHeight;
    const top = Math.max(0, Math.min(idx * ROW - 8, total));
    el.scrollTop = top;
    setScrollTop(top);
  }, []);

  const selectAndScroll = useCallback((idx) => {
    const n = itemsRef.current.length;
    if (n <= 0) return;
    const i = Math.max(0, Math.min(n - 1, idx));
    setSelectedIdx(i);
    scrollToIndex(i);
  }, [scrollToIndex]);

  useLayoutEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const syncHeight = () => {
      const h = el.clientHeight;
      if (h > 0) setViewH((prev) => (prev === h ? prev : h));
    };
    const ro = new ResizeObserver(syncHeight);
    ro.observe(el);
    syncHeight();
    return () => ro.disconnect();
  }, [bookId]);

  const drawSpectrum = useCallback(() => {
    const cv = spectRef.current;
    const el = trackRef.current;
    if (!cv || !el) return;
    const dpr = window.devicePixelRatio || 1;
    const w = el.clientWidth;
    const h = el.clientHeight;
    if (w <= 0 || h <= 0) return;
    cv.width = Math.max(1, Math.round(w * dpr));
    cv.height = Math.max(1, Math.round(h * dpr));
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, cv.width, cv.height);
    const n = itemsRef.current.length;
    if (n <= 0) return;
    const band = 4;
    for (let py = 0; py < cv.height; py += band) {
      const f = py / cv.height;
      const idx = Math.min(n - 1, Math.max(0, Math.round(f * (n - 1))));
      const item = itemsRef.current[idx];
      if (!item) continue;
      const [r, g, b] = hexToRgb(item.hex) || [0, 0, 0];
      ctx.fillStyle = "rgb(" + r + "," + g + "," + b + ")";
      ctx.fillRect(0, py, cv.width, band + 1);
    }
  }, []);

  useEffect(() => {
    drawSpectrum();
  }, [drawSpectrum, bookId, viewH]);

  const seek = useCallback((clientY) => {
    const el = trackRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const n = itemsRef.current.length;
    if (n <= 0) return;
    const f = Math.min(1, Math.max(0, (clientY - r.top) / r.height));
    const idx = Math.max(0, Math.min(n - 1, Math.round(f * (n - 1))));
    setSelectedIdx(idx);
    scrollToIndex(idx);
  }, [scrollToIndex]);

  const onTrackDown = (e) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    draggingRef.current = true;
    seek(e.clientY);
  };

  const onTrackMove = (e) => {
    if (!draggingRef.current) return;
    seek(e.clientY);
  };

  const onTrackUp = (e) => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // already released
    }
  };

  const page = Math.max(1, Math.floor((viewH || 300) / ROW));
  const thumbFrac = items.length <= 1 ? 0 : selectedIdx / (items.length - 1);

  const selectedRgb = hexToRgb(selected.hex) || [0, 0, 0];
  const [c, m, y, k] = rgbToCmyk(selectedRgb);
  const outOfGamut = c + m + y + k > WARN_TAC;

  const handleSearch = (value) => {
    setQuery(value);
    const q = value.trim().toLowerCase();
    if (!q) {
      setNoMatch(false);
      return;
    }
    const cleaned = q.replace(/^#/, "");
    const isHex = cleaned.length >= 3 && /^[0-9a-f]+$/i.test(cleaned);
    const qc = cleaned.replace(/\s+/g, "");
    const idx = itemsRef.current.findIndex((it) => {
      const nameN = it.name.toLowerCase();
      const nameC = nameN.replace(/\s+/g, "");
      if (isHex) return it.hex.slice(1).toLowerCase().startsWith(cleaned);
      return nameN.startsWith(q) || nameC.startsWith(qc);
    });
    if (idx >= 0) {
      selectAndScroll(idx);
      setNoMatch(false);
    } else {
      setNoMatch(true);
    }
  };

  const commitText = (e) => {
    if (e.key === "Enter") onCommit(selected.hex);
  };

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const start = Math.max(0, Math.floor(scrollTop / ROW) - 6);
  const end = Math.min(items.length, Math.ceil((scrollTop + viewH) / ROW) + 6);
  const rows = [];
  for (let i = start; i < end; i++) rows.push(i);

  const changeBook = (id) => {
    setBookId(id);
    setQuery("");
    setNoMatch(false);
  };

  return (
    <div
      className={styles.overlay}
      onClick={(e) => {
        e.stopPropagation();
        onCancel();
      }}
    >
      <div
        className={styles.lib}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.head}>
          <span className={styles.title}>Color Libraries</span>
          <button type="button" className="modal-close" aria-label="Close libraries" onClick={onCancel}>
            <Icon name="x" />
          </button>
        </div>

        <div className={styles.bookBar}>
          <label className={styles.bookLabel} htmlFor="cl-book">Book</label>
          <select id="cl-book" className={styles.bookSelect} value={bookId} onChange={(e) => changeBook(e.target.value)} aria-label="Color book">
            {BOOKS.map((b) => (
              <option key={b.id} value={b.id}>{b.label}</option>
            ))}
          </select>
        </div>

        <div className={styles.panes}>
          <div className={styles.listCol}>
            <div
              className={styles.viewport}
              ref={listRef}
              onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
            >
              <div style={{ position: "relative", height: items.length * ROW }}>
                {rows.map((i) => {
                  const item = items[i];
                  const active = i === selectedIdx;
                  const fg = fgStyle(item.hex);
                  return (
                    <div key={item.hex + "-" + i} className={styles.row} style={{ top: i * ROW }}>
                      <button
                        type="button"
                        className={styles.rowBtn + (active ? " " + styles.rowActive : "")}
                        style={{ background: item.hex }}
                        title={item.name + " · " + item.hex}
                        onClick={() => setSelectedIdx(i)}
                        onDoubleClick={() => onCommit(item.hex)}
                      >
                        {active && <span className={styles.rowMarker + " " + styles.rowMarkerL}>◀</span>}
                        <span className={styles.rowName} style={fg}>{item.name}</span>
                        {active && <span className={styles.rowMarker + " " + styles.rowMarkerR}>▶</span>}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <div className={styles.spectCol}>
            <button
              type="button"
              className={styles.spectArrow}
              title="Previous page"
              onClick={() => selectAndScroll(selectedIdx - page)}
            >
              ▲
            </button>
            <div
              className={styles.spectTrack}
              ref={trackRef}
              onPointerDown={onTrackDown}
              onPointerMove={onTrackMove}
              onPointerUp={onTrackUp}
              onPointerCancel={onTrackUp}
              title="Drag to jump through the color book"
            >
              <canvas ref={spectRef} className={styles.spectCanvas} />
              <span className={styles.spectThumb} style={{ top: thumbFrac * 100 + "%" }} />
            </div>
            <button
              type="button"
              className={styles.spectArrow}
              title="Next page"
              onClick={() => selectAndScroll(selectedIdx + page)}
            >
              ▼
            </button>
          </div>

          <div className={styles.infoCol}>
            <div className={styles.preview}>
              <div className={styles.previewCell}>
                <span className={styles.previewSwatch} style={{ background: initialHex }} />
                <span className={styles.previewCaption}>Current</span>
              </div>
              <div className={styles.previewCell}>
                <span className={styles.previewSwatch} style={{ background: selected.hex }} />
                <span className={styles.previewCaption}>New · {selected.name}</span>
              </div>
            </div>

            {outOfGamut && (
              <div className={styles.gamutBadge}>
                [!] Out of printable CMYK gamut — ink exceeds {WARN_TAC}%
              </div>
            )}

            <div className={styles.readout}>
              <div className={styles.readoutRow}>
                <span className={styles.readoutKey}>R</span>
                <span className={styles.readoutVal}>{Math.round(selectedRgb[0])}</span>
              </div>
              <div className={styles.readoutRow}>
                <span className={styles.readoutKey}>G</span>
                <span className={styles.readoutVal}>{Math.round(selectedRgb[1])}</span>
              </div>
              <div className={styles.readoutRow}>
                <span className={styles.readoutKey}>B</span>
                <span className={styles.readoutVal}>{Math.round(selectedRgb[2])}</span>
              </div>
              <div className={styles.readoutRow}>
                <span className={styles.readoutKey}>HEX</span>
                <span className={styles.readoutVal}>{selected.hex.toUpperCase()}</span>
              </div>
            </div>

            <div>
              <label className={styles.searchLabel} htmlFor="cl-search">Type to select</label>
              <input
                id="cl-search"
                type="text"
                className={styles.searchInput}
                value={query}
                spellCheck="false"
                placeholder="Name or HEX, e.g. Dark Red"
                onChange={(e) => handleSearch(e.target.value)}
                onKeyDown={commitText}
              />
            </div>
            {noMatch && <span className={styles.noMatch}>No matching color in this book</span>}

            <div className={styles.actions}>
              <div className={styles.actionRow}>
                <button type="button" className={"btn accent " + styles.actionPrimary} onClick={() => onCommit(selected.hex)}>
                  Apply
                </button>
                <button type="button" className="btn" onClick={onCancel}>Cancel</button>
              </div>
              <button type="button" className="btn" onClick={onPicker}>Picker</button>
              <span className={styles.pickerHint}>
                Picker returns to the main color picker without losing your work.
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}