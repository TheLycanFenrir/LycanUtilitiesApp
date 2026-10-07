import { useCallback, useMemo, useRef, useState } from "react";
import { ToolHeader } from "./common/components/TabChrome.jsx";
import { usePyWebView } from "../hooks/usePyWebView.js";
import EmojiText from "../components/common/EmojiText.jsx";
import { showToast } from "../utils/platform/toast.js";
import {ImgIcon} from "../components/common/ImageIcon.jsx";

/**
 * Load-error tab for utilities that failed validation / parsing.
 * Presents the failure as a diagnosable panel centered on the screen:
 * offending file, a console-style error log with a copy button, a snippet
 * of the last lines from the failing file (with real code row numbers) that
 * can be copied, and the actions inside the popup itself.
 */
export default function UtilityErrorTab({ tool, onBack, onOpenStore }) {
  const { call } = usePyWebView();
  const [copied, setCopied] = useState(false);
  const [snippetCopied, setSnippetCopied] = useState(false);
  const copyTimer = useRef(null);

  const openUtilities = useCallback(async () => {
    const res = await call("open_utilities_folder", tool.id || tool.title);
    if (res && res.ok !== true) showToast("Could not open the utility folder.", "error");
  }, [call, tool.id, tool.title]);

  const openStoreForUtility = useCallback(() => {
    onBack();
    if (onOpenStore) {
      onOpenStore(tool.title || tool.id);
    }
  }, [onBack, onOpenStore, tool.title, tool.id]);

  const messages = useMemo(
    () =>
      Array.isArray(tool.error_messages)
        ? tool.error_messages
        : [String(tool.error_messages || "This utility could not be loaded. Check the console output below.")],
    [tool.error_messages],
  );
  const snippet = useMemo(
    () => (Array.isArray(tool.error_snippet) ? tool.error_snippet : []),
    [tool.error_snippet],
  );
  const snippetLines = useMemo(
    () => (Array.isArray(tool.error_snippet_lines) ? tool.error_snippet_lines : []),
    [tool.error_snippet_lines],
  );
  const source = useMemo(() => String(tool.error_file || ""), [tool.error_file]);

  const copyReport = useCallback(async () => {
    const text = [
      "Utility failed to load: " + (tool.title || tool.id),
      source ? "File: " + source : "",
      "",
      ...messages,
    ].filter(Boolean).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 1600);
    } catch {
      showToast("Could not copy the error report.", "error");
    }
  }, [tool, source, messages]);

  const copySnippet = useCallback(async () => {
    const text = snippet
      .map((line, idx) => {
        const no = snippetLines[idx] != null ? snippetLines[idx] : idx + 1;
        return no + "\t" + line;
      })
      .join("\n");
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setSnippetCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setSnippetCopied(false), 1600);
    } catch {
      showToast("Could not copy the code snippet.", "error");
    }
  }, [snippet, snippetLines]);

  return (
    <div className="page">
      <div className="container">
        <ToolHeader title={tool.title} description={tool.description} onBack={onBack} />
        <div className="utility-error">
          <section className="panel utility-error-panel">
            <div className="utility-error-head">
              <div className="utility-error-icon">
                <ImgIcon src="assets/icons/wolf-sad.png" alt="Error" />
              </div>
              <div className="utility-error-head-body">
                <h2>This utility could not be loaded</h2>
                <p>
                  Whoops... Sorry, something failed while loading this utility happened. Update the utility via Lycan Utilities Store or report a bug to the utility creator.
                  We're sorry for the inconvenience, So sad....
                </p>
              </div>
            </div>
            <div className="error-snippet-title">
              <span>Loader console</span>
            </div>
            <div className="error-console" role="log" aria-label="Loader error log">
              <div className="error-console-bar">
                {source ? (
                    <code className="error-source">{source}</code>
                ) : (
                    <code className="error-source">No source or failed to load source</code>
                )}
                <button type="button" className="error-copy-btn" onClick={copyReport}>
                  {copied ? "Copied" : "Copy report"}
                </button>
              </div>
              <div className="error-console-body">
                {messages.map((message, idx) => (
                  <div key={idx} className="log-line error"><EmojiText text={message} /></div>
                ))}
              </div>
            </div>
            {snippet.length > 0 ? (
              <div className="error-snippet">
                <div className="error-snippet-title">
                  <span><EmojiText text={`Last ${snippet.length} line${snippet.length === 1 ? "" : "s"} of the offending file`} /></span>
                  <button type="button" className="error-copy-btn" onClick={copySnippet}>
                    {snippetCopied ? "Copied" : "Copy"}
                  </button>
                </div>
                <div className="error-snippet-body">
                  {snippet.map((line, idx) => (
                    <div key={idx} className="error-snippet-line">
                      <span className="error-snippet-no">{snippetLines[idx] != null ? snippetLines[idx] : idx + 1}</span>
                      <code>{line || " "}</code>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="form-actions form-actions-no-panel utility-error-actions">
              <button type="button" className="btn secondary" onClick={openUtilities}>
                Reveal This Utility Folder
              </button>
              <button type="button" className="btn accent" onClick={openStoreForUtility}>
                Check Updates for {tool.title}
              </button>
              <button type="button" className="btn accent" onClick={onBack}>
                OK
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}