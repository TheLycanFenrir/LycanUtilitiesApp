import { useCallback, useEffect, useRef, useState } from "react";
import { usePyWebView } from "../hooks/usePyWebView.js";
import { useJobConsole } from "../hooks/useJobConsole.js";
import { usePersistentForm } from "../hooks/usePersistentForm.js";
import { usePathHistory } from "./common/hooks/usePathHistory.js";
import { useSavedSettings } from "./common/hooks/useSavedSettings.js";
import { useRecentJobAttach } from "./common/hooks/useRecentJobAttach.js";
import ToolTabLayout from "./common/components/ToolTabLayout.jsx";
import PathRow from "./common/components/PathRow.jsx";
import { fieldRow } from "./common/utils/fieldRow.js";
import ColorField from "../components/common/ColorField.jsx";
import FpsDropdown from "../components/FpsDropdown.jsx";
import { hexToRgb, rgbToHex } from "../utils/color/colorMath.js";
import { fileName, joinPath } from "../utils/paths/paths.js";
import { sanitizeFps, sanitizeInt } from "../utils/validate/sanitizers.js";

const TOOL = {
  id: "frames_to_video",
  title: "Frames to Video",
  description: "Convert a folder of image frames into a video.",
};

const EXT_HINT = {
  mp4_h264: ".mp4",
  mp4_av1: ".mp4",
  webm: ".webm",
  gif: ".gif",
  apng: ".apng",
  webp: ".webp",
};

const FORMAT_LABEL = {
  mp4_h264: "MP4 h264",
  mp4_av1: "MP4 AV1",
  webm: "WebM",
  gif: "GIF",
  apng: "APNG",
  webp: "WEBP",
};

const FORMAT_OPTIONS = [
  ["mp4_h264", "MP4 h264"],
  ["mp4_av1", "MP4 AV1"],
  ["webm", "WebM"],
  ["gif", "GIF"],
  ["apng", "APNG"],
  ["webp", "WEBP"],
];

const QUALITY_LABELS = {
  CRF: "Constant Quality (CRF)",
  Bitrate: "Bitrate (CBR)",
  "2-Pass VBR": "2-Pass VBR",
  Lossless: "Lossless",
};

const ALPHA_FORMATS = ["webm", "apng", "gif", "webp"];

function crfRange(fmt) {
  if (fmt === "mp4_h264") return [0, 51];
  if (["mp4_av1", "webm", "webp"].includes(fmt)) return [0, 63];
  return [null, null];
}

function qualityOptions(fmt) {
  if (["mp4_h264", "mp4_av1", "webm"].includes(fmt)) return ["CRF", "Bitrate", "2-Pass VBR"];
  if (fmt === "webp") return ["CRF", "Lossless", "Bitrate"];
  return [];
}

export default function FramesToVideoTab({ tool = TOOL, onBack, focusJobId, queuedEdit, onQueuedEditDone, queueRunning }) {
  const { call } = usePyWebView();

  const [sourceFolder, setSourceFolder] = useState("");
  const [outputFolder, setOutputFolder] = useState("");
  const [outputType, setOutputType] = useState("mp4_h264");
  const [fps, setFps] = useState("30");
  const [qualityMode, setQualityMode] = useState("CRF");
  const [crf, setCrf] = useState("18");
  const [bitrate, setBitrate] = useState("8000");
  const [threads, setThreads] = useState("1");
  const [transparent, setTransparent] = useState(false);
  const [background, setBackground] = useState("black");
  const [backgroundCustom, setBackgroundCustom] = useState("#000000");
  const [gifColorLimit, setGifColorLimit] = useState("256");
  const [openExplorer, setOpenExplorer] = useState(false);
  const [queued, setQueued] = useState(false);
  const [editingJobId, setEditingJobId] = useState(null);

  const [coreOptions, setCoreOptions] = useState([]);

  const {
    busy, jobId, status, tone, progress, logs,
    confirmBox, flash, clearFlash, showFlash, runJob, abort, pause, resume, paused,
    copyLog, answerConfirm, attach,
  } = useJobConsole({ call });

  const lastFocusRef = useRef(null);

  useEffect(() => {
    if (!focusJobId || lastFocusRef.current === focusJobId) return;
    lastFocusRef.current = focusJobId;
    attach(focusJobId);
  }, [focusJobId, attach]);

  const lastQueueAttachRef = useRef(null);

  // Queue mode: when the Lycan Worker starts a job for this tool, attach this
  // open tab to it so its Output Log streams here too.
  useEffect(() => {
    if (!queueRunning || queueRunning.tool !== tool.id) return;
    if (busy || jobId) return;
    if (lastQueueAttachRef.current === queueRunning.jobId) return;
    lastQueueAttachRef.current = queueRunning.jobId;
    attach(queueRunning.jobId);
  }, [queueRunning, tool.id, busy, jobId, attach]);

  // Re-attach on remount: restores the progress percent and Output Log after
  // exiting and re-entering this card mid-run (direct or finished queue jobs).
  useRecentJobAttach({ call, toolId: TOOL.id, focusJobId, queueRunning, attach, busy, jobId });

  const { sourceHistory, outputHistory, addHistory } = usePathHistory(
    call,
    "frames_to_video_source",
    "frames_to_video_output",
  );

  const applyModel = useCallback((model) => {
    if ("source_folder" in model) setSourceFolder(String(model.source_folder || ""));
    if ("output_folder" in model) setOutputFolder(String(model.output_folder || ""));
    if ("output_type" in model && model.output_type) setOutputType(String(model.output_type));
    if ("fps" in model) setFps(sanitizeFps(String(model.fps ?? "")));
    if ("quality_mode" in model) setQualityMode(String(model.quality_mode || "CRF"));
    if ("crf" in model) setCrf(sanitizeInt(String(model.crf ?? "")));
    if ("bitrate" in model) setBitrate(sanitizeInt(String(model.bitrate ?? "")));
    if ("threads" in model) setThreads(String(model.threads ?? ""));
    if ("transparent" in model) setTransparent(Boolean(model.transparent));
    if ("background" in model) {
      const value = model.background;
      if (Array.isArray(value) && value.length === 3) {
        const rgb = [Number(value[0]) || 0, Number(value[1]) || 0, Number(value[2]) || 0];
        setBackgroundCustom(rgbToHex(rgb));
        setBackground("custom");
      } else if (value === "white" || value === "black") {
        setBackground(String(value));
      } else {
        setBackground("black");
      }
    } else if ("background_color" in model && Array.isArray(model.background_color)) {
      const rgb = [Number(model.background_color[0]) || 0, Number(model.background_color[1]) || 0, Number(model.background_color[2]) || 0];
      setBackgroundCustom(rgbToHex(rgb));
      if (rgb[0] === 255 && rgb[1] === 255 && rgb[2] === 255) setBackground("white");
      else if (rgb[0] === 0 && rgb[1] === 0 && rgb[2] === 0) setBackground("black");
      else setBackground("custom");
    }
    if ("background_custom" in model && model.background_custom) {
      setBackgroundCustom(String(model.background_custom));
    }
    if ("gif_color_limit" in model) setGifColorLimit(String(model.gif_color_limit ?? ""));
    if ("open_explorer_after_conversion" in model) {
      setOpenExplorer(Boolean(model.open_explorer_after_conversion));
    }
  }, []);

  const { loaded } = useSavedSettings(TOOL.id, call, applyModel);

  useEffect(() => {
    if (!queuedEdit || !queuedEdit.params || !queuedEdit.jobId) return;
    const id = queuedEdit.jobId;
    setTimeout(() => {
      applyModel(queuedEdit.params);
      setEditingJobId(id);
      setQueued(false);
    }, 0);
  }, [queuedEdit, applyModel]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const cores = await call("get_core_options");
      if (!mounted) return;
      if (Array.isArray(cores) && cores.length) setCoreOptions(cores);
    })();
    return () => { mounted = false; };
  }, [call]);

  const isAlpha = ALPHA_FORMATS.includes(outputType);
  const hideBg = isAlpha && transparent;
  const hasQuality = qualityOptions(outputType).length > 0;
  const modeKey = String(qualityMode || "").toLowerCase();
  const showQualityMode = hasQuality;
  const showCrf = hasQuality && (modeKey === "crf" || modeKey === "");
  const showBitrate = hasQuality && (modeKey === "bitrate" || modeKey === "2-pass vbr");
  const showTransparent = isAlpha;
  const showGifColors = outputType === "gif";
  const outputExt = EXT_HINT[outputType] || ".mp4";
  const crfBounds = crfRange(outputType);
  const qualityChoices = hasQuality ? qualityOptions(outputType) : [];
  const threadOptions = coreOptions.length ? coreOptions : ["1"];
  const effectiveThreads = (coreOptions.length && !coreOptions.includes(threads)) ? coreOptions[0] : threads;
  const gifColorChoices = Array.from({ length: 253 }, (_, i) => String(i + 4));

  const baseName = () => {
    const src = sourceFolder.trim();
    if (!src) return "";
    return fileName(src);
  };

  const resolveOutputFile = () => {
    const folder = outputFolder.trim();
    const name = baseName() || "video";
    return joinPath(folder, name + outputExt);
  };

  const collectParams = () => {
    const bg = background === "white"
      ? [255, 255, 255]
      : background === "black"
        ? [0, 0, 0]
        : (hexToRgb(backgroundCustom) || [0, 0, 0]);
    const folder = outputFolder.trim();
    return {
      source_mode: "folder",
      source_folder: sourceFolder.trim(),
      output_folder: folder,
      output_file: outputFolder ? resolveOutputFile() : folder,
      output_type: outputType,
      fps: sanitizeFps(fps),
      quality_mode: qualityMode,
      crf: crf.trim(),
      bitrate: bitrate.trim(),
threads: effectiveThreads,
      transparent,
      background: background,
      background_color: bg,
      background_custom: backgroundCustom,
      gif_color_limit: gifColorLimit.trim(),
      open_explorer_after_conversion: openExplorer,
    };
  };

  usePersistentForm({ toolId: TOOL.id, call, collect: collectParams, enabled: loaded });

  const resetFields = () => {
    setSourceFolder("");
    setOutputFolder("");
    setOutputType("mp4_h264");
    setFps("30");
    setQualityMode("CRF");
    setCrf("18");
    setBitrate("8000");
    setThreads("1");
    setTransparent(false);
    setBackground("black");
    setBackgroundCustom("#000000");
    setGifColorLimit("256");
    setOpenExplorer(false);
  };

  const validateParams = (params) => {
    if (!params.source_folder) {
      showFlash("Please select a source folder containing your image frames.", "warn");
      return false;
    }
    if (!params.output_folder) {
      showFlash("Please select an output folder.", "warn");
      return false;
    }
    if (!parseFloat(sanitizeFps(params.fps)) || parseFloat(sanitizeFps(params.fps)) <= 0) {
      showFlash("Please enter a valid FPS value.", "warn");
      return false;
    }
    if (["Bitrate", "2-Pass VBR"].includes(params.quality_mode) &&
        (!params.bitrate || Number(params.bitrate) <= 0)) {
      showFlash("Bitrate must be a positive number for this quality mode.", "warn");
      return false;
    }
    return true;
  };

  const handleStart = async () => {
    if (busy) return;
    const params = collectParams();
    if (!validateParams(params)) return;
    setQueued(false);
    await runJob(TOOL.id, params);
  };

  const handleEnqueue = async () => {
    if (busy) return;
    const params = collectParams();
    if (!validateParams(params)) return;
    const res = await call("enqueue_job", TOOL.id, params);
    if (res && res.ok) {
      setQueued(true);
      showFlash("Added to the Lycan Worker queue.", "good");
    } else {
      showFlash("Could not add to the queue.", "error");
    }
  };

  const handleSaveQueued = async () => {
    if (!editingJobId || busy) return;
    const params = collectParams();
    if (!validateParams(params)) return;
    const res = await call("update_queued_job", editingJobId, params);
    if (res && res.ok) {
      showFlash("Queued job updated.", "good");
    } else {
      showFlash("Could not update the queued job.", "error");
    }
    setEditingJobId(null);
    if (onQueuedEditDone) onQueuedEditDone();
  };

  const handleCancelQueued = () => {
    setEditingJobId(null);
    if (onQueuedEditDone) onQueuedEditDone();
  };

  const browseFolder = async (which) => {
    const current = which === "source" ? sourceFolder : outputFolder;
    const picked = await call("open_dialog", "folder", current || "");
    if (!picked || !picked.length) return;
    const value = picked[0];
    if (which === "source") {
      setSourceFolder(value);
      addHistory("frames_to_video_source", value);
    } else {
      setOutputFolder(value);
      addHistory("frames_to_video_output", value);
    }
  };

  const handleFormatChange = (fmt) => {
    const list = qualityOptions(fmt);
    setOutputType(fmt);
    if (list.length && !list.includes(qualityMode)) setQualityMode(list[0]);
  };

  const clampCrf = (value) => {
    const [lo, hi] = crfBounds;
    if (lo == null || hi == null) return null;
    const v = parseInt(value, 10);
    if (Number.isNaN(v)) return null;
    const clamped = Math.max(lo, Math.min(hi, v));
    if (clamped === v) return null;
    showFlash(
      "CRF adjusted to " + clamped + " for " + FORMAT_LABEL[outputType] +
      " (allowed range " + lo + "-" + hi + ").",
      "warn",
    );
    return String(clamped);
  };

  const handleCrfChange = (e) => {
    const clean = sanitizeInt(e.target.value);
    setCrf(clampCrf(clean) ?? clean);
  };

  const handleCrfBlur = () => {
    if (crf === "") return;
    const clamped = clampCrf(crf);
    if (clamped != null) setCrf(clamped);
  };

  const handleBitrateChange = (e) => {
    const clean = sanitizeInt(e.target.value);
    if (clean === "0") {
      setBitrate("1");
      return;
    }
    setBitrate(clean.replace(/^0+(?=\d)/, ""));
  };

  const handleBitrateBlur = () => {
    const v = String(bitrate || "").trim();
    if (v === "" || Number(v) === 0) {
      setBitrate("1");
      showFlash("Bitrate cannot be 0 or empty. It has been set to 1.", "warn");
    }
  };

  return (
    <ToolTabLayout
      title={tool.title}
      description={tool.description}
      onBack={onBack}
      preset={{ tool: TOOL, call, collect: collectParams, apply: applyModel, reset: resetFields }}
      console={{ status, tone, progress, logs, jobId, copyLog, abort, pause, resume, paused }}
      flash={flash}
      onFlashClose={clearFlash}
      confirmBox={confirmBox}
      onAnswer={answerConfirm}
      startLabel="Start Conversion"
      busy={busy}
      onStart={handleStart}
      onQueue={handleEnqueue}
      queued={queued}
      editingQueued={!!editingJobId}
      onSaveQueued={handleSaveQueued}
      onCancelQueued={handleCancelQueued}
      openExplorer={openExplorer}
      onOpenExplorerChange={setOpenExplorer}
    >
      <section className="panel" data-panel-title="Input & Output">
        <h2 className="panel-title">Input &amp; Output</h2>
        {fieldRow(
          "Source Type",
          <select id="in-source_mode" value="folder" readOnly>
            <option value="folder">Folder (Bulk)</option>
          </select>,
        )}
        <PathRow
          inputId="in-source_folder"
          listId="dl-frames_to_video-source_folder"
          label="Source Folder"
          placeholder="Folder containing your image frames"
          value={sourceFolder}
          onChange={(e) => setSourceFolder(e.target.value)}
          onBlur={() => addHistory("frames_to_video_source", sourceFolder.trim())}
          onBrowse={() => browseFolder("source")}
          history={sourceHistory}
        />
        <PathRow
          inputId="in-output_folder"
          listId="dl-frames_to_video-output_folder"
          label="Output Folder"
          placeholder="Folder where the converted video will be saved"
          value={outputFolder}
          onChange={(e) => setOutputFolder(e.target.value)}
          onBlur={() => addHistory("frames_to_video_output", outputFolder.trim())}
          onBrowse={() => browseFolder("output")}
          history={outputHistory}
        />
        {fieldRow(
          "Output Type",
          <select id="in-output_type" value={outputType} onChange={(e) => handleFormatChange(e.target.value)}>
            {FORMAT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>,
        )}
        <div className="field-note">Output extension: {outputExt}</div>
      </section>

            <section className="panel" data-panel-title="Video Settings">
              <h2 className="panel-title">Video Settings</h2>
              {fieldRow(
                "Frames Per Second (FPS)",
                <div className="fps-field">
                  <input
                    id="in-fps"
                    type="text"
                    inputMode="decimal"
                    placeholder="e.g. 30"
                    value={fps}
                    onChange={(e) => setFps(sanitizeFps(e.target.value))}
                  />
                  <FpsDropdown value={fps} onChange={setFps} />
                </div>,
                <div className="field-note">Manual value, or pick a preset (integer / broadcast &amp; decimal).</div>,
              )}
              {showQualityMode && fieldRow(
                "Quality Mode",
                <select
                  id="in-quality_mode"
                  value={qualityMode}
                  onChange={(e) => setQualityMode(e.target.value)}
                >
                  {qualityChoices.map((value) => <option key={value} value={value}>{QUALITY_LABELS[value] || value}</option>)}
                </select>,
              )}
              {showCrf && fieldRow(
                "CRF Quality (Lower = Better)",
                <input
                  id="in-crf"
                  type="text"
                  inputMode="numeric"
                  value={crf}
                  onChange={handleCrfChange}
                  onBlur={handleCrfBlur}
                />,
                <div className="field-note">GIF / APNG do not use a CRF value.</div>,
              )}
              {showBitrate && fieldRow(
                "Bitrate (kbps)",
                <input
                  id="in-bitrate"
                  type="text"
                  inputMode="numeric"
                  value={bitrate}
                  onChange={handleBitrateChange}
                  onBlur={handleBitrateBlur}
                />,
                <div className="field-note">Used by Bitrate and 2-Pass VBR modes.</div>,
              )}
              {fieldRow(
                "CPU Cores",
                <select id="in-threads" value={effectiveThreads} onChange={(e) => setThreads(e.target.value)}>
                  {threadOptions.map((value) => <option key={value} value={value}>{value}</option>)}
                </select>,
              )}
              {showTransparent && (
                <div className="field">
                  <label>Transparency</label>
                  <div>
                    <input
                      id="in-transparent"
                      type="checkbox"
                      checked={transparent}
                      onChange={(e) => setTransparent(e.target.checked)}
                    />
                  </div>
                </div>
              )}
              {!hideBg && fieldRow(
                "Background",
                <select id="in-background" value={background} onChange={(e) => setBackground(e.target.value)}>
                  <option value="black">Black</option>
                  <option value="white">White</option>
                  <option value="custom">Custom</option>
                </select>,
              )}
              {!hideBg && background === "custom" && fieldRow(
                "Custom Color",
                <ColorField
                  id="in-background_custom"
                  value={backgroundCustom}
                  onChange={setBackgroundCustom}
                />,
              )}
              {showGifColors && fieldRow(
                "Colors",
                <select
                  id="in-gif_color_limit"
                  value={gifColorLimit}
                  onChange={(e) => setGifColorLimit(e.target.value)}
                >
                  {gifColorChoices.map((value) => <option key={value} value={value}>{value}</option>)}
                </select>,
                <div className="field-note">GIF palette size.</div>,
              )}
            </section>

            </ToolTabLayout>
  );
}