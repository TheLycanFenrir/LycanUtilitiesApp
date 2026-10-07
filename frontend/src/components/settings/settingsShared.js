export const DEFAULT_SETTINGS = {
  version: 1,
  ffmpeg: { path: "", use_system_path: true },
  color_picking: { max_recents: 25, default_format: "rgb" },
  general: { theme: "", allow_internet: false, check_updates_automatically: false },
  python_libraries: { local_only: true },
};

// Mirror keys read by ColorPickerModal when it opens.
export const K_MAX_RECENTS = "lycan.color.maxRecents";
export const K_DEFAULT_FORMAT = "lycan.color.defaultFormat";
export const K_COLOR_RECENTS = "lycan.color.recents";

export const HISTORY_SLOTS = [
  { key: "frames_to_video_source", tool: "Frames to Video", label: "Past source folders" },
  { key: "frames_to_video_output", tool: "Frames to Video", label: "Past target files / folders" },
  { key: "image_split_source", tool: "Image Splitter", label: "Past source files / folders" },
  { key: "image_split_output", tool: "Image Splitter", label: "Past target folders" },
  { key: "texture_mipmap_source", tool: "Texture Mipmap", label: "Past source files / folders" },
  { key: "texture_mipmap_output", tool: "Texture Mipmap", label: "Past target folders" },
];

export const TOOL_LABELS = {
  frames_to_video: "Frames to Video",
  image_splitter: "Image Splitter",
  texture_mipmap: "Texture Mipmap",
};

export function formatBytes(n) {
  if (!Number.isFinite(n) || n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = n;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return value.toFixed(unit === 0 ? 0 : 1) + " " + units[unit];
}

export function readBrowserRecents() {
  try {
    const raw = localStorage.getItem(K_COLOR_RECENTS);
    if (!raw) return { count: 0, bytes: 0 };
    const parsed = JSON.parse(raw);
    return { count: Array.isArray(parsed) ? parsed.length : 0, bytes: raw.length };
  } catch {
    return { count: 0, bytes: 0 };
  }
}

export function clearBrowserRecents() {
  try {
    localStorage.removeItem(K_COLOR_RECENTS);
  } catch {
    // storage unavailable
  }
}

export async function fetchStorageStats(call) {
  const res = await call("get_storage_stats");
  return res && typeof res === "object" ? res : null;
}

export async function fetchInputHistory(call) {
  const results = await Promise.all(
    HISTORY_SLOTS.map((slot) => call("get_history", "paths", slot.key)),
  );
  const next = {};
  HISTORY_SLOTS.forEach((slot, i) => {
    next[slot.key] = Array.isArray(results[i]) ? results[i] : [];
  });
  return next;
}