import { createContext, useCallback, useContext, useRef, useState } from "react";
import { Icon } from "../components/common/SvgIcon.jsx";

const ModalCtx = createContext(null);

export function ModalProvider({ children }) {
  const [box, setBox] = useState(null);
  const resolveRef = useRef(null);

  const settle = useCallback((result) => {
    setBox(null);
    if (resolveRef.current) {
      resolveRef.current(result);
      resolveRef.current = null;
    }
  }, []);

  const confirm = useCallback((opts = {}) => {
    setBox({
      mode: "confirm",
      title: opts.title || "Confirmation",
      message: opts.message || "",
      yes: opts.yes || "Yes",
      no: opts.no || "No",
      danger: Boolean(opts.danger),
    });
    return new Promise((resolve) => {
      resolveRef.current = resolve;
    });
  }, []);

  const ask = useCallback((opts = {}) => {
    setBox({
      mode: "input",
      title: opts.title || "Input",
      message: opts.message || "",
      value: opts.value || "",
      yes: opts.yes || "OK",
      no: opts.no || "Cancel",
    });
    return new Promise((resolve) => {
      resolveRef.current = resolve;
    });
  }, []);

  const value = { confirm, ask };

  return (
    <ModalCtx.Provider value={value}>
      {children}
      {box ? (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) settle(null); }}>
          <div className="modal" role={box.mode === "input" ? "dialog" : "alertdialog"} aria-modal="true">
            <div className="modal-head">
              <h3 className="modal-title">{box.title}</h3>
              <button type="button" className="modal-close" aria-label="Close" onClick={() => settle(box.mode === "input" ? null : false)}>
                <Icon name="x" />
              </button>
            </div>
            {box.mode === "input" ? (
              <InputBody key={box.value} box={box} onOk={(v) => settle(v)} />
            ) : (
              <>
                <p className="modal-message">{box.message}</p>
                {box.danger ? (
                  <p className="modal-danger">This action cannot be undone and is irreversible.</p>
                ) : null}
                <div className="modal-actions">
                  <button type="button" className="btn ghost" onClick={() => settle(false)}>{box.no}</button>
                  <button type="button" className={"btn accent" + (box.danger ? " danger" : "")} onClick={() => settle(true)}>{box.yes}</button>
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}
    </ModalCtx.Provider>
  );
}

function InputBody({ box, onOk }) {
  const [value, setValue] = useState(box.value || "");
  return (
    <>
      <p className="modal-message">{box.message}</p>
      <input
        className="modal-input"
        type="text"
        value={value}
        autoFocus
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onOk(value);
          if (e.key === "Escape") onOk(null);
        }}
      />
      <div className="modal-actions">
        <button type="button" className="btn ghost" onClick={() => onOk(null)}>{box.no}</button>
        <button type="button" className="btn accent" onClick={() => onOk(value)}>{box.yes}</button>
      </div>
    </>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useModal() {
  const ctx = useContext(ModalCtx);
  if (!ctx) throw new Error("useModal must be used within ModalProvider");
  return ctx;
}