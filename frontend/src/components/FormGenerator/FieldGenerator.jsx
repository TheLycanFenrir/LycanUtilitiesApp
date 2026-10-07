import EmojiText from "../common/EmojiText.jsx";
import { useFormState } from "../../contexts/FormStateContext.jsx";
import { collectGroups } from "./layout.js";
import FieldPanels from "./FieldPanels.jsx";

/**
 * Field-only renderer (classic panels, no container interleaving).
 *
 * Standalone entry point for tools that want regular grouped panels without
 * any section/popup layout. Values and visibility come from the shared
 * form store; panels are grouped by the layout planner just like the
 * orchestrator groups them.
 */
export default function FieldGenerator({ call, onFieldBlur, description }) {
  const { snapshot } = useFormState();
  const { groups, orderedTitles } = collectGroups({ schema: undefined, snapshot, sectionOwned: undefined });

  if (orderedTitles.length === 0) {
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
      <FieldPanels orderedTitles={orderedTitles} groups={groups} call={call} onFieldBlur={onFieldBlur} />
    </>
  );
}