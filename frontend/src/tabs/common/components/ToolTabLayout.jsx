import {
  ToolHeader, FlashToast, ConfirmModal, FormActions,
} from "./TabChrome.jsx";
import PresetBar from "../../../components/PresetBar.jsx";
import ConsolePanel from "../../../components/ConsolePanel.jsx";

export default function ToolTabLayout({
  title, description, onBack,
  preset,
  console,
  flash, onFlashClose,
  confirmBox, onAnswer,
  startLabel, busy, onStart,
  onQueue, queued,
  editingQueued, onSaveQueued, onCancelQueued,
  openExplorer, onOpenExplorerChange,
  children,
}) {
  const { status, tone, progress, logs, jobId, copyLog, abort, pause, resume, paused } = console;
  return (
    <div className="page">
      <FlashToast flash={flash} onClose={onFlashClose} />
      <div className="container">
        <ToolHeader title={title} description={description} onBack={onBack} />
        <div className="tool-layout">
          <div className="tool-form" data-form="">
            <PresetBar {...preset} />
            {children}
            <section className="panel" data-panel-title="Options">
              <h2 className="panel-title">Options</h2>
              <div className="field">
                <label htmlFor="in-open_explorer_after_conversion">Open Explorer After Conversion</label>
                <div>
                  <input
                    id="in-open_explorer_after_conversion"
                    type="checkbox"
                    checked={openExplorer}
                    onChange={(e) => onOpenExplorerChange(e.target.checked)}
                  />
                </div>
              </div>
            </section>
            <FormActions busy={busy} label={startLabel} onStart={onStart} onQueue={onQueue} queued={queued} editingQueued={editingQueued} onSaveQueued={onSaveQueued} onCancelQueued={onCancelQueued} />
          </div>
          <div className="console-host">
            <ConsolePanel
              status={status}
              tone={tone}
              progress={progress}
              logs={logs}
              busy={busy}
              jobId={jobId}
              copyLog={copyLog}
              abort={abort}
              pause={pause}
              resume={resume}
              paused={paused}
            />
          </div>
        </div>
      </div>
      {confirmBox && <ConfirmModal box={confirmBox} onAnswer={onAnswer} />}
    </div>
  );
}