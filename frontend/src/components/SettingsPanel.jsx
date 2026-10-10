import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Icon, PythonIcon } from "./common/SvgIcon.jsx";
import { useModal } from "../contexts/ModalContext.jsx";
import { useToast } from "../contexts/ToastContext.jsx";
import { highlight } from "./settings/highlight.jsx";
import styles from "./SettingsPanel.module.scss";
import FFmpegSection from "./settings/FFmpegSection.jsx";
import ColorPickingSection from "./settings/ColorPickingSection.jsx";
import StorageSection from "./settings/StorageSection.jsx";
import GeneralSection from "./settings/GeneralSection.jsx";
import PythonLibrariesSection from "./settings/PythonLibrariesSection.jsx";
import {
  DEFAULT_SETTINGS,
  K_MAX_RECENTS,
  K_DEFAULT_FORMAT,
  clearBrowserRecents,
  fetchInputHistory,
  fetchStorageStats,
  readBrowserRecents,
} from "./settings/settingsShared.js";

const SECTIONS = [
  { id: "ffmpeg", label: "FFmpeg", icon: "cpu" },
  { id: "color", label: "Color Picking", icon: "eyedropper" },
  { id: "python", label: "Python Libraries", icon: "code-bracket" },
  { id: "storage", label: "Internal Storage & Cache", icon: "ram" },
  { id: "general", label: "General / Presets", icon: "sun" },
];

const SECTION_KEY = "lycan.settings.section";

const NARROW_QUERY = "(max-width: 720px)";

function useIsNarrow() {
  const [narrow, setNarrow] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(NARROW_QUERY).matches
      : false,
  );
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return undefined;
    const mql = window.matchMedia(NARROW_QUERY);
    const onChange = (e) => setNarrow(e.matches);
    if (typeof mql.addEventListener === "function") mql.addEventListener("change", onChange);
    else mql.addListener(onChange);
    return () => {
      if (typeof mql.removeEventListener === "function") mql.removeEventListener("change", onChange);
      else mql.removeListener(onChange);
    };
  }, []);
  return narrow;
}

function readSavedSection() {
  try {
    const value = localStorage.getItem(SECTION_KEY);
    return value && SECTIONS.some((s) => s.id === value) ? value : "";
  } catch {
    return "";
  }
}

function writeSavedSection(id) {
  try {
    localStorage.setItem(SECTION_KEY, id);
  } catch {
    // storage unavailable
  }
}

function mergeDoc(base, doc) {
  const out = { ...base };
  for (const key of Object.keys(out)) {
    if (!doc) continue;
    if (typeof out[key] === "object" && out[key] !== null && typeof doc[key] === "object" && doc[key] !== null) {
      out[key] = { ...out[key], ...doc[key] };
    } else if (doc[key] !== undefined) {
      out[key] = doc[key];
    }
  }
  return out;
}

function sectionCorpus(id, settings, stats) {
  const g = (v) => (v == null ? "" : String(v));
  const counts = (stats && stats.counts) || {};
  let text = "";
  if (id === "ffmpeg") {
    const f = (settings && settings.ffmpeg) || {};
    text = [
      "FFmpeg FFprobe executables used by the video tools Leave system PATH enabled any ffmpeg installed on PATH",
      "Binary lookup Use system PATH for ffmpeg / ffprobe",
      "Custom path Directory holding ffmpeg.exe / ffprobe.exe or the full path to ffmpeg.exe",
      "Manual path is ignored while system PATH lookup is enabled",
      "Auto-detect Scan PATH & common folders apply a detected directory",
      "Download & update official FFmpeg site latest build missing outdated Go to FFmpeg site Browse",
      "No FFmpeg installation was found ffmpeg already resolves on the system PATH",
      g(f.path),
    ].join(" ");
  } else if (id === "color") {
    const cp = (settings && settings.color_picking) || {};
    text = [
      "Color Picking defaults applied every time the color picker opens",
      "Recent colors remembered Palette and bookmark swatches are stored separately and are not limited",
      "swatches 1-200",
      "Default format channel mode picker starts sRGB RGB HSV",
      g(cp.max_recents),
      g(cp.default_format),
    ].join(" ");
  } else if (id === "storage") {
    text = [
      "Internal Storage & Cache snapshot of everything the app persists on disk and in the browser",
      "Stored bytes Settings & per-tool forms Presets Input history Dashboard favorites",
      "Last-used timestamps Recent colors browser cache swatches",
      "Past input history tool pages read these entries into their source target dropdowns",
      "Danger zone Clear Internal Storage & Cache Clear All Presets Clear Last Inputted History",
      "clear all data settings presets history favorites last-used recent color cache",
      g(counts.presets_total),
      g(counts.history_entries),
      g(counts.favorites),
      g(counts.last_used),
    ].join(" ");
  } else if (id === "general") {
    const gen = (settings && settings.general) || {};
    text = [
      "General Presets app-wide behaviour named presets per tool",
      "Appearance theme managed from the top bar",
      "Network Internet access Allow access to internet reach GitHub check for updates opening links browser",
      "Updates Automatic update checks Check for updates automatically new releases app starts",
      "Saved presets per-tool presets preset bars tool page saving loading deleting",
      "Clear all presets deletes every preset individual presets tool page",
      gen.allow_internet ? "enabled" : "disabled",
      gen.check_updates_automatically ? "enabled" : "disabled",
      g(gen.theme),
    ].join(" ");
  } else if (id === "python") {
    const pl = (settings && settings.python_libraries) || {};
    text = [
      "Python Libraries install and manage python packages dependencies pip PyPI",
      "per-utility requirements needed by the tools such as Pillow numpy",
      "search install update uninstall refresh package index internet PyPI enabled disabled",
      "local environment only recommended shared system python interpreter base venv",
      "requirements.txt installed missing outdated core protected third party",
      "FFmpeg external tool check",
      pl.local_only ? "local only" : "global shared",
    ].join(" ");
  }
  return text.toLowerCase();
}

export default function SettingsPanel({ call, onClose, initialSection }) {
  const [settings, setSettings] = useState(null);
  const [active, setActive] = useState(() => initialSection || readSavedSection() || "ffmpeg");
  const [view, setView] = useState(() => (initialSection ? "details" : "menu"));
  const [q, setQ] = useState("");
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState(null);
  const [detected, setDetected] = useState(null);
  const [detectedBusy, setDetectedBusy] = useState(false);
  const [browserRecents, setBrowserRecents] = useState(readBrowserRecents);
  const isNarrow = useIsNarrow();
  const { confirm } = useModal();
  const { showToast } = useToast();

  const timerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    fetchStorageStats(call).then((res) => {
      if (!cancelled && res) setStats(res);
    });
    fetchInputHistory(call).then((next) => {
      if (!cancelled) setHistory(next);
    });
    (async () => {
      const res = await call("get_app_settings");
      if (cancelled) return;
      const doc = res && res.ok !== false ? res.settings : null;
      setSettings(doc && typeof doc === "object" ? mergeDoc(DEFAULT_SETTINGS, doc) : { ...DEFAULT_SETTINGS });
    })();
    return () => {
      cancelled = true;
    };
  }, [call]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (!settings) return;
    const cp = settings.color_picking || {};
    try {
      localStorage.setItem(K_MAX_RECENTS, String(cp.max_recents == null ? 25 : cp.max_recents));
      localStorage.setItem(K_DEFAULT_FORMAT, cp.default_format === "hsv" ? "hsv" : "rgb");
    } catch {
      // storage unavailable
    }
  }, [settings]);

  const persist = useCallback(
    (next) => {
      call("save_app_settings", next);
    },
    [call],
  );

  const update = useCallback(
    (section, patch) => {
      setSettings((prev) => {
        const base = prev || { ...DEFAULT_SETTINGS };
        const next = { ...base, [section]: { ...base[section], ...patch } };
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => persist(next), 300);
        return next;
      });
    },
    [persist],
  );

  const selectSection = useCallback((id) => {
    setActive(id);
    writeSavedSection(id);
    setView("details");
  }, []);

  const goBack = useCallback(() => setView("menu"), []);

  const qTrim = q.trim().toLowerCase();
  const results = useMemo(() => {
    if (!qTrim) return null;
    const hits = [];
    for (const section of SECTIONS) {
      if (sectionCorpus(section.id, settings, stats).includes(qTrim)) hits.push(section);
    }
    return hits;
  }, [qTrim, settings, stats]);
  const activeHasHit = !qTrim || (results && results.some((s) => s.id === active));
  const searching = Boolean(qTrim);

  const runDetect = async () => {
    setDetectedBusy(true);
    const res = await call("detect_ffmpeg");
    setDetectedBusy(false);
    setDetected(res && typeof res === "object" ? res : { system: false, dirs: [] });
  };

  const browseFfmpeg = async () => {
    const current = (settings && settings.ffmpeg && settings.ffmpeg.path) || "";
    const initial = current.toLowerCase().endsWith(".exe")
      ? current.slice(0, current.lastIndexOf("\\"))
      : current;
    const picked = await call("open_dialog", "file", initial, "", false, ["Executable files (*.exe)", "All files (*.*)"]);
    const path = picked && picked.ok !== false && Array.isArray(picked.paths) ? picked.paths[0] : null;
    if (path) update("ffmpeg", { path, use_system_path: false });
  };

  const handleClear = async (kind) => {
    const plan = {
      data: {
        title: "Clear Internal Storage & Cache?",
        message:
          "This deletes all saved settings, presets, history, favorites and last-used data on disk, plus the recent color cache stored in the browser.",
      },
      presets: {
        title: "Clear All Presets?",
        message: "All saved presets across every tool will be deleted. This cannot be undone.",
      },
      history: {
        title: "Clear Last Inputted History?",
        message: "Every remembered source / target path across all forms will be forgotten.",
      },
    };
    const ok = await confirm({ ...plan[kind], yes: "Clear", no: "Cancel", danger: true });
    if (!ok) return;
    if (timerRef.current) clearTimeout(timerRef.current);

    if (kind === "data") {
      await call("clear_all_data");
      clearBrowserRecents();
      setSettings({ ...DEFAULT_SETTINGS });
      setDetected(null);
      showToast({ message: "Internal storage & cache cleared.", type: "good" });
    } else if (kind === "presets") {
      await call("clear_all_presets");
      showToast({ message: "All presets cleared.", type: "good" });
    } else {
      await call("clear_all_history");
      showToast({ message: "Input history cleared.", type: "good" });
    }
    setBrowserRecents(readBrowserRecents());
    setStats(await fetchStorageStats(call));
    setHistory(await fetchInputHistory(call));
  };

  const cp = (settings && settings.color_picking) || DEFAULT_SETTINGS.color_picking;
  const ffmpeg = (settings && settings.ffmpeg) || DEFAULT_SETTINGS.ffmpeg;
  const general = (settings && settings.general) || DEFAULT_SETTINGS.general;
  const python = (settings && settings.python_libraries) || DEFAULT_SETTINGS.python_libraries;

  return (
    <div className={styles.overlay} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={styles.panel} role="dialog" aria-modal="true" aria-label="Settings">
        <header className={styles.header}>
          <span className={styles.title}>Settings</span>
          <div className={styles.searchBar}>
            <Icon name="search" />
            <input
              type="text"
              value={q}
              placeholder="Search descriptions, parameters, categories…"
              spellCheck="false"
              onChange={(e) => setQ(e.target.value)}
            />
            {q ? (
              <button type="button" className={styles.searchClear} aria-label="Clear search" onClick={() => setQ("")}>
                <Icon name="x" />
              </button>
            ) : null}
          </div>
          <button type="button" className="modal-close" aria-label="Close settings" onClick={onClose}>
            <Icon name="x" />
          </button>
        </header>

        {searching ? (
          <div className={styles.results}>
            {results && results.length ? (
              <>
                <span className={styles.resultsLabel}>Found in:</span>
                {results.map((section) => (
                  <button
                    key={section.id}
                    type="button"
                    className={styles.searchChip + (active === section.id ? " " + styles.searchChipActive : "")}
                    onClick={() => selectSection(section.id)}
                  >
                    {section.label}
                  </button>
                ))}
              </>
            ) : (
              <span className={styles.resultsNone}>No settings match “{qTrim}”.</span>
            )}
          </div>
        ) : null}

        <div className={styles.body}>
          {!isNarrow || view === "menu" ? (
            <nav
              className={styles.sidebar + (isNarrow && view === "menu" ? " " + styles.sidebarDrill : "")}
              aria-label="Setting categories"
            >
              {SECTIONS.map((section) => {
                const hit = searching && results && results.some((s) => s.id === section.id);
                return (
                  <button
                    key={section.id}
                    type="button"
                    className={
                      styles.navItem +
                      (active === section.id ? " " + styles.navActive : "") +
                      (searching && !hit ? " " + styles.navNoHit : "") +
                      (searching && hit ? " " + styles.navHit : "")
                    }
                    onClick={() => selectSection(section.id)}
                  >
                    <span className={styles.navIcon}>
                      {section.id === "python" ? <PythonIcon /> : <Icon name={section.icon} />}
                    </span>
                    <span className={styles.navLabel}>{highlight(section.label, qTrim)}</span>
                  </button>
                );
              })}
            </nav>
          ) : null}

          {!isNarrow || view === "details" ? (
            <main className={styles.content + (isNarrow && view === "details" ? " " + styles.contentDrill : "")}>
              {isNarrow && view === "details" ? (
                <button type="button" className={styles.backBtn} onClick={goBack}>
                  <Icon name="arrow-left" />
                  Back to Categories
                </button>
              ) : null}
              {searching && !activeHasHit ? (
                <p className={styles.searchNoMatch}>No matches in this category — see the found categories above.</p>
              ) : null}
              {active === "ffmpeg" && (
                <FFmpegSection
                  call={call}
                  ffmpeg={ffmpeg}
                  update={update}
                  detected={detected}
                  detectedBusy={detectedBusy}
                  runDetect={runDetect}
                  browseFfmpeg={browseFfmpeg}
                  showToast={showToast}
                  q={qTrim}
                />
              )}
              {active === "color" && (
                <ColorPickingSection cp={cp} update={update} q={qTrim} />
              )}
              {active === "storage" && (
                <StorageSection
                  stats={stats}
                  history={history}
                  browserRecents={browserRecents}
                  handleClear={handleClear}
                  q={qTrim}
                />
              )}
              {active === "general" && (
                <GeneralSection stats={stats} handleClear={handleClear} general={general} update={update} q={qTrim} />
              )}
              {active === "python" && (
                <PythonLibrariesSection
                  call={call}
                  python={python}
                  update={update}
                  general={general}
                  confirm={confirm}
                  showToast={showToast}
                  q={qTrim}
                />
              )}
            </main>
          ) : null}
        </div>

        <footer className={styles.footer}>
          <span className={styles.footerNote}>Changes are saved automatically to settings.json.</span>
          <button type="button" className="btn accent" onClick={onClose}>Done</button>
        </footer>
      </div>
    </div>
  );
}