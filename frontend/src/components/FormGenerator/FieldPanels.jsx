import FormField from "./FormField.jsx";
import EmojiText from "../common/EmojiText.jsx";

/**
 * Presentational field panels. Renders each panel group (a `part`-titled
 * `<section class="panel">`) with its member FormFields. Pure/presentational:
 * grouping and ordering come from the layout planner — this component only
 * maps a pre-computed title order onto DOM.
 */
export default function FieldPanels({ orderedTitles, groups, call, onFieldBlur }) {
  if (!orderedTitles || orderedTitles.length === 0) return null;
  return orderedTitles.map((title) => {
    const group = groups.get(title);
    if (!group) return null;
    return (
      <section key={title} className="panel" data-panel-title={title}>
        <h2 className="panel-title"><EmojiText text={title} /></h2>
        {group.entries.map((entry) => (
          <FormField
            key={entry.schema.field_id}
            entry={entry}
            call={call}
            onFieldBlur={onFieldBlur}
          />
        ))}
      </section>
    );
  });
}