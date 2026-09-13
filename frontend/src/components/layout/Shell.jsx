import { useCallback, useEffect, useRef, useState } from "react";
import { ThemeProvider } from "../../contexts/ThemeContext.jsx";
import { ZoomProvider, useZoom } from "../../contexts/ZoomContext.jsx";
import { ToastProvider } from "../../contexts/ToastContext.jsx";
import { ModalProvider } from "../../contexts/ModalContext.jsx";
import { showToast } from "../../utils/platform/toast.js";
import Topbar from "./Topbar.jsx";
import ZoomDropdown from "./ZoomDropdown.jsx";
import Statusbar from "./Statusbar.jsx";
import AboutModal from "./AboutModal.jsx";
import UpdateModal from "./UpdateModal.jsx";
import SettingsPanel from "../SettingsPanel.jsx";
import EasterEggPeek from "../EasterEggPeek.jsx";
import useCyanPulse from "../../hooks/useCyanPulse.js";

function AppFrame({ call, app, cpuName, goHome, onFocusTool, onEditJob, openAbout, aboutVisible, closeAbout, openSettings, settingsVisible, settingsSection, closeSettings, onCheckUpdates, children }) {
  const { zoom } = useZoom();
  const [isPeeking, setIsPeeking] = useState(false);
  const startPeek = useCallback(() => setIsPeeking(true), []);
  const stopPeek = useCallback(() => setIsPeeking(false), []);
  const hidden = isPeeking ? " content-hidden" : "";
  const frameRef = useRef(null);
  useCyanPulse(frameRef, "frame");
  return (
    <>
      <div ref={frameRef} className={"app-frame-border" + hidden} aria-hidden="true"></div>
      <Topbar call={call} app={app} goHome={goHome} onFocusTool={onFocusTool} onEditJob={onEditJob} openAbout={openAbout} openSettings={openSettings} onCheckUpdates={onCheckUpdates} hidden={isPeeking} />
      <div id="app-layout" className={isPeeking ? "content-hidden" : undefined} style={{ zoom: zoom / 100 }}>
        <main className="view">{children}</main>
      </div>
      <Statusbar call={call} cpuName={cpuName} hidden={isPeeking} />
      <ZoomDropdown hidden={isPeeking} />
      <EasterEggPeek isPeeking={isPeeking} onStartPeek={startPeek} onStopPeek={stopPeek} />
      {aboutVisible ? <AboutModal app={app} call={call} onClose={closeAbout} /> : null}
      {settingsVisible ? <SettingsPanel call={call} onClose={closeSettings} initialSection={settingsSection || undefined} /> : null}
    </>
  );
}

export default function Shell({ call, app, cpuName, goHome, onFocusTool, onEditJob, children }) {
  const [aboutVisible, setAboutVisible] = useState(false);
  const [settingsVisible, setSettingsVisible] = useState(false);
  const [settingsSection, setSettingsSection] = useState("ffmpeg");
  const [updateInfo, setUpdateInfo] = useState(null);

  const openSettings = useCallback((section) => {
    if (section) setSettingsSection(section);
    setSettingsVisible(true);
  }, []);
  const closeSettings = useCallback(() => {
    setSettingsSection("");
    setSettingsVisible(false);
  }, []);

  const runUpdateCheck = useCallback(
    async (mode = "manual") => {
      const res = await call("check_for_updates");
      if (!res || res.ok !== true) {
        if (mode === "auto") return;
        const reason = res && res.reason;
        if (reason === "internet_disabled") {
          showToast("Internet access is disabled in Settings \u2192 General.", "warn");
        } else if (reason === "no_internet") {
          showToast("No internet connection. Check your connection and try again.", "error");
        } else {
          showToast("Could not check for updates right now.", "error");
        }
        return;
      }
      if (res.update_available) {
        setUpdateInfo(res);
      } else if (mode === "manual") {
        showToast(`You're up to date on v${res.current || "current"}.`, "good");
      }
    },
    [call],
  );

  useEffect(() => {
    let cancelled = false;
    const autoCheck = async () => {
      const settings = await call("get_app_settings");
      if (cancelled) return;
      const general = (settings && settings.general) || {};
      if (!general.allow_internet || !general.check_updates_automatically) return;
      const res = await call("check_for_updates");
      if (cancelled || !res || res.ok !== true || !res.update_available) return;
      setUpdateInfo(res);
    };
    autoCheck();
    return () => {
      cancelled = true;
    };
  }, [call]);

  return (
    <ThemeProvider call={call}>
      <ZoomProvider>
<ToastProvider
            onAction={(kind) => {
              if (kind === "open-settings") openSettings("ffmpeg");
            }}
          >
            <ModalProvider>
              <AppFrame
                call={call}
                app={app}
                cpuName={cpuName}
                goHome={goHome}
                onFocusTool={onFocusTool}
                onEditJob={onEditJob}
                openAbout={() => setAboutVisible(true)}
                aboutVisible={aboutVisible}
                closeAbout={() => setAboutVisible(false)}
                openSettings={openSettings}
                settingsVisible={settingsVisible}
                settingsSection={settingsSection}
                closeSettings={closeSettings}
                onCheckUpdates={() => runUpdateCheck("manual")}
              >
                {children}
              </AppFrame>
              {updateInfo ? <UpdateModal info={updateInfo} call={call} onClose={() => setUpdateInfo(null)} /> : null}
            </ModalProvider>
          </ToastProvider>
      </ZoomProvider>
    </ThemeProvider>
  );
}