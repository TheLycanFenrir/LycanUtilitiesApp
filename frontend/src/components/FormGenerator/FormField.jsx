import { useEffect, useRef } from "react";
import ColorField from "../common/ColorField.jsx";
import EmojiText from "../common/EmojiText.jsx";
import { rgbToHex } from "../../utils/color/colorMath.js";
import { dirname, dirnameWithSep, fileName } from "../../utils/paths/paths.js";
import { useFormState } from "../../contexts/FormStateContext.jsx";
import { buildFieldHtmlProps } from "./htmlProps.js";

function toDomId(fieldId) {
  return "in-" + fieldId;
}

/**
 * Resolve the effective dialog kind of a field.
 *
 * `schema.mode` may be:
 *   - a plain kind: "input" (single file), "output" (save), "folder" (directory)
 *   - a conditional description: { parts: [[fieldId, value, kind], ...], default: kind }
 *     resolved against the live store (first matching part wins).
 */
function resolveMode(schema, snapshot) {
  const raw = schema.mode || "input";
  if (typeof raw === "string") return raw;
  if (raw && Array.isArray(raw.parts)) {
    for (const [fieldId, want, kind] of raw.parts) {
      const got = (snapshot.fields[fieldId] || {}).value;
      if (String(got) === String(want)) return kind;
    }
    return raw.default || "input";
  }
  return "input";
}

function UseFocusWatcher({ schema, controlRef }) {
  const { snapshot } = useFormState();
  const lastTick = useRef(0);
  useEffect(() => {
    const tick = snapshot.focusTick;
    if (!tick.fieldId || tick.fieldId !== schema.field_id) return;
    if (tick.n === lastTick.current) return;
    lastTick.current = tick.n;
    const el = controlRef.current;
    if (el && typeof el.focus === "function") el.focus({ preventScroll: true });
    if (typeof el?.select === "function") setTimeout(() => el.select(), 0);
  }, [snapshot.focusTick, schema.field_id, controlRef]);
  return null;
}

export default function FormField({ entry, call, onFieldBlur }) {
  const { snapshot, setValue } = useFormState();
  const schema = entry.schema;
  const value = entry.value;
  const controlRef = useRef(null);
  const domId = toDomId(schema.field_id);
  const htmlProps = buildFieldHtmlProps(schema);

  const browse = async () => {
    if (!call) return;
    const mode = resolveMode(schema, snapshot);
    const fileTypes = schema.file_types ? [String(schema.file_types)] : undefined;
    const current = String(value || "");
    let result;
    try {
      if (mode === "output") {
        const name = fileName(current) || (schema.default_input ? fileName(String(schema.default_input)) : "");
        result = await call("open_dialog", "save", current ? dirnameWithSep(current) : "", name || "", false, fileTypes);
      } else if (mode === "folder") {
        const start = current && (/^[a-zA-Z]:/.test(current) || current.startsWith("/")) ? current : "";
        result = await call("open_dialog", "folder", start, "", false);
      } else {
        result = await call("open_dialog", "file", current.startsWith("/") || /^[a-zA-Z]:/.test(current) ? dirname(current) : "", "", false, fileTypes);
      }
    } catch {
      result = null;
    }
    const paths = result && result.ok !== false && Array.isArray(result.paths) ? result.paths : null;
    if (paths && paths.length) setValue(schema.field_id, paths[0]);
  };

  let control;
  switch (schema.type) {
    case "text":
      control = (
        <input
          ref={controlRef}
          {...htmlProps}
          id={domId}
          type="text"
          value={value}
          maxLength={typeof schema.max_length === "number" ? schema.max_length : undefined}
          placeholder={schema.placeholder}
          onChange={(e) => setValue(schema.field_id, e.target.value, { validate: schema.real_time_validation !== false })}
          onBlur={(e) => {
            setValue(schema.field_id, e.target.value);
            onFieldBlur?.();
          }}
        />
      );
      break;
    case "number":
      control = (
        <input
          ref={controlRef}
          {...htmlProps}
          id={domId}
          type="number"
          value={value}
          inputMode={schema.allow_decimal === false ? "numeric" : "decimal"}
          step={schema.allow_decimal === false ? (schema.step || 1) : (schema.step || "any")}
          min={schema.min}
          max={schema.max}
          placeholder={schema.placeholder}
          onChange={(e) => setValue(schema.field_id, e.target.value, { validate: schema.real_time_validation !== false })}
          onBlur={(e) => {
            setValue(schema.field_id, e.target.value);
            onFieldBlur?.();
          }}
        />
      );
      break;
    case "dropdown":
      control = (
        <select
          ref={controlRef}
          {...htmlProps}
          id={domId}
          value={value}
          onChange={(e) => setValue(schema.field_id, e.target.value)}
          onBlur={() => onFieldBlur?.()}
        >
          {(schema.pre_defined_dropdown || []).map(([optValue, label]) => (
            <option key={optValue} value={optValue}>{label}</option>
          ))}
        </select>
      );
      break;
    case "date":
      control = (
        <input
          ref={controlRef}
          {...htmlProps}
          id={domId}
          type="date"
          value={value}
          onChange={(e) => setValue(schema.field_id, e.target.value)}
          onBlur={() => onFieldBlur?.()}
        />
      );
      break;
    case "color":
      control = (
        <ColorField
          id={domId}
          value={Array.isArray(value) && value.length >= 3 ? rgbToHex(value) : String(value || "")}
          onChange={(hex) => setValue(schema.field_id, hex)}
        />
      );
      break;
    case "checkbox":
      control = (
        <div>
          <input
            ref={controlRef}
            {...htmlProps}
            id={domId}
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => setValue(schema.field_id, e.target.checked)}
          />
        </div>
      );
      break;
    case "file":
      control = (
        <div className="file-row">
          <input
            ref={controlRef}
            {...htmlProps}
            id={domId}
            type="text"
            value={value}
            placeholder={schema.placeholder}
            onChange={(e) => setValue(schema.field_id, e.target.value)}
            onBlur={() => onFieldBlur?.()}
          />
          <button type="button" className="btn" onClick={browse} disabled={!call}>
            Browse
          </button>
        </div>
      );
      break;
    default:
      control = <input id={domId} type="text" value={value} readOnly />;
  }

  const statusNote = entry.status === "invalid" ? "invalid" : entry.status === "valid" ? "valid" : entry.status;
  const className = ["field"]
    .concat(schema.classes ? schema.classes.split(/\s+/).filter(Boolean) : [])
    .concat(entry.status === "invalid" ? ["has-invalid"] : [])
    .concat(statusNote !== "idle" ? ["status-" + statusNote] : [])
    .join(" ");

  return (
    <div
      className={className}
      data-field={schema.field_id}
      data-status={statusNote}
      data-tooltip={schema.tooltip || undefined}
      title={schema.tooltip || undefined}
    >
      <label htmlFor={domId}><EmojiText text={schema.label_name || schema.field_id} />{schema.required ? <span className="req"> *</span> : null}</label>
      <UseFocusWatcher schema={schema} controlRef={controlRef} />
      {control}
      {schema.description ? <div className="field-note"><EmojiText text={schema.description} /></div> : null}
      {schema.tooltip ? <div className="field-note"><EmojiText text={schema.tooltip} /></div> : null}
    </div>
  );
}