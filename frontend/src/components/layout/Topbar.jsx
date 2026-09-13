import { useEffect, useRef, useState } from "react";
import { Icon } from "../common/SvgIcon.jsx";
import { useTheme } from "../../contexts/ThemeContext.jsx";
import { useZoom } from "../../contexts/ZoomContext.jsx";
import { openDevTools, openExternalLink, quitApp, reloadApp, hardRefreshApp, restartApp } from "../../utils/platform/bridge.js";
import useCyanPulse from "../../hooks/useCyanPulse.js";
import WorkerDropdown from "./WorkerDropdown.jsx";

function Brand({ app, goHome }) {
  const version = app.version ? "v" + app.version : "Alpha";
  const wordRef = useRef(null);
  const utilityRef = useRef(null);
  useCyanPulse(wordRef);
  useCyanPulse(utilityRef);
  return (
    <div
      className="brand"
      role="button"
      tabIndex={0}
      title="Go to dashboard"
      onClick={goHome}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          goHome();
        }
      }}
    >
      <img src="/assets/favicon.png" alt="" className="brand-mark" />
      <span ref={wordRef} className="brand-word">Lycan</span>
      <span ref={utilityRef} className="brand-utility">Utilities</span>
      <span className="brand-version chip">{version}</span>
    </div>
  );
}

function GithubButton({ call, url }) {
  return (
    <button
      type="button"
      className="icon-btn"
      title="Open GitHub repository"
      aria-label="Open GitHub repository"
      onClick={() => openExternalLink(call, url)}
    >
      <Icon name="github" />
    </button>
  );
}

function ZoomControl() {
  const { zoom, popup, zoomIn, zoomOut, openZoomPopup, closeZoomPopup } = useZoom();
  return (
    <div className="zoom-control" role="group" aria-label="Zoom controls">
      <button type="button" className="zoom-btn" title="Zoom out" aria-label="Zoom out" onClick={zoomOut}>-</button>
      <button
        type="button"
        className="zoom-value"
        title="Open zoom options"
        aria-label="Open zoom options"
        onClick={(e) => (popup ? closeZoomPopup() : openZoomPopup(e.currentTarget.getBoundingClientRect()))}
      >
        {zoom}%
      </button>
      <button type="button" className="zoom-btn" title="Zoom in" aria-label="Zoom in" onClick={zoomIn}>+</button>
    </div>
  );
}

function ThemeSwitch() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      type="button"
      className="theme-switch"
      role="switch"
      aria-checked={theme === "dark"}
      title="Toggle theme"
      aria-label="Toggle theme"
      onClick={toggleTheme}
    >
      <span className="theme-switch-track">
        <span className="theme-opt theme-opt-sun" aria-hidden="true"><Icon name="sun" /></span>
        <span className="theme-thumb" aria-hidden="true"></span>
        <span className="theme-opt theme-opt-moon" aria-hidden="true"><Icon name="moon" /></span>
      </span>
    </button>
  );
}

const MENU_ITEMS = [
  { action: "console", label: "Console Info" },
  { action: "about", label: "About Me" },
  { action: "apprepo", label: "Lycan Utilities Repository" },
  { action: "repos", label: "GitHub Repositories" },
  { action: "profile", label: "GitHub TheLycanFenrir Profile" },
];

const APP_ITEMS = [
  { action: "refresh", label: "Refresh" },
  { action: "hardrefresh", label: "Hard Refresh" },
  { action: "restart", label: "Restart App" },
];

function Menu({ call, app, openAbout, openSettings, onCheckUpdates }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  const profileBaseUrl = (app.github_url || "https://github.com/TheLycanFenrir").replace(/\/+$/, "");

  const act = (action) => {
    setOpen(false);
    switch (action) {
      case "console":
        openDevTools(call);
        break;
      case "about":
        openAbout();
        break;
      case "refresh":
        reloadApp();
        break;
      case "hardrefresh":
        hardRefreshApp();
        break;
      case "restart":
        restartApp(call);
        break;
      case "checkupdates":
        onCheckUpdates();
        break;
      case "apprepo":
        openExternalLink(call, "https://github.com/TheLycanFenrir/LycanUtilitiesApp");
        break;
      case "repos":
        openExternalLink(call, profileBaseUrl + "?tab=repositories");
        break;
      case "profile":
        openExternalLink(call, profileBaseUrl);
        break;
      case "quit":
        quitApp(call);
        break;
      default:
        break;
    }
  };

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("click", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="menu-wrap" ref={wrapRef}>
      <button
        type="button"
        className="icon-btn"
        title="Menu"
        aria-label="Open menu"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <svg className="menu-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M4 6h16M4 12h16M4 18h16"></path>
        </svg>
      </button>
      {open ? (
        <div className="menu-popup">
          <button
            type="button"
            className="menu-item"
            onClick={() => {
              setOpen(false);
              openSettings();
            }}
          >
            <span className="menu-label">Settings</span>
          </button>
          <div className="menu-sep" role="separator"></div>
          {APP_ITEMS.map((item) => (
            <button key={item.action} type="button" className="menu-item" onClick={() => act(item.action)}>
              {item.label}
            </button>
          ))}
          <div className="menu-sep" role="separator"></div>
          <button type="button" className="menu-item" onClick={() => act("checkupdates")}>Check Updates</button>
          <div className="menu-sep" role="separator"></div>
          {MENU_ITEMS.map((item) => (
            <button key={item.action} type="button" className="menu-item" onClick={() => act(item.action)}>
              {item.label}
            </button>
          ))}
          <div className="menu-sep" role="separator"></div>
          <button type="button" className="menu-item danger" onClick={() => act("quit")}>Quit App</button>
        </div>
      ) : null}
    </div>
  );
}

export default function Topbar({ call, app, goHome, openAbout, openSettings, onCheckUpdates, onFocusTool, onEditJob, hidden }) {
  return (
    <header className={"topbar" + (hidden ? " content-hidden" : "")}>
      <Brand app={app} goHome={goHome} />
      <div className="topbar-right">
        <WorkerDropdown call={call} onFocusTool={onFocusTool} onEditJob={onEditJob} />
        <GithubButton call={call} url={app.github_url || "https://github.com/TheLycanFenrir"} />
        <ZoomControl />
        <ThemeSwitch />
        <Menu call={call} app={app} openAbout={openAbout} openSettings={openSettings} onCheckUpdates={onCheckUpdates} />
      </div>
    </header>
  );
}