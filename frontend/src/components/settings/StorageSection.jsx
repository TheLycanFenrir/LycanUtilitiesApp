import styles from "../SettingsPanel.module.scss";
import { HISTORY_SLOTS, formatBytes } from "./settingsShared.js";
import { SettingsHead } from "./SettingsBits.jsx";
import { highlight } from "./highlight.jsx";

export default function StorageSection({ stats, history, browserRecents, handleClear, q }) {
  const counts = (stats && stats.counts) || {};
  const files = (stats && stats.files) || {};
  return (
    <section className={styles.section}>
      <SettingsHead q={q} title="Internal Storage & Cache" blurb="A snapshot of everything the app persists on disk and in the browser." />
      <div className={styles.subHead}>{highlight("Stored bytes", q)}</div>
      <div className={styles.statList}>
        {[
          { key: "settings", label: "Settings & per-tool forms", count: "" },
          { key: "presets", label: "Presets", count: counts.presets_total ? counts.presets_total + " preset" + (counts.presets_total === 1 ? "" : "s") : "" },
          { key: "history", label: "Input history", count: counts.history_entries ? counts.history_entries + " entries" : "" },
          { key: "favorites", label: "Dashboard favorites", count: counts.favorites ? counts.favorites + " starred" : "" },
          { key: "last_used", label: "Last-used timestamps", count: "" },
        ].map((row) => (
          <div key={row.key} className={styles.statRow}>
            <span className={styles.statLabel}>{highlight(row.label, q)}</span>
            {row.count ? <span className={styles.statCount}>{highlight(row.count, q)}</span> : null}
            <span className={styles.statBytes}>{(files[row.key] && formatBytes(files[row.key].bytes)) || "0 B"}</span>
          </div>
        ))}
        <div className={styles.statRow}>
          <span className={styles.statLabel}>{highlight("Recent colors (browser cache)", q)}</span>
          <span className={styles.statCount}>{highlight(browserRecents.count + " swatches", q)}</span>
          <span className={styles.statBytes}>{formatBytes(browserRecents.bytes)}</span>
        </div>
      </div>

      <div className={styles.subHead}>{highlight("Past input history", q)}</div>
      <p className={styles.hint}>{highlight("The tool pages read these entries into their source / target dropdowns.", q)}</p>
      {HISTORY_SLOTS.map((slot) => (
        <div key={slot.key} className={styles.histRow}>
          <label className={styles.histLabel}>{highlight(slot.tool + " — " + slot.label, q)}</label>
          <select
            className={styles.histSelect}
            value=""
            aria-label={slot.label}
          >
            <option value="">
              {history && history[slot.key] && history[slot.key].length
                ? highlight(history[slot.key].length + " remembered", q)
                : highlight("Nothing remembered yet", q)}
            </option>
            {history && history[slot.key]
              ? history[slot.key].map((entry) => (
                  <option key={entry} value={entry}>{entry}</option>
                ))
              : null}
          </select>
        </div>
      ))}

      <div className={styles.subHead}>{highlight("Danger zone", q)}</div>
      <div className={styles.dangerRow}>
        <button type="button" className="btn danger" onClick={() => handleClear("data")}>
          {highlight("Clear Internal Storage & Cache", q)}
        </button>
        <button type="button" className="btn danger" onClick={() => handleClear("presets")}>
          {highlight("Clear All Presets", q)}
        </button>
        <button type="button" className="btn danger" onClick={() => handleClear("history")}>
          {highlight("Clear Last Inputted History", q)}
        </button>
      </div>
    </section>
  );
}