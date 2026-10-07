/**
 * Backwards-compatible public API for the UI tree.
 *
 * The registry/resolver/collectors moved to nodeRegistry.js as part of the
 * generator architecture; this module keeps every previously exported name so
 * existing consumers (utilities, FormGenerator internals) keep working without
 * changes.
 */

export {
  registerNodeType,
  getNodeRenderer,
  collectUiFieldIds,
  collectSectionFieldIds,
  collectCardFieldIds,
  isUiContainerType,
  resolveNodeKind,
  resolveUiNode,
  renderUiChildren,
} from "./nodeRegistry.js";