import styles from "../SettingsPanel.module.scss";
import { highlight } from "./highlight.jsx";

export function SettingsHead({ title, blurb, q }) {
  return (
    <div className={styles.head}>
      <h3 className={styles.headTitle}>{highlight(title, q)}</h3>
      {blurb ? <p className={styles.headBlurb}>{highlight(blurb, q)}</p> : null}
    </div>
  );
}

export function Row({ label, hint, children, q }) {
  return (
    <div className={styles.row}>
      <label className={styles.rowLabel}>{highlight(label, q)}</label>
      <div className={styles.rowControl}>{children}</div>
      {hint ? <span className={styles.rowHint}>{highlight(hint, q)}</span> : null}
    </div>
  );
}