import { useCallback, useEffect, useRef, useState } from "react";
import { usePyWebView } from "../hooks/usePyWebView.js";
import { useJobConsole } from "../hooks/useJobConsole.js";
import { usePersistentForm } from "../hooks/usePersistentForm.js";
import { useRecentJobAttach } from "./common/hooks/useRecentJobAttach.js";
import ToolTabLayout from "./common/components/ToolTabLayout.jsx";
import FormGenerator from "../components/FormGenerator/FormGenerator.jsx";
import { FormStateProvider, useFormState } from "../contexts/FormStateContext.jsx";
import { hexToRgb } from "../utils/color/colorMath.js";

function FormToolInner({ tool, call, console, onBack, focusJobId, queuedEdit, onQueuedEditDone, queueRunning, schemaDescription }) {
  const { getAll, setAll, reset, schema } = useFormState();
  const [openExplorer, setOpenExplorer] = useState(false);
  const [queued, setQueued] = useState(false);
  const [ready, setReady] = useState(false);

  // Collect current form values into the backend job parameter payload. Color
  // fields are stored as hex in the UI but serialized as [r, g, b] for the
  // runtime scripts. open_explorer_after_conversion stays a frontend toggle
  // and is always serialized (true or false) so an explicit "off" survives
  // reloads. The output log console is always part of the tool layout.
  const collectParams = () => {
    const p = { ...getAll() };
    for (const s of schema || []) {
      if (s.type === "color" && typeof p[s.field_id] === "string" && p[s.field_id].startsWith("#")) {
        const rgb = hexToRgb(p[s.field_id]);
        if (rgb) p[s.field_id] = rgb;
      }
    }
    p.open_explorer_after_conversion = openExplorer;
    return p;
  };

  const { flush } = usePersistentForm({ toolId: tool.id, call, collect: collectParams, enabled: ready });

  // Save immediately when any field loses focus
  const handleFieldBlur = useCallback(() => {
    if (ready) flush();
  }, [ready, flush]);

  // Restore the user's saved settings once, then enable persistence so the
  // defaults never overwrite stored values on the first tick.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let saved;
      try {
        saved = await call("get_settings", tool.id);
      } catch {
        saved = null;
      }
      const doc = saved && saved.ok !== false ? saved.settings : null;
      if (cancelled) return;
      if (doc && typeof doc === "object" && Object.keys(doc).length) {
        const { open_explorer_after_conversion: savedOpenExplorer, ...formValues } = doc;
        delete formValues.show_output_log;
        if (typeof savedOpenExplorer === "boolean") setOpenExplorer(savedOpenExplorer);
        setAll(formValues);
      }
      setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [call, tool.id, setAll]);

  // Editing a queued job: prefill the form from the stored configuration.
  const appliedQueuedRef = useRef(null);
  useEffect(() => {
    if (!queuedEdit || !queuedEdit.params) return;
    if (appliedQueuedRef.current === queuedEdit.jobId) return;
    appliedQueuedRef.current = queuedEdit.jobId;
    setAll(queuedEdit.params || {});
    setReady(true);
  }, [queuedEdit, setAll]);

  // Attach to an explicitly focused job.
  const lastFocusRef = useRef(null);
  useEffect(() => {
    if (!focusJobId || lastFocusRef.current === focusJobId) return;
    lastFocusRef.current = focusJobId;
    console.attach(focusJobId);
  }, [focusJobId, console.attach]);

  // Queue mode: stream the Lycan Worker's job into this open tab too.
  const lastQueueAttachRef = useRef(null);
  useEffect(() => {
    if (!queueRunning || queueRunning.tool !== tool.id) return;
    if (console.busy || console.jobId) return;
    if (lastQueueAttachRef.current === queueRunning.jobId) return;
    lastQueueAttachRef.current = queueRunning.jobId;
    console.attach(queueRunning.jobId);
  }, [queueRunning, tool.id, console.busy, console.jobId, console.attach]);

  // Re-attach on remount to replay a finished/recent job's log and progress.
  useRecentJobAttach({
    call,
    toolId: tool.id,
    focusJobId,
    queueRunning,
    attach: console.attach,
    busy: console.busy,
    jobId: console.jobId,
  });

  const onStart = useCallback(async () => {
    const started = await console.runJob(tool.id, collectParams());
    if (started) setQueued(false);
  }, [console, tool.id]);

  const onQueue = useCallback(async () => {
    if (console.busy) return;
    const res = await call("enqueue_job", tool.id, collectParams());
    if (res && res.ok) {
      setQueued(true);
      console.showFlash("Added to the Lycan Worker queue.", "good");
    }
  }, [call, console, tool.id]);

  const onSaveQueued = useCallback(async () => {
    if (!queuedEdit) return;
    const res = await call("update_queued_job", queuedEdit.jobId, collectParams());
    if (res && res.ok) onQueuedEditDone();
    else console.showFlash("Could not save the queued job.", "error");
  }, [call, queuedEdit, onQueuedEditDone, console]);

  const onCancelQueued = useCallback(() => {
    if (queuedEdit) onQueuedEditDone();
  }, [queuedEdit, onQueuedEditDone]);

  return (
    <ToolTabLayout
      title={tool.title}
      description={tool.description}
      onBack={onBack}
      preset={{ tool, call, collect: collectParams, apply: setAll, reset }}
      console={console}
      flash={console.flash}
      onFlashClose={console.clearFlash}
      confirmBox={console.confirmBox}
      onAnswer={console.answerConfirm}
      startLabel="Start"
      busy={console.busy}
      onStart={onStart}
      onQueue={onQueue}
      queued={queued}
      editingQueued={Boolean(queuedEdit)}
      onSaveQueued={onSaveQueued}
      onCancelQueued={onCancelQueued}
      openExplorer={openExplorer}
      onOpenExplorerChange={setOpenExplorer}
    >
      <FormGenerator call={call} description={schemaDescription} onFieldBlur={handleFieldBlur} />
    </ToolTabLayout>
  );
}

export default function FormTool({ tool, onBack, focusJobId, queuedEdit, onQueuedEditDone, queueRunning }) {
  const { call } = usePyWebView();
  const console = useJobConsole({ call });
  const fields = (tool.form_schema && tool.form_schema.fields) || [];
  const fieldsKey = JSON.stringify(fields);
  const schemaDescription =
    tool.form_schema && typeof tool.form_schema.description === "string" ? tool.form_schema.description : null;
  return (
    <FormStateProvider moduleId={tool.id} fieldsKey={fieldsKey} fields={fields}>
      <FormToolInner
        tool={tool}
        call={call}
        console={console}
        onBack={onBack}
        focusJobId={focusJobId}
        queuedEdit={queuedEdit}
        onQueuedEditDone={onQueuedEditDone}
        queueRunning={queueRunning}
        schemaDescription={schemaDescription}
      />
    </FormStateProvider>
  );
}