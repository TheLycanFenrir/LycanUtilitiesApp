const STEP_MS = 100;
const CYCLE_MS = 4000;

const BRIGHT_R = 0;
const BRIGHT_G = 136;
const BRIGHT_B = 255;
const DIM_R = 0;
const DIM_G = 75;
const DIM_B = 123;

const reduceMotion =
  typeof window !== "undefined" &&
  window.matchMedia != null &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const nodes = new Map();
let timerId = null;

function lerp(from, to, phase) {
  return Math.round(from + (to - from) * phase);
}

function rgbString(r, g, b) {
  return "rgb(" + r + "," + g + "," + b + ")";
}

function glowString(r, g, b, alpha) {
  return "rgba(" + r + "," + g + "," + b + "," + alpha.toFixed(2) + ")";
}

function applyNode(el, kind, phase) {
  const r = lerp(BRIGHT_R, DIM_R, phase);
  const g = lerp(BRIGHT_G, DIM_G, phase);
  const b = lerp(BRIGHT_B, DIM_B, phase);
  if (kind === "frame") {
    el.style.borderColor = rgbString(r, g, b);
    el.style.boxShadow =
      "0 0 " + (16 - 4 * phase).toFixed(1) + "px " + glowString(r, g, b, 0.45 - 0.17 * phase) +
      ", inset 0 0 " + (24 - 4 * phase).toFixed(1) + "px " + glowString(r, g, b, 0.08 - 0.03 * phase);
  } else {
    el.style.webkitTextStrokeColor = rgbString(r, g, b);
    el.style.textShadow =
      "0 0 " + (6 - 2 * phase).toFixed(1) + "px " + glowString(r, g, b, 0.5 - 0.1 * phase) +
      ", 0 0 " + (16 - 4 * phase).toFixed(1) + "px " + glowString(r, g, b, 0.3 - 0.1 * phase);
  }
}

function tick() {
  const phase = 1 - Math.abs(2 * ((performance.now() / CYCLE_MS) % 1) - 1);
  for (const [el, kind] of nodes) {
    if (!el.isConnected) continue;
    applyNode(el, kind, phase);
  }
}

export function registerBluePulse(el, kind) {
  if (!el || nodes.has(el)) return;
  const k = kind === "frame" ? "frame" : "text";
  nodes.set(el, k);
  if (reduceMotion) {
    applyNode(el, k, 0);
    return;
  }
  if (nodes.size === 1) {
    tick();
    timerId = window.setInterval(tick, STEP_MS);
  }
}

export function unregisterBluePulse(el) {
  if (!el) return;
  nodes.delete(el);
  if (nodes.size === 0 && timerId !== null) {
    window.clearInterval(timerId);
    timerId = null;
  }
}