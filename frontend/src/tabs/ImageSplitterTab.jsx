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
  id: "image_splitter",
  title: "Image Splitter",
  description: "Split images into tiles.",
};

const GRID_TEMPLATE = "{basename}_r{row}_c{col}_w{width}_h{height}.{ext}";
const GRID_FALLBACK = "{basename}_r{row}_c{col}.{ext}";
const ALPHA_FALLBACK = "{basename}_tile_{index}.{ext}";

const MODE_LABELS = {
  grid: "Grid (rows x columns)",
  tile_size: "Custom Tile Size (pixels)",
  alpha_components: "Transparency Components",
};

const RESOLUTION_OPTIONS = [
  ["allow_variation", "Allow Variation (uneven tiles)"],
  ["bleed_padding", "Bleed / Edge Padding"],
  ["crop_to_fit", "Crop to Fit"],
  ["abort", "Abort After Partial Detection"],
];

const PADDING_OPTIONS = [
  ["edge", "Edge Padding"],
  ["reflect", "Reflect Padding"],
  ["texture_bleed", "Texture Bleed"],
];

export default function ImageSplitterTab({ tool = TOOL, onBack, focusJobId, queuedEdit, onQueuedEditDone, queueRunning }) {
  const { call } = usePyWebView();

  const [sourceMode, setSourceMode] = useState("single");
  const [source, setSource] = useState("");
  const [output, setOutput] = useState("");
  const [mode, setMode] = useState("grid");
  const [rows, setRows] = useState("1");
  const [columns, setColumns] = useState("1");
  const [tileWidth, setTileWidth] = useState("512");
  const [tileHeight, setTileHeight] = useState("512");
  const [alphaThreshold, setAlphaThreshold] = useState("0");
  const [resolutionMode, setResolutionMode] = useState("allow_variation");
  const [paddingMode, setPaddingMode] = useState("edge");
  const [bleedRadius, setBleedRadius] = useState("0");
  const [imageFormat, setImageFormat] = useState("png");
  const [quality, setQuality] = useState("95");
  const [pngCompressLevel, setPngCompressLevel] = useState("6");
  const [tgaCompression, setTgaCompression] = useState("none");
  const [tiffCompression, setTiffCompression] = useState("none");
  const [discardBlankTiles, setDiscardBlankTiles] = useState(false);
  const [namingTemplate, setNamingTemplate] = useState(GRID_TEMPLATE);
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
    "image_split_source",
    "image_split_output",
  );

  const applyModel = useCallback((model) => {
    if ("source" in model) setSource(String(model.source || ""));
    if ("output" in model) setOutput(String(model.output || ""));
    if ("source_mode" in model) setSourceMode(String(model.source_mode || "single"));
    if ("mode" in model) setMode(String(model.mode || "grid"));
    if ("rows" in model) setRows(String(model.rows ?? ""));
    if ("columns" in model) setColumns(String(model.columns ?? ""));
    if ("tile_width" in model) setTileWidth(String(model.tile_width ?? ""));
    if ("tile_height" in model) setTileHeight(String(model.tile_height ?? ""));
    if ("alpha_threshold" in model) setAlphaThreshold(String(model.alpha_threshold ?? ""));
    if ("resolution_mode" in model) setResolutionMode(String(model.resolution_mode || "allow_variation"));
    if ("padding_mode" in model) setPaddingMode(String(model.padding_mode || "edge"));
    if ("bleed_radius" in model) setBleedRadius(String(model.bleed_radius ?? ""));
    if ("image_format" in model) setImageFormat(String(model.image_format || "png"));
    if ("quality" in model) setQuality(String(model.quality ?? ""));
    if ("png_compress_level" in model) setPngCompressLevel(String(model.png_compress_level ?? ""));
    if ("tga_compression" in model) setTgaCompression(String(model.tga_compression || "none"));
    if ("tiff_compression" in model) setTiffCompression(String(model.tiff_compression || "none"));
    if ("discard_blank_tiles" in model) setDiscardBlankTiles(Boolean(model.discard_blank_tiles));
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
      sourceKey: "image_split_source",
      outputKey: "image_split_output",
      sourceMode,
      source,
      setSource,
      output,
      setOutput,
    },
    addHistory,
  );

  const isAlpha = mode === "alpha_components";
  const showGrid = mode === "grid";
  const showTile = mode === "tile_size";
  const showResolution = !isAlpha;
  const showPadding = !isAlpha;
  const showBleed = !isAlpha;
  const sourcePlaceholder = sourceMode === "bulk"
    ? "Folder containing the images to split"
    : "The image file to split";

  const collectParams = () => ({
    source: source.trim(),
    output: output.trim(),
    source_mode: sourceMode,
    mode,
    rows: rows.trim(),
    columns: columns.trim(),
    tile_width: tileWidth.trim(),
    tile_height: tileHeight.trim(),
    alpha_threshold: alphaThreshold.trim(),
    resolution_mode: resolutionMode,
    padding_mode: paddingMode,
    bleed_radius: bleedRadius.trim(),
    image_format: imageFormat,
    quality: quality.trim(),
    png_compress_level: pngCompressLevel.trim(),
    tga_compression: tgaCompression,
    tiff_compression: tiffCompression,
    discard_blank_tiles: discardBlankTiles,
    naming_template: namingTemplate.trim() ||
      (mode === "alpha_components" ? ALPHA_FALLBACK : GRID_FALLBACK),
    open_explorer_after_conversion: openExplorer,
  });

  usePersistentForm({ toolId: TOOL.id, call, collect: collectParams, enabled: loaded });

  const resetFields = () => {
    setSourceMode("single");
    setSource("");
    setOutput("");
    setMode("grid");
    setRows("1");
    setColumns("1");
    setTileWidth("512");
    setTileHeight("512");
    setAlphaThreshold("0");
    setResolutionMode("allow_variation");
    setPaddingMode("edge");
    setBleedRadius("0");
    setImageFormat("png");
    setQuality("95");
    setPngCompressLevel("6");
    setTgaCompression("none");
    setTiffCompression("none");
    setDiscardBlankTiles(false);
    setNamingTemplate(GRID_TEMPLATE);
    setOpenExplorer(false);
  };

  const validateParams = (params) => {
    if (!params.source) {
      showFlash("Please select a source image or folder.", "warn");
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
      startLabel="Start Split"
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
            <option value="single">Single Image</option>
            <option value="bulk">Folder (bulk)</option>
          </select>,
        )}
        <PathRow
          inputId="in-source"
          listId="dl-image_splitter-source"
          label="Source"
          placeholder={sourcePlaceholder}
          value={source}
          onChange={(e) => setSource(e.target.value)}
          onBlur={() => addHistory("image_split_source", source.trim())}
          onBrowse={browseSource}
          history={sourceHistory}
        />
        <PathRow
          inputId="in-output"
          listId="dl-image_splitter-output"
          label="Output Folder"
          placeholder="Where the tiles will be saved"
          value={output}
          onChange={(e) => setOutput(e.target.value)}
          onBlur={() => addHistory("image_split_output", output.trim())}
          onBrowse={browseOutput}
          history={outputHistory}
        />
      </section>

            <section className="panel" data-panel-title="Split Mode">
              <h2 className="panel-title">Split Mode</h2>
              {fieldRow(
                "Split Mode",
                <select id="in-mode" value={mode} onChange={(e) => setMode(e.target.value)}>
                  {Object.keys(MODE_LABELS).map((value) => (
                    <option key={value} value={value}>{MODE_LABELS[value]}</option>
                  ))}
                </select>,
              )}
              {showGrid && fieldRow(
                "Rows",
                <input
                  id="in-rows"
                  type="number"
                  min="1"
                  value={rows}
                  onChange={(e) => setRows(e.target.value)}
                />,
              )}
              {showGrid && fieldRow(
                "Columns",
                <input
                  id="in-columns"
                  type="number"
                  min="1"
                  value={columns}
                  onChange={(e) => setColumns(e.target.value)}
                />,
              )}
              {showTile && fieldRow(
                "Tile Width (px)",
                <input
                  id="in-tile_width"
                  type="number"
                  min="1"
                  value={tileWidth}
                  onChange={(e) => setTileWidth(e.target.value)}
                />,
              )}
              {showTile && fieldRow(
                "Tile Height (px)",
                <input
                  id="in-tile_height"
                  type="number"
                  min="1"
                  value={tileHeight}
                  onChange={(e) => setTileHeight(e.target.value)}
                />,
              )}
              {fieldRow(
                "Alpha Threshold",
                <input
                  id="in-alpha_threshold"
                  type="number"
                  min="0"
                  max="255"
                  value={alphaThreshold}
                  onChange={(e) => setAlphaThreshold(e.target.value)}
                />,
                <div className="field-note">Pixels with alpha above this value count as part of a component.</div>,
              )}
              {showResolution && fieldRow(
                "Resolution Mode",
                <select
                  id="in-resolution_mode"
                  value={resolutionMode}
                  onChange={(e) => setResolutionMode(e.target.value)}
                >
                  {RESOLUTION_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>,
              )}
              {showPadding && fieldRow(
                "Padding Mode",
                <select
                  id="in-padding_mode"
                  value={paddingMode}
                  onChange={(e) => setPaddingMode(e.target.value)}
                >
                  {PADDING_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>,
              )}
              {showBleed && fieldRow(
                "Bleed Radius (px)",
                <input
                  id="in-bleed_radius"
                  type="number"
                  min="0"
                  value={bleedRadius}
                  onChange={(e) => setBleedRadius(e.target.value)}
                />,
                <div className="field-note">Pixels of edge texel extrusion used by texture-bleed padding.</div>,
              )}
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
              onResetNaming={() => setNamingTemplate(GRID_TEMPLATE)}
              tokensNote="{basename} {row} {col} {index} {width} {height} {ext}"
            >
              <div className="field">
                <label>Discard Blank (Fully Transparent) Tiles</label>
                <div>
                  <input
                    id="in-discard_blank_tiles"
                    type="checkbox"
                    checked={discardBlankTiles}
                    onChange={(e) => setDiscardBlankTiles(e.target.checked)}
                  />
                </div>
              </div>
            </ImageExportSettingsPanel>

            </ToolTabLayout>
  );
}