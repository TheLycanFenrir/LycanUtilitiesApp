import { memo, useEffect, useState } from "react";
import { Icon } from "../common/SvgIcon.jsx";
import { clamp } from "../../utils/color/colorMath.js";

function meterClass(pct) {
  if (pct >= 90) return "red";
  if (pct >= 70) return "orange";
  return "";
}

function fixed(value, digits) {
  return Number(value || 0).toFixed(digits);
}

const Statusbar = memo(function Statusbar({ call, cpuName, hidden }) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const tick = async () => {
      const s = await call("get_system_stats");
      if (!cancelled && s) setStats(s);
    };
    tick();
    timer = setInterval(tick, 2000);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [call]);

  const ready = stats != null;
  const cpuPct = clamp(Number(stats?.cpu_percent) || 0, 0, 100);
  const sysPct = clamp(Number(stats?.sys_used_pct) || 0, 0, 100);
  const cpu = stats?.cpu_name && stats.cpu_name !== "Unknown CPU Model" ? stats.cpu_name : cpuName;
  const sysMem = fixed(stats?.sys_used_gb, 1) + " / " + fixed(stats?.sys_total_gb, 1) + " GB";
  const cpuLabel = cpu ? cpu + " (" + cpuPct.toFixed(0) + "%)" : "";

  return (
    <footer className={"statusbar" + (hidden ? " content-hidden" : "")}>
      <div className="statusbar-inner">
        <span className="status-chip" title={"CPU \u2014 " + cpuLabel}>
          <Icon name="cpu" />
          <span className="status-chip-label">CPU</span>
          <span className="status-chip-value status-chip-cpu">{ready ? cpu || "Unknown" : "\u2026"}</span>
        </span>
        <span className="status-chip" title={"CPU usage " + cpuPct.toFixed(0) + "%"}>
          <span className="status-meter">
            <span className={"status-meter-fill " + meterClass(cpuPct)} style={{ width: cpuPct + "%" }} />
          </span>
          <span className="status-chip-value">{ready ? cpuPct.toFixed(0) + "%" : "\u2026"}</span>
        </span>

        <span className="status-chip-sep" />

        <span className="status-chip" title={"This app is using " + fixed(stats?.app_rss_mb, 0) + " MB (peak " + fixed(stats?.app_peak_mb, 0) + " MB)"}>
          <Icon name="ram" />
          <span className="status-chip-label">App</span>
          <span className="status-chip-value">{ready ? fixed(stats?.app_rss_mb, 0) + " MB" : "\u2026"}</span>
        </span>

        <span className="status-chip-sep" />

        <span className="status-chip" title={"System RAM \u2014 " + sysMem + " (" + sysPct.toFixed(0) + "%)"}>
          <Icon name="ram" />
          <span className="status-chip-label">RAM</span>
          <span className="status-chip-value">{ready ? sysMem : "\u2026"}</span>
        </span>
        <span className="status-chip" title={"System RAM usage " + sysPct.toFixed(0) + "%"}>
          <span className="status-meter">
            <span className={"status-meter-fill " + meterClass(sysPct)} style={{ width: sysPct + "%" }} />
          </span>
          <span className="status-chip-value">{ready ? sysPct.toFixed(0) + "%" : "\u2026"}</span>
        </span>

        <span className="status-chip-grow" />
      </div>
    </footer>
  );
});

export default Statusbar;