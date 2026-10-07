import { Fragment } from "react";
import EmojiText from "../common/EmojiText.jsx";
import { useFormState } from "../../contexts/FormStateContext.jsx";
import { makeUiContext } from "./uiContext.js";
import { buildLayout } from "./layout.js";
import { collectUiFieldIds, resolveUiNode } from "./nodeRegistry.js";
import FieldPanels from "./FieldPanels.jsx";

/**
 * Data-driven form orchestrator.
 *
 * Reads the active module's field store (hydrated from form_schema.json) and
 * maps fields to panels grouped by their `part` title. Container nodes — section
 * and popup — are positioned between those panels in the order the author listed
 * them in the schema and are delegated to the shared resolver
 * (SectionGenerator / PopupGenerator / FieldGenerator / ElementGenerator). A
 * field a container owns via a form_component / form_field reference is
 * excluded from automatic panel rendering while still carrying its value.
 *
 * This component intentionally stays thin: planning lives in layout.js,
 * per-node rendering lives in the generator components and nodeRegistry.js,
 * and cross-language actions live in uiActions.js.
 */
export default function FormGenerator({ call, description, onFieldBlur }) {
  const { snapshot, schema, moduleId } = useFormState();
  const sectionOwned = collectUiFieldIds(schema);
  const layout = buildLayout({ schema, snapshot, sectionOwned });
  const ctx = makeUiContext({ snapshot, call, onFieldBlur, moduleId });

  if (!layout.hasContent) {
    return (
      <section className="panel" data-panel-title="Inputs">
        <h2 className="panel-title"><EmojiText text="Inputs" /></h2>
        {description ? <p className="form-desc"><EmojiText text={description} /></p> : null}
        <p className="field-note">No form fields defined for this utility.</p>
      </section>
    );
  }

  return (
    <>
      {description ? <p className="form-desc"><EmojiText text={description} /></p> : null}
      {layout.blocks.map((block) => {
        if (block.kind === "group") {
          return (
            <FieldPanels
              key={block.title}
              orderedTitles={[block.title]}
              groups={layout.groups}
              call={call}
              onFieldBlur={onFieldBlur}
            />
          );
        }
        const node = block.node;
        const identity =
          node &&
          typeof node === "object" &&
          (node.idName || node.field_id || node.actionId);
        return (
          <Fragment key={identity || `container-${block.order}`}>
            {resolveUiNode(node, ctx)}
          </Fragment>
        );
      })}
    </>
  );
}