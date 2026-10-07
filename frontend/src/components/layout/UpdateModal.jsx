import { useEffect } from "react";
import { Icon } from "../common/SvgIcon.jsx";
import { openExternalLink } from "../../utils/platform/bridge.js";

export default function UpdateModal({ info = {}, call, onClose }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const changelog = Array.isArray(info.changelog) ? info.changelog : [];

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal update-modal" role="dialog" aria-modal="true" aria-label="Update available">
        <div className="modal-head">
          <h3 className="modal-title">Update Available</h3>
          <button type="button" className="modal-close" aria-label="Close" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        <p className="modal-message">
          A new version of Lycan Utilities is available. You are on <b>v{info.current || "—"}</b>; the
          latest release is <b>v{info.latest}</b>.
        </p>

        {changelog.length ? (
          <div className="update-changelog">
            <div className="update-changelog-head">What&apos;s new</div>
            <ul className="update-changelog-list">
              {changelog.map((entry, i) => (
                <li key={i} className="update-changelog-item">
                  <span className="update-changelog-title">{entry.title || entry}</span>
                  {entry.body ? <span className="update-changelog-body">{entry.body}</span> : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="modal-actions">
          <button
            type="button"
            className="btn accent"
            onClick={() => {
              onClose();
              openExternalLink(call, info.url);
            }}
          >
            <Icon name="github" />
            Open GitHub Releases
          </button>
          <button type="button" className="btn ghost" onClick={onClose}>Remind me later</button>
        </div>
      </div>
    </div>
  );
}
