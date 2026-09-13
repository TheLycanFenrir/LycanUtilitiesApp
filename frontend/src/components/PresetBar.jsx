import { useCallback, useEffect, useState } from "react";
import { useModal } from "../contexts/ModalContext.jsx";
import { showToast } from "../utils/platform/toast.js";

export default function PresetBar({ tool, call, collect, apply, reset }) {
  const { ask, confirm } = useModal();
  const [presets, setPresets] = useState({});
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const data = await call("get_presets", tool.id);
    setPresets(data && typeof data === "object" ? data : {});
  }, [call, tool.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSelect = (e) => {
    const name = e.target.value;
    setSelected(name);
    const model = presets[name];
    if (name && model) {
      apply(model);
      showToast("Loaded preset '" + name + "'.");
    }
  };

  const handleSave = async () => {
    if (busy) return;
    const raw = await ask({
      title: "Save '" + tool.title + "' as preset",
      message: "Name for the preset to store the current settings:",
      value: selected || "",
    });
    if (raw == null) return;
    const name = String(raw || "").trim();
    if (!name) return;
    setBusy(true);
    try {
      const unique = await call("unique_preset_name", tool.id, name);
      const finalName = unique && unique.name ? unique.name : name;
      const next = { ...presets, [finalName]: collect() };
      await call("save_presets", tool.id, next);
      setPresets(next);
      setSelected(finalName);
      showToast("Preset saved as '" + finalName + "'.");
    } finally {
      setBusy(false);
    }
  };

  const handleReset = () => {
    setSelected("");
    if (reset) reset();
  };

  const handleDelete = async () => {
    if (!selected || busy) return;
    const ok = await confirm({
      title: "Delete preset",
      message: "Delete preset '" + selected + "'?",
      yes: "Delete",
      no: "Cancel",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await call("delete_preset", tool.id, selected);
      const next = { ...presets };
      delete next[selected];
      setPresets(next);
      setSelected("");
      showToast("Preset deleted.", "warn");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="preset-bar">
      <select className="preset-select" value={selected} onChange={handleSelect}>
        <option value="">— Presets —</option>
        {Object.keys(presets).map((name) => (
          <option key={name} value={name}>{name}</option>
        ))}
      </select>
      <button type="button" className="btn" onClick={handleSave} disabled={busy}>
        Save As...
      </button>
      <button type="button" className="btn" onClick={handleReset}>
        ↺ Reset Fields
      </button>
      <button type="button" className="btn danger" onClick={handleDelete} disabled={busy || !selected}>
        ✕ Delete
      </button>
    </div>
  );
}