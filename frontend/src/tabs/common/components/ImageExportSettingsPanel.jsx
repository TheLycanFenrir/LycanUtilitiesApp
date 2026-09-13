import { fieldRow } from "../utils/fieldRow.js";
import { FORMAT_OPTIONS, TIFF_OPTIONS } from "../utils/imageOptions.js";

export default function ImageExportSettingsPanel({
  imageFormat,
  onImageFormatChange,
  quality,
  onQualityChange,
  pngCompressLevel,
  onPngCompressLevelChange,
  tgaCompression,
  onTgaCompressionChange,
  tiffCompression,
  onTiffCompressionChange,
  namingTemplate,
  onNamingTemplateChange,
  onResetNaming,
  tokensNote,
  children,
}) {
  const tiffJpeg = imageFormat === "tiff" && tiffCompression === "jpeg";
  const showQuality = ["jpg", "jpeg", "webp"].includes(imageFormat) || tiffJpeg;
  const showPngLevel = imageFormat === "png";
  const showTgaCompression = imageFormat === "tga";
  const showTiffCompression = imageFormat === "tiff";

  return (
    <section className="panel" data-panel-title="Export Settings">
      <h2 className="panel-title">Export Settings</h2>
      {fieldRow(
        "Image Format",
        <select
          id="in-image_format"
          value={imageFormat}
          onChange={(e) => onImageFormatChange(e.target.value)}
        >
          {FORMAT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>,
      )}
      {showQuality && fieldRow(
        "Quality (1-100)",
        <input
          id="in-quality"
          type="number"
          min="1"
          max="100"
          value={quality}
          onChange={(e) => onQualityChange(e.target.value)}
        />,
      )}
      {showPngLevel && fieldRow(
        "PNG Compression Level (0-9)",
        <input
          id="in-png_compress_level"
          type="number"
          min="0"
          max="9"
          value={pngCompressLevel}
          onChange={(e) => onPngCompressLevelChange(e.target.value)}
        />,
      )}
      {showTgaCompression && fieldRow(
        "TGA Compression",
        <select
          id="in-tga_compression"
          value={tgaCompression}
          onChange={(e) => onTgaCompressionChange(e.target.value)}
        >
          <option value="none">None</option>
          <option value="rle">RLE</option>
        </select>,
      )}
      {showTiffCompression && fieldRow(
        "TIFF Compression",
        <select
          id="in-tiff_compression"
          value={tiffCompression}
          onChange={(e) => onTiffCompressionChange(e.target.value)}
        >
          {TIFF_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>,
      )}
      {children}
      {fieldRow(
        "Naming Template",
        <input
          id="in-naming_template"
          type="text"
          value={namingTemplate}
          onChange={(e) => onNamingTemplateChange(e.target.value)}
        />,
        <div className="inline-actions">
          <button type="button" className="btn" onClick={onResetNaming}>
            Reset
          </button>
        </div>,
      )}
      <div className="field-note">Tokens: {tokensNote}</div>
    </section>
  );
}