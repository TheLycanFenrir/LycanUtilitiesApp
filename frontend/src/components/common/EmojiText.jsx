import { useState } from "react";
import { EMOJI_RE, emojiToTwemojiSrc } from "../../utils/emoji/twemoji.js";

const NBSP = "\u00A0";

export function Emoji({ emoji, size = "1em", className = "" }) {
  const [failed, setFailed] = useState(false);
  const src = emojiToTwemojiSrc(emoji);
  if (!src || failed) {
    return (
      <span className={"twemoji-native" + (className ? " " + className : "")} style={{ fontSize: size }}>
        {emoji}
      </span>
    );
  }
  return (
    <img
      src={src}
      alt={emoji}
      className={"twemoji" + (className ? " " + className : "")}
      style={{ height: size, width: size }}
      loading="lazy"
      draggable={false}
      onError={() => setFailed(true)}
    />
  );
}

export default function EmojiText({ text, className = "", size = "1em" }) {
  if (text == null) return null;
  const str = String(text);
  if (!str) return str;
  const parts = str.split(EMOJI_RE);
  if (parts.length === 1) return str;
  return parts.map((part, idx) => {
    if (!part) return null;
    if (idx % 2 === 1) {
      const trimmed = part.trim();
      const padLeft = part.length - part.trimStart().length ? NBSP : "";
      const padRight = part.length - part.trimEnd().length ? NBSP : "";
      return (
        <span key={idx} className={"twemoji-run" + (className ? " " + className : "")}>
          {padLeft}
          <Emoji emoji={trimmed} size={size} />
          {padRight}
        </span>
      );
    }
    return <span key={idx}>{part}</span>;
  });
}