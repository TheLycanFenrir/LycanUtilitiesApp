import { useEffect, useRef } from "react";
import { Icon } from "../common/SvgIcon.jsx";
import EmojiText from "../common/EmojiText.jsx";
import { openExternalLink } from "../../utils/platform/bridge.js";
import useBluePulse from "../../hooks/useCyanPulse.js";

const STACK = ["FFmpeg", "PyWebView", "React"];

const FEATURES = [
  {
    title: "Frames to Video",
    text: "Turn image sequences into MP4, WebM, GIF, APNG or WEBP video, with full control over FPS, quality and encoding.",
  },
  {
    title: "Image Splitter",
    text: "Slice large textures into grids, custom tiles or alpha components, ready for reuse in your textures.",
  },
  {
    title: "Texture Mipmap Generator",
    text: "Generate mipmap chains for DDS and other texture workflows in a few clicks.",
  },
  {
    title: "Video Audio Merger",
    text: "Combine a video and an audio track into a single file. Coming soon.",
  },
];

export default function AboutModal({ app = {}, call, onClose }) {
  const titleRef = useRef(null);
  useBluePulse(titleRef);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const title = app.title || "Lycan Utilities";
  const subtitle = app.subtitle;
  const version = app.version;
  const contrib = app.contributor;
  const repoUrl = app.github_url || "https://github.com/TheLycanFenrir";

  return (
    <div className="about-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="about-card" role="dialog" aria-modal="true" aria-labelledby="about-title">
        <div className="about-banner">
          <img src="/assets/favicon.png" alt={title} />
        </div>
        <div className="about-body">
          <h3 ref={titleRef} className="about-title" id="about-title"><EmojiText text={"About " + title} /></h3>
          <div className="about-version-line">
            <span className="about-badge">Alpha</span>
            {version ? <span className="about-version">Version {version}</span> : null}
          </div>
          {subtitle ? <p className="about-desc"><EmojiText text={subtitle} /></p> : null}

          <div className="about-section-label">Capabilities</div>
          <ul className="about-features">
            {FEATURES.map((feature) => (
              <li key={feature.title} className="about-feature">
                <span className="about-feature-check">
                  <Icon name="check" />
                </span>
                <div className="about-feature-body">
                  <span className="about-feature-title"><EmojiText text={feature.title} /></span>
                  <span className="about-feature-text"><EmojiText text={feature.text} /></span>
                </div>
              </li>
            ))}
          </ul>

          <p className="about-stack">
            <EmojiText text={"Powered by " + STACK.join(", ") + ". Runs entirely offline — files never leave your machine."} />
          </p>
          {contrib ? (
            <p className="about-credits">
              Developed by <b><EmojiText text={contrib} /></b>. Feedback, bug reports and contributions are welcome on GitHub.
            </p>
          ) : null}

          <div className="about-actions">
            <button
              type="button"
              className="btn"
              onClick={() => {
                onClose();
                openExternalLink(call, repoUrl);
              }}
            >
              <Icon name="github" />
              View on GitHub
            </button>
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}