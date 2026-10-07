import { useCallback, useEffect, useState } from "react";
import "./styles/styles.scss";
import { usePyWebView } from "./hooks/usePyWebView.js";
import { showToast } from "./utils/platform/toast.js";
import Shell from "./components/layout/Shell.jsx";
import { ToolHeader } from "./tabs/common/components/TabChrome.jsx";
import HomeDashboard from "./tabs/HomeDashboard.jsx";
import FormTool from "./tabs/FormTool.jsx";
import UtilityErrorTab from "./tabs/UtilityErrorTab.jsx";

function ComingSoon({ tool, onBack }) {
  return (
    <div className="page">
      <div className="container">
        <ToolHeader title={tool.title} description={tool.description} onBack={onBack} />
        <div className="coming-soon">
          <div className="panel">
            <h2>Coming Soon</h2>
            <p>This utility is in the works. Check back after the next update.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const { call } = usePyWebView();
  const [app, setApp] = useState({});
  const [cpuName, setCpuName] = useState("Unknown CPU Model");
  const [tools, setTools] = useState([]);
  const [active, setActive] = useState(null);
  const [focusJobId, setFocusJobId] = useState(null);
  const [queuedEdit, setQueuedEdit] = useState(null);
  const [queueCurrent, setQueueCurrent] = useState(null);
  const [storeOpen, setStoreOpen] = useState(false);
  const [storeSearchQuery, setStoreSearchQuery] = useState("");

  // Track the currently running queue job so an already-open tool tab can
  // attach to it and keep streaming its Output Log (queue mode).
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (cancelled) return;
      try {
        const q = await call("get_queue");
        if (!cancelled && q) setQueueCurrent(q.current || null);
      } catch {
        // skip
      }
    };
    poll();
    const handle = setInterval(poll, 1000);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [call]);

  const loadDashboard = useCallback(async () => {
    const dash = await call("get_dashboard");
    if (!dash) return;
    setTools(
      Array.isArray(dash.tools)
        ? dash.tools.map((t) => ({ ...t, last_used: t.last_used || null }))
        : [],
    );
    if (dash.app) setApp(dash.app);
    if (dash.cpu_name) setCpuName(dash.cpu_name);
  }, [call]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const dash = await call("get_dashboard");
      if (cancelled || !dash) return;
      setTools(
        Array.isArray(dash.tools)
          ? dash.tools.map((t) => ({ ...t, last_used: t.last_used || null }))
          : [],
      );
      if (dash.app) setApp(dash.app);
      if (dash.cpu_name) setCpuName(dash.cpu_name);
    };
    tick();
    const onReady = () => tick();
    window.addEventListener("pywebviewready", onReady, { once: true });
    return () => {
      cancelled = true;
      window.removeEventListener("pywebviewready", onReady);
    };
  }, [call]);

  const openTool = useCallback(
    (tool, jobId) => {
      const resolved = typeof tool === "string"
        ? (tools.find((t) => t.id === tool) || { id: tool })
        : tool;
      setFocusJobId(jobId || null);
      setActive(resolved);
      setTools((prev) =>
        prev.map((t) => (t.id === resolved.id ? { ...t, last_used: Math.floor(Date.now() / 1000) } : t)),
      );
      call("open_tool", resolved.id);
    },
    [call, tools],
  );

  const goHome = useCallback(() => {
    setActive(null);
    setFocusJobId(null);
    setQueuedEdit(null);
    loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (!active) return;
    const onFocusEscape = (e) => {
      if (e.key !== "Escape") return;
      const el = document.activeElement;
      if (
        el &&
        (el.tagName === "INPUT" ||
          el.tagName === "SELECT" ||
          el.tagName === "TEXTAREA" ||
          el.isContentEditable)
      ) {
        return;
      }
      if (
        document.querySelector(
          ".modal-overlay, .about-overlay, [role='dialog'], .menu-popup, .worker-popup, .store-popup, .zoom-dropdown-panel",
        )
      ) {
        return;
      }
      goHome();
    };
    window.addEventListener("keydown", onFocusEscape);
    return () => window.removeEventListener("keydown", onFocusEscape);
  }, [active, goHome]);

  const openStore = useCallback((searchQuery = "") => {
    setStoreSearchQuery(searchQuery);
    setStoreOpen(true);
  }, []);

  const editQueuedJob = useCallback(async (jobId) => {
    let res;
    try {
      res = await call("get_queued_job", jobId);
    } catch {
      res = null;
    }
    if (!res || res.ok !== true || !res.tool) {
      showToast("Could not load the queued job.", "error");
      return;
    }
    const tool = tools.find((t) => t.id === res.tool) || { id: res.tool };
    setQueuedEdit({ jobId: res.job_id, toolId: res.tool, params: res.params || {} });
    setFocusJobId(null);
    setActive(tool);
    setTools((prev) =>
      prev.map((t) => (t.id === tool.id ? { ...t, last_used: Math.floor(Date.now() / 1000) } : t)),
    );
    call("open_tool", tool.id);
  }, [call, tools]);

  const queuedEditDone = useCallback(() => {
    setQueuedEdit(null);
    setFocusJobId(null);
  }, []);

  const toggleFavorite = useCallback(
    async (tool) => {
      const res = await call("toggle_favorite", tool.id);
      const favorite = res && typeof res.favorite === "boolean" ? res.favorite : !tool.favorite;
      setTools((prev) => prev.map((t) => (t.id === tool.id ? { ...t, favorite } : t)));
    },
    [call],
  );

  const ActiveComponent =
    active && active.has_error
      ? UtilityErrorTab
      : active && active.form_schema
        ? FormTool
        : null;

  return (
    <Shell call={call} app={app} cpuName={cpuName} goHome={goHome} onFocusTool={openTool} onEditJob={editQueuedJob} storeOpen={storeOpen} onStoreOpenChange={setStoreOpen} storeSearchQuery={storeSearchQuery}>
      {!active ? (
        <HomeDashboard tools={tools} app={app} onOpenTool={openTool} onToggleFavorite={toggleFavorite} />
      ) : ActiveComponent ? (
        <ActiveComponent
          tool={active}
          onBack={goHome}
          focusJobId={focusJobId}
          queuedEdit={queuedEdit}
          onQueuedEditDone={queuedEditDone}
          queueRunning={queueCurrent ? { tool: queueCurrent.tool, jobId: queueCurrent.job_id } : null}
          onOpenStore={openStore}
        />
      ) : (
        <ComingSoon tool={active} onBack={goHome} />
      )}
    </Shell>
  );
}