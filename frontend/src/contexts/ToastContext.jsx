import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { setToastHandler } from "../utils/platform/toast.js";

const ToastCtx = createContext(null);

export function ToastProvider({ children, onAction }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    window.setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 300);
  }, []);

  const push = useCallback(({ message, type, ms, action }) => {
    if (!message) return;
    const id = ++idRef.current;
    setToasts((prev) => prev.concat({ id, message, type: type || "good", action: action || null }));
    window.setTimeout(() => {
      setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
      window.setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 300);
    }, ms || 4600);
  }, []);

  useEffect(() => {
    setToastHandler(push);
    return () => setToastHandler(null);
  }, [push]);

  return (
    <ToastCtx.Provider value={{ showToast: push }}>
      {children}
      {toasts.length > 0 ? (
        <div className="toast-stack">
          {toasts.map((t) => (
            <div
              key={t.id}
              className={"toast " + t.type + (t.leaving ? " out" : "") + (t.action ? " with-action" : "")}
            >
              <span className="toast-text">{t.message}</span>
              {t.action ? (
                <button
                  type="button"
                  className="toast-action"
                  onClick={() => {
                    if (onAction) onAction(t.action.kind);
                    dismiss(t.id);
                  }}
                >
                  {t.action.label}
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </ToastCtx.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}