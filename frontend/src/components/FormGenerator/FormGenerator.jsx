import FormField from "./FormField.jsx";
import { useFormState } from "../../contexts/FormStateContext.jsx";
import { evalVisibility } from "../../utils/form/visibility.js";

/**
 * Data-driven form renderer. Iterates the active module's field store (itself
 * hydrated from form_schema.json) and maps each entry to the matching HTML
 * control, keyed by field_id. Fields are grouped into panels by their `part`
 * title (form splitting); a field without a part falls back to the default
 * "Inputs" panel. Hidden fields (field_visibility = false and unsatisfied
 * show_if / matching hide_if conditions) are skipped at render time but retain
 * their value in the store.
 */
export default function FormGenerator({ call, description }) {
  const { snapshot } = useFormState();
  const entries = Object.values(snapshot.fields).filter(
    (entry) =>
      entry &&
      entry.schema &&
      entry.visible !== false &&
      (entry.schema.show_if == null || evalVisibility(entry.schema.show_if, snapshot)) &&
      (entry.schema.hide_if == null || !evalVisibility(entry.schema.hide_if, snapshot)),
  );

  if (entries.length === 0) {
    return (
      <section className="panel" data-panel-title="Inputs">
        <h2 className="panel-title">Inputs</h2>
        {description ? <p className="form-desc">{description}</p> : null}
        <p className="field-note">No form fields defined for this utility.</p>
      </section>
    );
  }

  const groups = [];
  const byPart = new Map();
  for (const entry of entries) {
    const part = typeof entry.schema.part === "string" && entry.schema.part.trim() ? entry.schema.part.trim() : null;
    const key = part || "__default__";
    if (!byPart.has(key)) {
      byPart.set(key, []);
      groups.push({ key, title: part || "Inputs" });
    }
    byPart.get(key).push(entry);
  }

  return (
    <>
      {description ? <p className="form-desc">{description}</p> : null}
      {groups.map(({ key, title }) => (
        <section key={key} className="panel" data-panel-title={title}>
          <h2 className="panel-title">{title}</h2>
          {byPart.get(key).map((entry) => (
            <FormField key={entry.schema.field_id} entry={entry} call={call} />
          ))}
        </section>
      ))}
    </>
  );
}