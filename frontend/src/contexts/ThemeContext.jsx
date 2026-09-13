import { createContext, useCallback, useContext, useEffect, useState } from "react";

const STORAGE_KEY = "lycan.ui.theme";

const ThemeCtx = createContext(null);

function readStored() {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  } catch (e) {
    return "dark";
  }
}

export function ThemeProvider({ children, call }) {
  const [theme, setTheme] = useState(readStored);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch (e) {
    }
  }, [theme]);

  const toggleTheme = useCallback(() => {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    if (call) call("set_theme", next);
  }, [call, theme]);

  return <ThemeCtx.Provider value={{ theme, toggleTheme }}>{children}</ThemeCtx.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}