import { useState } from "react";
import ColorPickerModal from "./ColorPickerModal.jsx";
import { isHexColor } from "../../utils/color/colorMath.js";

export default function ColorField({ id, value = "#000000", onChange }) {
  const [open, setOpen] = useState(false);
  const color = isHexColor(value) ? String(value).toLowerCase() : "#000000";

  return (
    <>
      <button type="button" id={id} className="color-swatch-btn" onClick={() => setOpen(true)}>
        <span className="color-swatch-btn-box" style={{ background: color }} />
        <span className="color-swatch-btn-hex">{color}</span>
      </button>
      {open && (
        <ColorPickerModal
          initial={color}
          onCommit={(hex) => {
            onChange(hex);
            setOpen(false);
          }}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}