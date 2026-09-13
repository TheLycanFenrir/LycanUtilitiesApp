import { Icon } from "../common/SvgIcon.jsx";
import styles from "../SettingsPanel.module.scss";
import { Row, SettingsHead } from "./SettingsBits.jsx";
import { highlight } from "./highlight.jsx";
import { openExternalLink } from "../../utils/platform/bridge.js";

export default function FFmpegSection({ call, ffmpeg, update, detected, detectedBusy, runDetect, browseFfmpeg, showToast, q }) {
  return (
    <section className={styles.section}>
      <SettingsHead title="FFmpeg" q={q} blurb="Locate the FFmpeg / FFprobe executables used by the video tools. Leave system PATH enabled to use any ffmpeg already installed on PATH." />
      <Row label="Binary lookup" q={q}>
        <label className={styles.checkRow}>
          <input
            type="checkbox"
            checked={Boolean(ffmpeg.use_system_path)}
            onChange={(e) => update("ffmpeg", { use_system_path: e.target.checked })}
          />
          <span>{highlight("Use system PATH for ffmpeg / ffprobe", q)}</span>
        </label>
      </Row>
      <Row
        label="Custom path"
        q={q}
        hint={
          ffmpeg.use_system_path
            ? "Manual path is ignored while system PATH lookup is enabled."
            : "Directory holding ffmpeg.exe / ffprobe.exe, or the full path to ffmpeg.exe."
        }
      >
        <div className={styles.inline}>
          <input
            type="text"
            spellCheck="false"
            placeholder="C:\\ffmpeg\\bin"
            value={ffmpeg.path}
            disabled={Boolean(ffmpeg.use_system_path)}
            onChange={(e) => update("ffmpeg", { path: e.target.value })}
          />
          <button type="button" className="btn" onClick={browseFfmpeg}>Browse…</button>
        </div>
      </Row>
      <Row label="Auto-detect" q={q}>
        <div className={styles.inline}>
          <button
            type="button"
            className="btn"
            disabled={detectedBusy}
            onClick={runDetect}
          >
            {detectedBusy ? "Scanning…" : highlight("Scan PATH & common folders", q)}
          </button>
        </div>
        {detected && (
          <div className={styles.detectedBox}>
            {detected.system ? (
              <p className={styles.detectedOk}>
                <Icon name="check" /> {highlight("ffmpeg already resolves on the system PATH.", q)}
              </p>
            ) : (
              <p className={styles.detectedWarn}>{highlight("ffmpeg was not found on the system PATH.", q)}</p>
            )}
            {Array.isArray(detected.dirs) && detected.dirs.length ? (
              <select
                className={styles.detectedSelect}
                value=""
                aria-label="Detected FFmpeg directories"
                onChange={(e) => {
                  if (e.target.value) {
                    update("ffmpeg", { path: e.target.value, use_system_path: false });
                    showToast({ message: "FFmpeg location applied.", type: "good" });
                  }
                }}
              >
                <option value="">Apply a detected directory…</option>
                {detected.dirs.map((item) => (
                  <option key={item.dir} value={item.dir}>
                    {item.dir} · {item.binaries.join(", ")}
                  </option>
                ))}
              </select>
            ) : (
              !detected.system && <p className={styles.detectedNone}>{highlight("No FFmpeg installation was found.", q)}</p>
            )}
          </div>
        )}
      </Row>
      <Row
        label="Download & update"
        q={q}
        hint="Open the official FFmpeg site to get the latest build if FFmpeg is missing or outdated."
      >
        <div className={styles.inline}>
          <button
            type="button"
            className="btn"
            onClick={() => openExternalLink(call, "https://ffmpeg.org/download.html")}
          >
            Go to FFmpeg site
          </button>
        </div>
      </Row>
    </section>
  );
}