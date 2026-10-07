/**
 * Pure helpers for mapping JSON UI nodes onto React element props.
 *
 * Shared by ElementGenerator, SectionGenerator and PopupGenerator so the
 * rendering components stay thin and attribute handling stays in one place.
 */

export const HTML_TAGS = new Set([
  "div", "span", "p", "h1", "h2", "h3", "h4", "h5", "h6",
  "button", "label", "section", "header", "footer", "main", "aside", "nav",
  "ul", "ol", "li", "small", "strong", "em", "b", "i", "u", "code", "pre",
  "hr", "br", "img", "a",
]);

// JSON property name -> React DOM attribute. `type` doubles as the node
// discriminator, so the actual HTML `type` attribute is spelled `typeAttribute`.
export const HTML_ATTR_MAP = {
  idName: "id",
  typeAttribute: "type",
  title: "title",
  disabled: "disabled",
  href: "href",
  target: "target",
  rel: "rel",
  placeholder: "placeholder",
  role: "role",
  alt: "alt",
  src: "src",
  width: "width",
  height: "height",
  value: "value",
  ariaLabel: "aria-label",
  "aria-label": "aria-label",
};

// Properties that are consumed by the generators and must never leak onto the
// DOM element (they are handled explicitly, not forwarded).
export const SKIP_KEYS = new Set([
  "type",
  "children",
  "header",
  "actions",
  "footer",
  "innerText",
  "innerHTML",
  "styleCSS",
  "className",
  "idName",
  "field_id",
  "label_name",
  "field_visibility",
  "show_if",
  "hide_if",
  "actionId",
  "actionParams",
]);

// The root container markers: sections render as `data-section`, popups as
// `data-popup` (mirrors the classic container-data-attribute convention).
export const CONTAINER_DATA_ATTR = {
  section: "data-section",
  popup: "data-popup",
};

export function kebabToCamel(value) {
  if (typeof value !== "string") return value;
  return value.replace(/-([a-z])/gi, (_, ch) => ch.toUpperCase());
}

export function normalizeStyle(styleCSS) {
  if (!styleCSS || typeof styleCSS !== "object") return undefined;
  const out = {};
  for (const key of Object.keys(styleCSS)) {
    const value = styleCSS[key];
    if (value == null) continue;
    out[kebabToCamel(key)] = value;
  }
  return Object.keys(out).length ? out : undefined;
}

/**
 * Resolve the stable identity of a UI node: `idName` first, then the field_id
 * (for form references), then the action id, else undefined.
 */
export function nodeIdentity(node, fallback) {
  if (!node || typeof node !== "object") return fallback;
  if (typeof node.idName === "string" && node.idName) return node.idName;
  if (typeof node.field_id === "string" && node.field_id) return node.field_id;
  if (typeof node.actionId === "string" && node.actionId) return node.actionId;
  return fallback;
}

/**
 * Build the DOM props for a JSON element node: mapped attributes, passthrough
 * data- and aria- prefixed keys, className and normalized inline styleCSS.
 */
export function buildElementProps(node) {
  const props = {};
  for (const key of Object.keys(node)) {
    if (key in HTML_ATTR_MAP) {
      const value = node[key];
      if (value == null) continue;
      props[HTML_ATTR_MAP[key]] = key === "disabled" ? Boolean(value) : value;
      continue;
    }
    if (key.startsWith("data-") || key.startsWith("aria-")) {
      const value = node[key];
      if (
        typeof value === "string" ||
        typeof value === "number" ||
        typeof value === "boolean"
      ) {
        props[key] = value;
      }
      continue;
    }
    if (SKIP_KEYS.has(key)) continue;
  }
  if (typeof node.className === "string" && node.className.trim()) {
    props.className = node.className.trim();
  }
  const style = normalizeStyle(node.styleCSS);
  if (style) props.style = style;
  return props;
}