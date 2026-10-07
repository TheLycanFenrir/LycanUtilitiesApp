export function emojiToTwemojiName(emoji) {
  if (!emoji) return "";
  const cps = [];
  for (const ch of emoji) {
    const cp = ch.codePointAt(0);
    if (cp === 0xfe0f) continue;
    cps.push(cp.toString(16));
  }
  if (!cps.length) return "";
  return cps.join("-");
}

export function emojiToTwemojiSrc(emoji) {
  const name = emojiToTwemojiName(emoji);
  return name ? `assets/twemoji/assets/svg/${name}.svg` : "";
}

const EMOJI_BASE =
  "[\\u{1F000}-\\u{1FAFF}\\u{1F1E6}-\\u{1F1FF}\\u{2600}-\\u{27BF}\\u{2B00}-\\u{2BFF}\\u{2300}-\\u{23FF}]";
const EMOJI_MOD =
  "(?:\\u{FE0F}?\\u{200D}" + EMOJI_BASE + "|\\u{FE0F}|\\u{20E3})";
const EMOJI_KEYCAP =
  "[0-9#*]\\u{FE0F}\\u{20E3}";
const EMOJI_FULL =
  "(?:" + EMOJI_KEYCAP + "|" + EMOJI_BASE + EMOJI_MOD + "*)";

export const EMOJI_RE = new RegExp("(" + EMOJI_FULL + ")+", "gu");