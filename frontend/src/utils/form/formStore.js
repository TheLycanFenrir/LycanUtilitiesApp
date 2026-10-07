// External form-state store plus the frontend half of the cross-language
// interop bridge. React reads this store with useSyncExternalStore while the
// backend (Lua scripts / Python hooks) drives it through the global
// `window.__lycanForm` escape hatch, so runtime signals can mutate the active
// form without any component coupling.

import { invokeUiAction } from "../../components/FormGenerator/uiActions.js";

const listeners = new Set();
let fields = {}; // fieldId -> { schema, value, status, visible }
let focusTick = { fieldId: null, n: 0 };
let moduleId = null;
let currentSnapshot = { fields, focusTick };

const CONTAINER_TYPES = new Set(["section", "popup"]);
function isContainerType(type) {
  return typeof type === "string" && CONTAINER_TYPES.has(type);
}

function emit() {
  currentSnapshot = { fields, focusTick };
  for (const fn of listeners) fn();
}

export function subscribeForm(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getFormSnapshot() {
  return currentSnapshot;
}

export function getActiveModuleId() {
  return moduleId;
}

function buildEntry(schema) {
  let value = "default_input" in schema ? schema.default_input : "";
  if (schema.type === "checkbox") {
    value = Boolean(schema.default_input);
  }
  return {
    schema,
    value,
    status: schema.field_status || "idle",
    visible: schema.field_visibility !== false,
  };
}

export function initForm(id, schemaFields) {
  moduleId = id;
  const next = {};
  for (const schema of schemaFields || []) {
    // Card / section / popup entries are layout containers rendered by the
    // generator tree; they never hold a value so they must not enter the field
    // store (which would pollute getAllValues() / job parameters).
    if (schema && schema.field_id && !isContainerType(schema.type)) next[schema.field_id] = buildEntry(schema);
  }
  fields = next;
  focusTick = { fieldId: null, n: 0 };
  emit();
}

export function clearForm() {
  fields = {};
  focusTick = { fieldId: null, n: 0 };
  moduleId = null;
  emit();
}

export function getFieldValue(id) {
  const entry = fields[id];
  return entry ? entry.value : undefined;
}

function applyRegex(text, spec) {
  let pattern = spec;
  let replacement = "";
  if (spec && typeof spec === "object") {
    pattern = spec.pattern;
    replacement = spec.replacement ?? "";
  }
  if (!pattern) return text;
  try {
    return String(text).replace(new RegExp(pattern, "g"), replacement);
  } catch {
    return text;
  }
}

function normalizeValue(schema, value) {
  if (schema.type === "number") {
    if (value === "" || value === null || value === undefined) return "";
    const num = Number(value);
    if (Number.isNaN(num)) return value;
    return schema.allow_decimal === false ? Math.trunc(num) : num;
  }
  if (schema.type === "checkbox") return Boolean(value);
  if (typeof value === "string") {
    if (schema.type === "text" && typeof schema.max_length === "number") {
      return value.slice(0, schema.max_length);
    }
    return value;
  }
  return value;
}

function validateEntry(entry, value) {
  const schema = entry.schema;
  if (value === "" || value === null || value === undefined) {
    return schema.required ? "invalid" : "valid";
  }
  if (schema.enable_validation === false && !schema.regex_validation) return "valid";
  const str = typeof value === "string" ? value : String(value);
  if (schema.regex_validation) {
    try {
      if (!new RegExp(schema.regex_validation).test(str)) return "invalid";
    } catch {
      return "valid";
    }
  }
  if (schema.type === "number") {
    const num = Number(str);
    if (Number.isNaN(num)) return "invalid";
    if (typeof schema.min === "number" && num < schema.min) return "invalid";
    if (typeof schema.max === "number" && num > schema.max) return "invalid";
  }
  if (schema.type === "text") {
    if (typeof schema.min_length === "number" && str.length < schema.min_length) return "invalid";
  }
  return "valid";
}

export function setFieldValue(id, value, opts = {}) {
  const entry = fields[id];
  if (!entry) return false;
  let val = value;
  if (typeof val === "string" && entry.schema.regex_sanitization) {
    val = applyRegex(val, entry.schema.regex_sanitization);
  }
  if (entry.schema.type === "number" && entry.schema.force_clamp && val !== "" && val != null) {
    const num = Number(val);
    if (!Number.isNaN(num)) {
      if (typeof entry.schema.min === "number") val = Math.max(entry.schema.min, num);
      if (typeof entry.schema.max === "number") val = Math.min(entry.schema.max, num);
    }
  }
  entry.value = normalizeValue(entry.schema, val);
  if (opts.validate !== false && entry.schema.enable_validation !== false) {
    entry.status = validateEntry(entry, entry.value);
  }
  emit();
  return true;
}

export function getAllValues() {
  const out = {};
  for (const [id, entry] of Object.entries(fields)) out[id] = entry.value;
  return out;
}

export function setAllValues(data) {
  data = data || {};
  for (const [id, value] of Object.entries(data)) {
    if (fields[id]) {
      setFieldValue(id, value);
    } else {
      fields[id] = buildEntry({ field_id: id, type: "text", label_name: id, default_input: value });
    }
  }
  emit();
  return true;
}

export function resetDefaults() {
  for (const entry of Object.values(fields)) {
    entry.value = 'default_input' in entry.schema ? entry.schema.default_input : (entry.schema.type === "checkbox" ? false : "");
    entry.status = entry.schema.field_status || "idle";
  }
  emit();
  return true;
}

export function addField(schemaJsonOrObj) {
  let schema = schemaJsonOrObj;
  if (typeof schemaJsonOrObj === "string") {
    try {
      schema = JSON.parse(schemaJsonOrObj);
    } catch {
      return false;
    }
  }
  if (!schema || typeof schema !== "object" || !schema.field_id) return false;
  if (fields[schema.field_id]) return false;
  fields[schema.field_id] = buildEntry(schema);
  emit();
  return true;
}

export function deleteField(id) {
  if (!fields[id]) return false;
  delete fields[id];
  emit();
  return true;
}

export function hideField(id) {
  if (!fields[id]) return false;
  fields[id].visible = false;
  emit();
  return true;
}

export function unhideField(id) {
  if (!fields[id]) return false;
  fields[id].visible = true;
  emit();
  return true;
}

export function setFocus(id) {
  if (!fields[id]) return false;
  focusTick = { fieldId: id, n: focusTick.n + 1 };
  emit();
  return true;
}

export function setFieldStatus(id, status) {
  if (!fields[id]) return false;
  fields[id].status = String(status || "idle");
  emit();
  return true;
}

export function registerGlobalBridge() {
  if (typeof window === "undefined" || window.__lycanForm) return;
  const ui = { call: null, moduleId: () => moduleId };
  window.__lycanForm = {
    get_form_data: (field_id) => getFieldValue(field_id) ?? null,
    set_form_data: (field_id, value) => setFieldValue(field_id, value),
    get_all_form_data: () => getAllValues(),
    set_all_form_data: (data_table) => setAllValues(data_table || {}),
    add_field: (field_schema_json) => addField(field_schema_json),
    delete_field: (field_id) => deleteField(field_id),
    hide_field: (field_id) => hideField(field_id),
    unhide_field: (field_id) => unhideField(field_id),
    set_focus: (field_id) => setFocus(field_id),
    set_field_status: (field_id, status) => setFieldStatus(field_id, status),
    invoke_ui_action: (action_id, params) => invokeUiAction(action_id, params, ui),
  };
}