import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "../common/SvgIcon.jsx";
import styles from "./PythonLibraries.module.scss";
import panelStyles from "../SettingsPanel.module.scss";
import { Row, SettingsHead } from "./SettingsBits.jsx";
import { highlight } from "./highlight.jsx";
import pythonMark from "../../assets/icons/python.svg";

const PER_PAGE = 12;

const SECURITY_WARNING =
  "Security: installing or updating a third-party package downloads and runs code from an external source (PyPI). That code executes with the app's permissions inside your local Python environment and may access files and run programs on this system. Only continue if you trust the package and its maintainer.";

function reasonText(reason) {
  const map = {
    internet_disabled: "Internet access is disabled (General settings).",
    confirmation_required: "Confirmation was required but not provided.",
    core_package: "This package is required by the app and cannot be uninstalled.",
    invalid_name: "Invalid package name.",
    pypi_unavailable: "The PyPI index could not be downloaded. Try again later.",
    pypi_search_cache_unavailable: "The PyPI search engine isn't installed in this environment.",
    timeout: "The operation timed out.",
  };
  return map[reason] || reason || "Operation failed.";
}

function vulnSummary(affected) {
  return (affected || [])
    .map((a) => {
      const head =
        "• " + a.name + (a.version ? " " + a.version : "") +
        " — " + a.count + " known vulnerability" + (a.count === 1 ? "" : "ies");
      const ids = (a.ids || []).slice(0, 4).join(", ");
      const fix = (a.fix_versions || []).join(", ");
      const extra = [];
      if (ids) extra.push("IDs: " + ids);
      if (fix) extra.push("fixed in: " + fix);
      return extra.length ? head + " (" + extra.join("; ") + ")" : head;
    })
    .join("\n");
}

export default function PythonLibrariesSection({ call, python = {}, update, general = {}, confirm, showToast, q }) {
  const localOnly = Boolean(python.local_only);
  const allowInternet = Boolean(general.allow_internet);

  const [data, setData] = useState(null);
  const [loadBusy, setLoadBusy] = useState(true);

  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [indexBusy, setIndexBusy] = useState(false);
  const [scanBusy, setScanBusy] = useState(false);

  const [busy, setBusy] = useState({});
  const [toolBusy, setToolBusy] = useState("");
  const [progress, setProgress] = useState(null);
  const aliveRef = useRef(true);
  const seededRef = useRef(false);
  const pollRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      if (!aliveRef.current) {
        stopPolling();
        return;
      }
      const res = await call("get_pypi_progress");
      if (!aliveRef.current) return;
      const progress = res && res.ok !== false ? res.progress : null;
      if (progress) {
        setProgress(progress);
        if (!progress.active) stopPolling();
      }
    }, 250);
  }, [call, stopPolling]);

  const beginOp = useCallback(() => startPolling(), [startPolling]);
  const endOp = useCallback(() => {
    stopPolling();
    setProgress(null);
  }, [stopPolling]);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      stopPolling();
    };
  }, [stopPolling]);

  const runSearch = useCallback(
    async (q2, p, force) => {
      setSearchBusy(true);
      setSearchError("");
      const res = await call("pypi_search", q2, p, PER_PAGE, Boolean(force));
      if (!aliveRef.current) return;
      setSearchBusy(false);
      if (!res) {
        setSearchError("Search is unavailable (bridge not connected).");
        return;
      }
      if (res.ok) {
        setSearch(res);
        setPage(res.page || p);
      } else {
        setSearchError(reasonText(res.detail));
      }
    },
    [call],
  );

  const loadEnv = useCallback(
    async (force) => {
      const res = await call("get_python_libraries", Boolean(force));
      if (!aliveRef.current) return;
      if (res && res.ok) {
        const env = res.environment;
        if (!seededRef.current) {
          seededRef.current = true;
          const restored = String(env.state_query || "");
          const restoredPage = Math.max(1, parseInt(env.state_page, 10) || 1);
          if (restored) {
            setDraft(restored);
            setQuery(restored);
            setPage(restoredPage);
            runSearch(restored, restoredPage, false);
          }
        }
      }
      setData(res && res.ok ? res : null);
      setLoadBusy(false);
    },
    [call, runSearch],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadEnv(false);
  }, [loadEnv]);

  const refreshAfterOp = useCallback(() => {
    loadEnv(true);
    if (query) runSearch(query, page, true);
  }, [loadEnv, query, page, runSearch]);

  const submitSearch = (e) => {
    e.preventDefault();
    const trimmed = draft.trim();
    setQuery(trimmed);
    if (!trimmed) {
      setSearch(null);
      return;
    }
    runSearch(trimmed, 1, false);
  };

  const rescanVulns = async () => {
    setScanBusy(true);
    const res = await call("pypi_audit", true);
    setScanBusy(false);
    if (res && res.ok) {
      showToast({
        message: res.total
          ? "Vulnerability scan: " + res.total + " known issue" + (res.total === 1 ? "" : "s") + " found in " + res.affected.length + " package" + (res.affected.length === 1 ? "" : "s") + "."
          : "Vulnerability scan: no known issues detected.",
        type: res.total ? "warn" : "good",
      });
    } else {
      const why =
        res && res.state === "offline"
          ? "Internet access is disabled."
          : res && res.state === "unavailable"
            ? "pip-audit is not installed in this environment."
            : res && res.state === "failed"
              ? "The advisory database is unreachable."
              : "The vulnerability scan failed.";
      showToast({ message: "Vulnerability scan failed: " + why, type: "warn" });
    }
    loadEnv(true);
    if (query) runSearch(query, page, true);
  };

  const refreshIndex = async () => {
    setIndexBusy(true);
    const res = await call("refresh_pypi_index", true);
    setIndexBusy(false);
    if (res && res.ok) {
      showToast({ message: "PyPI package index refreshed (" + res.total + " packages).", type: "good" });
      if (query) runSearch(query, page, true);
    } else {
      showToast({ message: "PyPI index refresh failed: " + reasonText(res && res.detail), type: "warn" });
    }
  };

  const setOp = (key, on) => {
    setBusy((prev) => {
      const next = { ...prev };
      if (on) next[key] = true;
      else delete next[key];
      return next;
    });
  };
  const busyKey = (name, op) => name + "|" + op;
  const isBusy = (name) => Boolean(busy[name + "|install"] || busy[name + "|update"] || busy[name + "|uninstall"]);
  const targetLabel = localOnly ? "Local project environment (.venv)" : "Global Python (shared)";

  const confirmInstall = (item, isUpdate) => {
    const action = isUpdate ? "Update" : "Install";
    return confirm({
      title: action + " “" + item.name + "”?",
      message:
        "Action: " + action + "\n" +
        "Package: " + item.name + "\n" +
        "Version: " + (item.version || "latest") + (isUpdate && item.installed_version ? "  (installed " + item.installed_version + ")" : "") + "\n" +
        "Target environment: " + targetLabel + "\n\n" +
        SECURITY_WARNING,
      yes: "Continue",
      no: "Cancel",
    });
  };

  const runPipInstall = async (name, isUpdate, batch, done) => {
    const scope = localOnly ? "local" : "global";
    const attempt = async (ack) => call("pypi_install", name, scope, isUpdate, true, batch, done, ack);
    const res = await attempt(false);
    if (!res) return null;
    if (res.ok || res.code !== "vulnerabilities_found") return res;
    const proceed = await confirm({
      title: "Vulnerabilities found in “" + name + "”",
      message:
        "The pre-install security scan (pip-audit) found " + res.total + " known vulnerability" + (res.total === 1 ? "" : "ies") + " in “" + name + "”.\n\n" +
        vulnSummary(res.affected) +
        "\n\nDo you still want to install this package?",
      yes: "Proceed Anyway",
      no: "Cancel",
    });
    if (!proceed) return { cancelled: true };
    const sure = await confirm({
      title: "Are you sure?",
      message:
        "Installing a package with known vulnerabilities can expose your system, your files and your network to risk. The security scan will keep flagging it until a fixed version is released.\n\nAre you really sure you want to install “" + name + "” anyway?",
      yes: "Yes, install anyway",
      no: "No, cancel",
      danger: true,
    });
    if (!sure) return { cancelled: true };
    return attempt(true);
  };

  const runInstall = async (item, op, batch, done) => {
    const name = item.name;
    const isUpdate = op === "update";
    const key = busyKey(name, isUpdate ? "update" : "install");
    const ok = await confirmInstall(item, isUpdate);
    if (!ok) return;
    setOp(key, true);
    beginOp();
    const res = await runPipInstall(name, isUpdate, batch, done);
    endOp();
    setOp(key, false);
    if (res && res.cancelled) return;
    if (res && res.ok) {
      showToast({
        message: (isUpdate ? "Updated " : "Installed ") + name + (res.scope === "global" ? " in the shared Python environment." : " in the local environment."),
        type: "good",
      });
    } else {
      showToast({ message: "Could not " + (isUpdate ? "update " : "install ") + name + ": " + reasonText(res && res.detail), type: "warn" });
    }
    refreshAfterOp();
  };

  const runUninstall = async (item) => {
    const name = item.name;
    const key = busyKey(name, "uninstall");
    const ok = await confirm({
      title: "Uninstall “" + name + "”?",
      message:
        "Action: Uninstall\n" +
        "Package: " + name + "\n" +
        "Installed version: " + (item.installed_version || "unknown") + "\n" +
        "Target environment: " + targetLabel + "\n\n" +
        "This removes the package from the selected environment. Uninstalling is irreversible within this manager.",
      yes: "Uninstall",
      no: "Cancel",
      danger: true,
    });
    if (!ok) return;
    setOp(key, true);
    beginOp();
    const res = await call("pypi_uninstall", name, localOnly ? "local" : "global", true, 1, 0);
    endOp();
    setOp(key, false);
    if (res && res.ok) {
      showToast({ message: "Uninstalled " + name + ".", type: "good" });
    } else {
      showToast({ message: "Could not uninstall " + name + ": " + reasonText(res && res.detail), type: "warn" });
    }
    refreshAfterOp();
  };

  const installMissing = async (tool) => {
    const todo = tool.requirements.filter((r) => r.state !== "installed");
    if (!todo.length) return;
    const ok = await confirm({
      title: "Install requirements for “" + tool.title + "”?",
      message:
        "Action: Install\n" +
        "Packages: " + todo.map((r) => r.name + (r.state === "outdated" ? " (update)" : "")).join(", ") + "\n" +
        "Target environment: " + targetLabel + "\n\n" +
        SECURITY_WARNING,
      yes: "Continue",
      no: "Cancel",
    });
    if (!ok) return;
    setToolBusy(tool.id);
    setBusy((prev) => ({ ...prev, bulk: true }));
    beginOp();
    let okCount = 0;
    for (let i = 0; i < todo.length; i += 1) {
      const req = todo[i];
      const res = await runPipInstall(req.name, req.state === "outdated", todo.length, i);
      if (res && res.ok) okCount += 1;
    }
    endOp();
    setBusy((prev) => {
      const next = { ...prev };
      delete next.bulk;
      return next;
    });
    setToolBusy("");
    if (okCount) {
      showToast({ message: "Installed " + okCount + "/" + todo.length + " requirement(s) for “" + tool.title + "”.", type: "good" });
    } else {
      showToast({ message: "Could not install any requirements for “" + tool.title + "”.", type: "warn" });
    }
    refreshAfterOp();
  };

  const env = (data && data.environment) || {};
  const utilities = (data && data.utilities) || [];
  const scopeHint = localOnly
    ? "New installs go into the app's virtual environment (" + (env.executable || "python") + "), so imported packages are available immediately and nothing leaks outside the app."
    : "WARNING: installs target the shared base/system Python (" + (env.base_executable || "python") + "). This environment is shared with other programs.";

  const chipClass = (state) =>
    state === "installed" ? styles.chipOk : state === "outdated" ? styles.chipWarn : styles.chipBad;

  const progressActive = progress && progress.active;
  const progressBatch = (progress && (progress.batch_total || 1)) || 1;
  const progressFraction = Math.min(1, ((progress && progress.pct) || 0) / 100);
  const progressPct =
    progressBatch > 1
      ? Math.round(((Math.min(progress.batch_done || 0, progressBatch) + progressFraction) / progressBatch) * 100)
      : (progress && progress.pct) || 0;
  const progressDone =
    progress && Math.min((progress.batch_done || 0) + (progress.phase === "done" ? 1 : 0), progressBatch);
  const progressTitle = progress
    ? (progress.op === "uninstall"
        ? "Uninstalling "
        : progress.op === "update"
          ? "Updating "
          : "Installing ") + progress.name
    : "";

  return (
    <section className={panelStyles.section}>
      <SettingsHead
        q={q}
        title="Python Libraries"
        blurb="Manage the Python packages the utilities depend on. Search PyPI, install into the app's local Python, track per-tool requirements and refresh the package index."
      />

      <div className={styles.notice}>
        <Icon name="exclamation-triangle" />
        <span>{highlight(SECURITY_WARNING, q)}</span>
      </div>

      <Row label="Install scope" q={q} hint={scopeHint}>
        <label className={panelStyles.checkRow}>
          <input
            type="checkbox"
            checked={localOnly}
            onChange={(e) => update("python", { local_only: e.target.checked })}
          />
          <span>{highlight("Put installed Python libraries that only for local (Recommended)", q)}</span>
        </label>
      </Row>

      {!allowInternet ? (
        <div className={styles.banner}>
          <Icon name="exclamation-triangle" />
          <span>
            {highlight("PyPI access is disabled. Enable “Internet access” under General to install or search packages.", q)}
          </span>
        </div>
      ) : null}

      {progressActive ? (
        <div className={styles.progressBox}>
          <div className={styles.progressTop}>
            <span className={styles.progressTitle}>{progressTitle}</span>
            {progressBatch > 1 ? (
              <span className={styles.progressCount}>
                package {Math.min(progressDone, progressBatch)}/{progressBatch}
              </span>
            ) : null}
            <span className={styles.progressPct}>{progressPct}%</span>
          </div>
          <div className={styles.progressBar}>
            <span style={{ width: progressPct + "%" }} />
          </div>
          {progress.status ? <div className={styles.progressStatus}>{progress.status}</div> : null}
        </div>
      ) : null}

      {loadBusy ? (
        <div className={styles.empty}>Loading Python environment…</div>
      ) : (
        <div className={styles.envBox}>
          <div className={styles.envGrid}>
            <span className={styles.envKey}>Python</span>
            <span className={styles.envVal}>{env.python_version || "unknown"}</span>
            <span className={styles.envKey}>Environment</span>
            <span className={styles.envVal}>{env.in_venv ? "Virtual (app local)" : "System (shared)"}</span>
            <span className={styles.envKey}>Interpreter</span>
            <span className={styles.envMono}>{env.executable || "unknown"}</span>
            {env.in_venv ? (
              <>
                <span className={styles.envKey}>Base Python</span>
                <span className={styles.envMono}>{env.base_executable || "unknown"}</span>
              </>
            ) : null}
            <span className={styles.envKey}>Installed</span>
            <span className={styles.envVal}>{env.installed_count == null ? "?" : env.installed_count} packages · pip {env.pip_available ? <span className={styles.envOk}>available</span> : <span className={styles.envWarn}>missing</span>}</span>
            <span className={styles.envKey}>Search index</span>
            <span className={styles.envVal}>
              {env.search_engine === "pypi-search-caching"
                ? env.search_index_size
                  ? env.search_index_size + " packages" + (env.index_fresh ? "" : " (cached)") + (env.index_stale_recovered ? " · stale, refresh to update" : "")
                  : "cache not built yet"
                : "search engine unavailable"}
            </span>
            <span className={styles.envKey}>Vulnerability scan</span>
            <span className={styles.envVal}>
              {env.vuln_scan_state === "ok"
                ? env.vuln_total > 0
                  ? <span className={styles.envBad}>auto-scan · {env.vuln_total} vulnerability{env.vuln_total === 1 ? "" : "ies"} in {env.vuln_affected} package{env.vuln_affected === 1 ? "" : "s"}{env.vuln_fetched_at ? " · " + env.vuln_fetched_at : ""}</span>
                  : <span className={styles.envOk}>auto-scan · no known vulnerabilities detected</span>
                : env.vuln_scan_state === "offline"
                  ? <span className={styles.envWarn}>auto-scan skipped — internet access is off</span>
                  : env.vuln_scan_state === "unavailable"
                    ? <span className={styles.envWarn}>auto-scan unavailable — pip-audit not installed</span>
                    : env.vuln_scan_state === "failed"
                      ? <span className={styles.envWarn}>auto-scan failed — advisory database unreachable</span>
                      : <span className={styles.envWarn}>auto-scan pending…</span>}
            </span>
            <span className={styles.envKey}>Protected</span>
            <span className={styles.envVal}>{Array.isArray(env.core_packages) ? env.core_packages.join(", ") : ""}</span>
          </div>
          <div className={styles.scanRow}>
            <button type="button" className="btn" disabled={scanBusy} onClick={rescanVulns}>
              {scanBusy ? "Scanning…" : "Scan now"}
            </button>
            <span className={styles.scanRowHint}>Re-scans the installed packages against the pip-audit advisory database.</span>
          </div>
        </div>
      )}

      <div className={panelStyles.subHead}>{highlight("PyPI store", q)}</div>
      <form className={styles.searchForm} onSubmit={submitSearch}>
        <input
          type="text"
          value={draft}
          spellCheck="false"
          placeholder="Search packages… e.g. pillow, numpy, requests"
          disabled={!allowInternet}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" className="btn accent" disabled={!allowInternet || searchBusy}>
          {searchBusy ? "Searching…" : "Search"}
        </button>
        <button type="button" className="btn" disabled={!allowInternet || indexBusy} onClick={refreshIndex}>
          {indexBusy ? "Refreshing…" : "Refresh index"}
        </button>
      </form>
      <p className={styles.searchHint}>
        {highlight(
          query
            ? "Results for “" + query + "”. Search results and PyPI metadata are cached, so browsing this category again won't re-fetch or hit PyPI's rate limits; use “Refresh index” only when you want a fresh copy."
            : "Discovery is powered by the pypi-search-cache engine. The first search downloads the PyPI package index; afterwards everything works from its local cache and is never re-fetched just by reopening this category.",
          q,
        )}
      </p>

      {searchError && !searchBusy ? <div className={styles.banner}><Icon name="exclamation-triangle" /><span>{searchError}</span></div> : null}

      {search && search.items && search.items.length ? (
        <>
          <div className={styles.resultList}>
            {search.items.map((item) => {
              const actionBusy = isBusy(item.name);
              return (
                <div key={item.name} className={styles.resultRow}>
                  <div className={styles.resultTop}>
                    <div>
                      <span className={styles.resultName}>
                        <img src={pythonMark} alt="" className={styles.mark} />
                        {item.name}
                      </span>
                      {item.version ? <span className={styles.resultVer}>v{item.version}</span> : null}
                      {item.vulnerable ? (
                        <span
                          className={styles.vulnBadge}
                          title={"Known vulnerabilities: " + (item.vuln_ids && item.vuln_ids.length ? item.vuln_ids.join(", ") : item.vuln_count)}
                        >
                          {item.vuln_count} Vulnerability{item.vuln_count === 1 ? "" : "ies"} Found
                        </span>
                      ) : null}
                      {item.installed ? (
                        <span className={item.core ? styles.badge + " " + styles.badgeDim : styles.badge + " " + styles.badgeGood}>
                          {item.core ? "protected" : "installed " + (item.installed_version || "")}
                        </span>
                      ) : null}
                    </div>
                    <div className={styles.resultActions}>
                      {item.core ? (
                        <span className={styles.badge + " " + styles.badgeDim}>core</span>
                      ) : item.installed ? (
                        <>
                          {item.outdated ? (
                            <button type="button" className="btn" disabled={!allowInternet || actionBusy} onClick={() => runInstall(item, "update", 1, 0)}>
                              {actionBusy ? "Working…" : "Update"}
                            </button>
                          ) : null}
                          <button type="button" className="btn danger" disabled={actionBusy} onClick={() => runUninstall(item)}>
                            {actionBusy ? "Working…" : "Uninstall"}
                          </button>
                        </>
                      ) : (
                        <button type="button" className="btn accent" disabled={!allowInternet || actionBusy} onClick={() => runInstall(item, "install", 1, 0)}>
                          {actionBusy ? "Working…" : "Install"}
                        </button>
                      )}
                    </div>
                  </div>
                  {item.summary ? <p className={styles.resultSummary}>{item.summary}</p> : null}
                </div>
              );
            })}
          </div>
          <div className={styles.pager}>
            <span>
              {search.total} package{search.total === 1 ? "" : "s"} · page {search.page}/{search.pages}
            </span>
            <div className={styles.pagerBtns}>
              <button type="button" className="btn" disabled={searchBusy || search.page <= 1} onClick={() => runSearch(query, search.page - 1, false)}>
                ‹ Previous
              </button>
              <button type="button" className="btn" disabled={searchBusy || search.page >= search.pages} onClick={() => runSearch(query, search.page + 1, false)}>
                Next ›
              </button>
            </div>
          </div>
        </>
      ) : searchBusy ? (
        <div className={styles.empty}>Searching PyPI…</div>
      ) : query ? (
        <div className={styles.empty}>No packages match “{query}”.</div>
      ) : searchError ? null : (
        <div className={styles.empty}>Search for a package to see results here.</div>
      )}

      <div className={panelStyles.subHead}>{highlight("Utility dependencies", q)}</div>
      {loadBusy ? (
        <div className={styles.empty}>Loading dependencies…</div>
      ) : utilities.length ? (
        <div className={styles.depsBox}>
          {utilities.map((tool) => {
            const todo = tool.requirements.filter((r) => r.state !== "installed");
            return (
              <div key={tool.id} className={styles.depTool}>
                <div className={styles.depTop}>
                  <span className={styles.depName}>
                    <img src={pythonMark} alt="" className={styles.mark} />
                    {tool.title}
                  </span>
                  {todo.length && allowInternet ? (
                    <button type="button" className="btn accent" disabled={Boolean(toolBusy)} onClick={() => installMissing(tool)}>
                      {toolBusy === tool.id ? "Installing…" : "Install missing (" + todo.length + ")"}
                    </button>
                  ) : null}
                </div>
                {tool.requirements.length || tool.additional_requirements.length ? (
                  <div className={styles.depChips}>
                    {tool.requirements.map((req) => (
                      <span key={req.normalized} className={styles.chip + " " + chipClass(req.state)}>
                        {req.name}
                        <span className={styles.depNote}>
                          {req.state === "installed" ? " " + (req.installed_version || "ok") : req.state === "outdated" ? " → " + (req.latest_version || "update") : " missing"}
                        </span>
                      </span>
                    ))}
                    {tool.additional_requirements.map((ext) => (
                      <span key={ext.name} className={styles.chip + " " + (ext.satisfied ? styles.chipOk : styles.chipWarn)}>
                        {ext.name} · {ext.satisfied ? "ok" : ext.satisfied === false ? ext.note || "not found" : ext.note || "manual"}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className={styles.depNone}>No Python requirements declared.</div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className={styles.empty}>No utilities found.</div>
      )}
    </section>
  );
}