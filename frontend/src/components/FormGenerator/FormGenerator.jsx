import FormField from "./FormField.jsx";
import { useFormState } from "../../contexts/FormStateContext.jsx";
import { evalVisibility } from "../../utils/form/visibility.js";

/**
 * Data-driven form renderer. Iterates the active module's field store (itself
 * hydrated from form_schema.json) and maps each entry to the matching HTML
 * control, keyed by field_id. Hidden fields (field_visibility = false and
 * unsatisfied show_if / matching hide_if conditions) are skipped at render
 * time but retain their value in the store.
 */
export default function FormGenerator({ call }) {
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
        <p className="field-note">No form fields defined for this utility.</p>
      </section>
    );
  }

  return (
    <section className="panel" data-panel-title="Inputs">
      <h2 className="panel-title">Inputs</h2>
      {entries.map((entry) => (
        <FormField key={entry.schema.field_id} entry={entry} call={call} />
      ))}
    </section>
  );
}