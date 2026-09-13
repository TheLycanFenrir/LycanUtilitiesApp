import { useCallback } from "react";
import { IMAGE_TYPES } from "../utils/imageOptions.js";

function isBulkSource(sourceMode) {
  return sourceMode === "bulk";
}

export function useImageBrowse(call, { sourceKey, outputKey, sourceMode, source, setSource, output, setOutput }, addHistory) {
  const browseSource = useCallback(async () => {
    const isBulk = isBulkSource(sourceMode);
    const picked = await call(
      "open_dialog",
      isBulk ? "folder" : "file",
      source || "",
      "",
      false,
      isBulk ? [] : IMAGE_TYPES,
    );
    if (!picked || !picked.length) return;
    setSource(picked[0]);
    addHistory(sourceKey, picked[0]);
  }, [call, sourceMode, source, setSource, addHistory, sourceKey]);

  const browseOutput = useCallback(async () => {
    const picked = await call("open_dialog", "folder", output || "");
    if (!picked || !picked.length) return;
    setOutput(picked[0]);
    addHistory(outputKey, picked[0]);
  }, [call, output, setOutput, addHistory, outputKey]);

  return { browseSource, browseOutput };
}