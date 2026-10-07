/**
 * Layout planning for the data-driven form.
 *
 * The planner walks the raw schema (not the hydrated store) so containers keep
 * the position their author declared, then mixes in groups of ordinary fields
 * (keyed by their `part` title, "Inputs" default). Fields that a container
 * owns via form_component / form_field references never become panels.
 *
 *   blocks: [{ order, kind: "group" | "container", title?, node? }] sorted
 *           by author position; container blocks wrap section/popup nodes.
 *   groups: title -> { title, entries } for all panel-ready fields.
 *   hasContent: true when any panel or visible container exists.
 */

import { isNodeVisible } from "../../utils/form/visibility.js";
import { isUiContainerType } from "./nodeRegistry.js";

function fieldTitle(entry) {
  const part = entry.schema.part;
  return typeof part === "string" && part.trim() ? part.trim() : "Inputs";
}

export function collectGroups({ schema, snapshot, sectionOwned }) {
  const groups = new Map();
  const orderedTitles = [];
  const firstIndex = new Map();
  const seen = new Set();

  (schema || []).forEach((node, index) => {
    if (!node || typeof node !== "object") return;
    if (isUiContainerType(node.type)) return;
    const fid = typeof node.field_id === "string" ? node.field_id : null;
    if (!fid) return;
    seen.add(fid);
    if (sectionOwned && sectionOwned.has(fid)) return;
    const entry = snapshot.fields[fid];
    if (!isNodeVisible(entry, snapshot)) return;
    const title = fieldTitle(entry);
    if (!groups.has(title)) {
      groups.set(title, { title, entries: [] });
      orderedTitles.push(title);
      firstIndex.set(title, index);
    }
    groups.get(title).entries.push(entry);
  });

  for (const entry of Object.values(snapshot.fields)) {
    if (!entry || !entry.schema) continue;
    const fid = entry.schema.field_id;
    if (seen.has(fid) || (sectionOwned && sectionOwned.has(fid))) continue;
    if (!isNodeVisible(entry, snapshot)) continue;
    const title = fieldTitle(entry);
    if (!groups.has(title)) {
      groups.set(title, { title, entries: [] });
      orderedTitles.push(title);
      firstIndex.set(title, Number.MAX_SAFE_INTEGER);
    }
    groups.get(title).entries.push(entry);
  }

  return { groups, orderedTitles, firstIndex };
}

export function buildLayout({ schema, snapshot, sectionOwned }) {
  const base = collectGroups({ schema, snapshot, sectionOwned });
  const containers = [];
  (schema || []).forEach((node, index) => {
    if (!node || typeof node !== "object") return;
    if (!isUiContainerType(node.type)) return;
    containers.push({ index, node });
  });

  const blocks = [];
  for (const { index, node } of containers) {
    if (!isNodeVisible(node, snapshot)) continue;
    blocks.push({ order: index, kind: "container", node });
  }
  for (const title of base.orderedTitles) {
    blocks.push({ order: base.firstIndex.get(title), kind: "group", title });
  }
  blocks.sort((a, b) => a.order - b.order);

  return {
    groups: base.groups,
    orderedTitles: base.orderedTitles,
    blocks,
    hasContent: base.orderedTitles.length > 0 || blocks.some((block) => block.kind === "container"),
  };
}