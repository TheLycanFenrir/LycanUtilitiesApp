import styles from "../SettingsPanel.module.scss";
import { Row, SettingsHead } from "./SettingsBits.jsx";
import { highlight } from "./highlight.jsx";

export default function ColorPickingSection({ cp, update, q }) {
  return (
    <section className={styles.section}>
      <SettingsHead title="Color Picking" q={q} blurb="Defaults applied every time the color picker opens." />
      <Row
        label="Recent colors remembered"
        q={q}
        hint="Palette and bookmark swatches are stored separately and are not limited."
      >
        <div className={styles.inline}>
          <input
            type="number"
            min="1"
            max="200"
            value={cp.max_recents}
            onChange={(e) => {
              const n = parseInt(e.target.value, 10);
              update("color_picking", {
                max_recents: Number.isFinite(n) ? Math.max(1, Math.min(200, n)) : 25,
              });
            }}
          />
          <span className={styles.valueNote}>{highlight("swatches (1–200)", q)}</span>
        </div>
      </Row>
      <Row label="Default format" q={q} hint="The channel mode the picker starts in each time it opens.">
        <select
          value={cp.default_format === "hsv" ? "hsv" : "rgb"}
          aria-label="Default color picker format"
          onChange={(e) => update("color_picking", { default_format: e.target.value })}
        >
          <option value="rgb">sRGB (R / G / B)</option>
          <option value="hsv">HSV (H / S / V)</option>
        </select>
      </Row>
    </section>
  );
}