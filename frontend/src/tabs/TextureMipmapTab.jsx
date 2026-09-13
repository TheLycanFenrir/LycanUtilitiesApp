import { useCallback, useEffect, useRef, useState } from "react";
import { usePyWebView } from "../hooks/usePyWebView.js";
import { useJobConsole } from "../hooks/useJobConsole.js";
import { usePersistentForm } from "../hooks/usePersistentForm.js";
import { usePathHistory } from "./common/hooks/usePathHistory.js";
import { useSavedSettings } from "./common/hooks/useSavedSettings.js";
import { useRecentJobAttach } from "./common/hooks/useRecentJobAttach.js";
import { useImageBrowse } from "./common/hooks/useImageBrowse.js";
import ToolTabLayout from "./common/components/ToolTabLayout.jsx";
import PathRow from "./common/components/PathRow.jsx";
import { fieldRow } from "./common/utils/fieldRow.js";
import ImageExportSettingsPanel from "./common/components/ImageExportSettingsPanel.jsx";

const TOOL = {
  id: "texture_mipmap",
  title: "Texture Mipmap Generator",
  description: "Generate mip chains from a single texture.",
};

const DEFAULT_TEMPLATE = "{texture_name}_mip{level}.{ext}";

const NPOT_OPTIONS = [
  ["none", "None (keep as-is)"],
  ["pad_edge", "Pad to Next Power Of Two (edge)"],
  ["stretch", "Stretch to Nearest Power Of Two"],
];

const FILTER_OPTIONS = [
  ["lanczos", "Lanczos"],
  ["box", "Box"],
  ["mitchell", "Mitchell / Cubic"],
  ["bilinear", "Bilinear"],
];

export default function TextureMipmapTab({ tool = TOOL, onBack, focusJobId, queuedEdit, onQueuedEditDone, queueRunning }) {
  const { call } = usePyWebView();

  const [sourceMode, setSourceMode] = useState("single");
  const [source, setSource] = useState("");
  const [output, setOutput] = useState("");
  const [normalMap, setNormalMap] = useState(false);
  const [npotMode, setNpotMode] = useState("none");
  const [resampleFilter, setResampleFilter] = useState("lanczos");
  const [exportDds, setExportDds] = useState(false);
  const [imageFormat, setImageFormat] = useState("png");
  const [quality, setQuality] = useState("95");
  const [pngCompressLevel, setPngCompressLevel] = useState("6");
  const [tgaCompression, setTgaCompression] = useState("none");
  const [tiffCompression, setTiffCompression] = useState("none");
  const [retainAlpha, setRetainAlpha] = useState(true);
  const [namingTemplate, setNamingTemplate] = useState(DEFAULT_TEMPLATE);
  const [openExplorer, setOpenExplorer] = useState(false);
  const [queued, setQueued] = useState(false);
  const [editingJobId, setEditingJobId] = useState(null);

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
    "texture_mipmap_source",
    "texture_mipmap_output",
  );

  const applyModel = useCallback((model) => {
    if ("source" in model) setSource(String(model.source || ""));
    if ("output" in model) setOutput(String(model.output || ""));
    if ("source_mode" in model) setSourceMode(String(model.source_mode || "single"));
    if ("normal_map" in model) setNormalMap(Boolean(model.normal_map));
    if ("npot_mode" in model) setNpotMode(String(model.npot_mode || "none"));
    if ("resample_filter" in model) setResampleFilter(String(model.resample_filter || "lanczos"));
    if ("export_dds" in model) setExportDds(Boolean(model.export_dds));
    if ("image_format" in model) setImageFormat(String(model.image_format || "png"));
    if ("quality" in model) setQuality(String(model.quality ?? ""));
    if ("png_compress_level" in model) setPngCompressLevel(String(model.png_compress_level ?? ""));
    if ("tga_compression" in model) setTgaCompression(String(model.tga_compression || "none"));
    if ("tiff_compression" in model) setTiffCompression(String(model.tiff_compression || "none"));
    if ("retain_alpha" in model) setRetainAlpha(Boolean(model.retain_alpha));
    if ("naming_template" in model) setNamingTemplate(String(model.naming_template ?? ""));
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

  const { browseSource, browseOutput } = useImageBrowse(
    call,
    {
      sourceKey: "texture_mipmap_source",
      outputKey: "texture_mipmap_output",
      sourceMode,
      source,
      setSource,
      output,
      setOutput,
    },
    addHistory,
  );

  const sourcePlaceholder = sourceMode === "bulk"
    ? "Folder containing the textures"
    : "The texture image file";

  const collectParams = () => ({
    source: source.trim(),
    output: output.trim(),
    source_mode: sourceMode,
    normal_map: normalMap,
    npot_mode: npotMode,
    resample_filter: resampleFilter,
    export_dds: exportDds,
    retain_alpha: retainAlpha,
    image_format: imageFormat,
    quality: quality.trim(),
    png_compress_level: pngCompressLevel.trim(),
    tga_compression: tgaCompression,
    tiff_compression: tiffCompression,
    naming_template: namingTemplate.trim() || DEFAULT_TEMPLATE,
    open_explorer_after_conversion: openExplorer,
  });

  usePersistentForm({ toolId: TOOL.id, call, collect: collectParams, enabled: loaded });

  const resetFields = () => {
    setSourceMode("single");
    setSource("");
    setOutput("");
    setNormalMap(false);
    setNpotMode("none");
    setResampleFilter("lanczos");
    setExportDds(false);
    setImageFormat("png");
    setQuality("95");
    setPngCompressLevel("6");
    setTgaCompression("none");
    setTiffCompression("none");
    setRetainAlpha(true);
    setNamingTemplate(DEFAULT_TEMPLATE);
    setOpenExplorer(false);
  };

  const validateParams = (params) => {
    if (!params.source) {
      showFlash("Please select a source texture or folder.", "warn");
      return false;
    }
    if (!params.output) {
      showFlash("Please select an output folder.", "warn");
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
      startLabel="Generate Mipmaps"
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
          <select id="in-source_mode" value={sourceMode} onChange={(e) => setSourceMode(e.target.value)}>
            <option value="single">Single Texture</option>
            <option value="bulk">Folder (bulk)</option>
          </select>,
        )}
        <PathRow
          inputId="in-source"
          listId="dl-texture_mipmap-source"
          label="Source"
          placeholder={sourcePlaceholder}
          value={source}
          onChange={(e) => setSource(e.target.value)}
          onBlur={() => addHistory("texture_mipmap_source", source.trim())}
          onBrowse={browseSource}
          history={sourceHistory}
        />
        <PathRow
          inputId="in-output"
          listId="dl-texture_mipmap-output"
          label="Output Folder"
          placeholder="Where the mip levels will be saved"
          value={output}
          onChange={(e) => setOutput(e.target.value)}
          onBlur={() => addHistory("texture_mipmap_output", output.trim())}
          onBrowse={browseOutput}
          history={outputHistory}
        />
      </section>

            <section className="panel" data-panel-title="Mipmap Settings">
              <h2 className="panel-title">Mipmap Settings</h2>
              <div className="field">
                <label>Normal Map</label>
                <div>
                  <input
                    id="in-normal_map"
                    type="checkbox"
                    checked={normalMap}
                    onChange={(e) => setNormalMap(e.target.checked)}
                  />
                </div>
                <div className="field-note">
                  Enables normal-map compatible resampling that avoids flipping signed channels.
                </div>
              </div>
              {fieldRow(
                "Non-Power-Of-Two Handling",
                <select id="in-npot_mode" value={npotMode} onChange={(e) => setNpotMode(e.target.value)}>
                  {NPOT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>,
              )}
              {fieldRow(
                "Resample Filter",
                <select
                  id="in-resample_filter"
                  value={resampleFilter}
                  onChange={(e) => setResampleFilter(e.target.value)}
                >
                  {FILTER_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>,
              )}
              <div className="field">
                <label>Export DDS Container</label>
                <div>
                  <input
                    id="in-export_dds"
                    type="checkbox"
                    checked={exportDds}
                    onChange={(e) => setExportDds(e.target.checked)}
                  />
                </div>
                <div className="field-note">
                  Attempts a .dds container alongside the image files when imageio is available.
                </div>
              </div>
            </section>

            <ImageExportSettingsPanel
              imageFormat={imageFormat}
              onImageFormatChange={setImageFormat}
              quality={quality}
              onQualityChange={setQuality}
              pngCompressLevel={pngCompressLevel}
              onPngCompressLevelChange={setPngCompressLevel}
              tgaCompression={tgaCompression}
              onTgaCompressionChange={setTgaCompression}
              tiffCompression={tiffCompression}
              onTiffCompressionChange={setTiffCompression}
              namingTemplate={namingTemplate}
              onNamingTemplateChange={setNamingTemplate}
              onResetNaming={() => setNamingTemplate(DEFAULT_TEMPLATE)}
              tokensNote="{texture_name} {level} {ext}"
            >
              <div className="field">
                <label>Retain Alpha Channel</label>
                <div>
                  <input
                    id="in-retain_alpha"
                    type="checkbox"
                    checked={retainAlpha}
                    onChange={(e) => setRetainAlpha(e.target.checked)}
                  />
                </div>
              </div>
            </ImageExportSettingsPanel>

            </ToolTabLayout>
  );
}