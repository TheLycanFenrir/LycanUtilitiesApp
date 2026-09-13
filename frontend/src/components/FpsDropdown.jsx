import { useId } from "react";

export const FPS_STANDARD = [12, 15, 24, 25, 30, 50, 60, 120, 144];
export const FPS_BROADCAST = [23.976, 29.97, 47.952, 59.94, 119.88];
export const FPS_PRESETS = FPS_STANDARD.concat(FPS_BROADCAST);

function normalize(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(String(value).trim());
  return Number.isFinite(n) && n > 0 ? String(n) : null;
}

export default function FpsDropdown({ id, value = "30", onChange }) {
  const autoId = useId();
  const selectId = id || ("fps-" + autoId);
  const current = normalize(value);
  const preset = FPS_PRESETS.find((fps) => normalize(fps) === current);
  const selected = preset != null ? String(preset) : "";

  return (
    <span className="fps-wrap">
      <select
        id={selectId}
        className="fps-dropdown"
        value={selected}
        onChange={(e) => {
          if (onChange && e.target.value) onChange(e.target.value);
        }}
        title="Pick a predefined frames-per-second rate"
      >
        {preset == null && (
          <option value="" disabled>Presets…</option>
        )}
        <optgroup label="Standard">
          {FPS_STANDARD.map((fps) => (
            <option key={fps} value={String(fps)}>{fps}</option>
          ))}
        </optgroup>
        <optgroup label="Broadcast &amp; Decimal">
          {FPS_BROADCAST.map((fps) => (
            <option key={fps} value={String(fps)}>{fps}</option>
          ))}
        </optgroup>
      </select>
    </span>
  );
}