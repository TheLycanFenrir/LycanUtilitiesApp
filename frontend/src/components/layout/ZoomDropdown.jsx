import { useEffect } from "react";
import { useZoom } from "../../contexts/ZoomContext.jsx";

export default function ZoomDropdown({ hidden }) {
  const { zoom, popup, applyZoom, resetZoom, closeZoomPopup } = useZoom();

  useEffect(() => {
    if (!popup) return;
    const onKey = (e) => {
      if (e.key === "Escape") closeZoomPopup();
    };
    const onDoc = (e) => {
      if (!e.target.closest(".zoom-control") && !e.target.closest(".zoom-dropdown-panel")) closeZoomPopup();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("click", onDoc);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("click", onDoc);
    };
  }, [popup, closeZoomPopup]);

  if (!popup) return null;

  return (
    <div
      className={"zoom-dropdown-panel open" + (hidden ? " content-hidden" : "")}
      style={{ left: popup.left + "px", top: popup.top + "px" }}
    >
      <div className="zoom-popup-head">
        <span className="zoom-popup-title">Zoom</span>
        <span className="zoom-popup-current">{zoom}%</span>
      </div>
      <input
        type="range"
        min="25"
        max="500"
        step="1"
        value={zoom}
        aria-label="Zoom percentage"
        onChange={(e) => applyZoom(e.target.value)}
      />
      <div className="zoom-popup-actions">
        <span className="zoom-popup-hint">25% - 500%</span>
        <button type="button" className="btn accent" onClick={resetZoom}>Reset Zoom</button>
      </div>
    </div>
  );
}