import styles from "../SettingsPanel.module.scss";
import { TOOL_LABELS } from "./settingsShared.js";
import { Row, SettingsHead } from "./SettingsBits.jsx";
import { highlight } from "./highlight.jsx";

export default function GeneralSection({ stats, handleClear, general = {}, update, q }) {
  const counts = (stats && stats.counts) || {};
  const allowInternet = Boolean(general.allow_internet);
  return (
    <section className={styles.section}>
      <SettingsHead q={q} title="General / Presets" blurb="App-wide behaviour and everything saved as named presets per tool." />
      <Row label="Appearance theme" q={q}>
        <select value="" onChange={() => {}} aria-label="Appearance theme">
          <option value="">{highlight("Managed from the top bar", q)}</option>
        </select>
      </Row>

      <div className={styles.subHead}>{highlight("Network", q)}</div>
      <Row
        label="Internet access"
        q={q}
        hint="Allow the app to reach GitHub to check for updates. Opening links always happens in your browser."
      >
        <label className={styles.checkRow}>
          <input
            type="checkbox"
            checked={allowInternet}
            onChange={(e) => update("general", { allow_internet: e.target.checked })}
          />
          <span>{highlight("Allow access to internet", q)}</span>
        </label>
      </Row>

      <div className={styles.subHead}>{highlight("Updates", q)}</div>
      <Row
        label="Automatic update checks"
        q={q}
        hint={allowInternet ? "Check for new releases automatically each time the app starts." : "Re-enable internet access to turn on automatic update checks."}
      >
        <label className={styles.checkRow + (allowInternet ? "" : " " + styles.checkRowDisabled)}>
          <input
            type="checkbox"
            checked={Boolean(general.check_updates_automatically)}
            disabled={!allowInternet}
            onChange={(e) => update("general", { check_updates_automatically: e.target.checked })}
          />
          <span>{highlight("Check for updates automatically", q)}</span>
        </label>
      </Row>

      <div className={styles.subHead}>{highlight("Saved presets", q)}</div>
      <Row label="Per-tool presets" q={q} hint="Preset bars on each tool page handle saving, loading and deleting individual presets.">
        <div className={styles.presetChips}>
          {Object.keys(TOOL_LABELS).map((toolId) => {
            const n = (counts.presets_by_tool && counts.presets_by_tool[toolId]) || 0;
            return (
              <span key={toolId} className={styles.presetChip}>
                {highlight(TOOL_LABELS[toolId], q)}
                <span className={styles.presetChipCount}>{n}</span>
              </span>
            );
          })}
        </div>
      </Row>
      <Row label="Clear all presets" q={q} hint="Deletes every preset at once. Individual presets are managed from each tool page.">
        <div className={styles.inline}>
          <button type="button" className="btn danger" onClick={() => handleClear("presets")}>
            {highlight("Clear All Presets", q)}
          </button>
        </div>
      </Row>
    </section>
  );
}