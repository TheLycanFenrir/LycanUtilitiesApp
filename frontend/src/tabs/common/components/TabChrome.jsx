import EmojiText from "../../../components/common/EmojiText.jsx";

export function ToolHeader({ title, description, onBack }) {
  return (
    <div className="tool-head">
      <div>
        <h1 className="tool-head-title"><EmojiText text={title} /></h1>
        {description && <p className="tool-head-sub"><EmojiText text={description} /></p>}
      </div>
      {onBack && (
        <button type="button" className="back-btn" onClick={onBack}>
          Back to Dashboard
        </button>
      )}
    </div>
  );
}

export function FlashToast({ flash, onClose }) {
  if (!flash) return null;
  return (
    <div className="toast-stack">
      <div className={"toast " + flash.kind} onClick={onClose}>
        <EmojiText text={flash.message} />
      </div>
    </div>
  );
}

export function ConfirmModal({ box, onAnswer }) {
  return (
    <div className="modal-overlay" onClick={() => onAnswer(false)}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title"><EmojiText text={box.title} /></div>
          <button type="button" className="modal-close" onClick={() => onAnswer(false)}>x</button>
        </div>
        <div className="modal-message"><EmojiText text={box.message} /></div>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={() => onAnswer(false)}>{box.no}</button>
          <button type="button" className="btn accent" onClick={() => onAnswer(true)}>{box.yes}</button>
        </div>
      </div>
    </div>
  );
}

export function FormActions({ busy, label, onStart, onQueue, queued, editingQueued, onSaveQueued, onCancelQueued }) {
  if (editingQueued) {
    return (
      <div className="form-actions">
        <button type="button" className="btn" onClick={onCancelQueued} disabled={busy}>
          Cancel Edit
        </button>
        <button type="button" className="btn accent" onClick={onSaveQueued} disabled={busy}>
          Save Job
        </button>
        <span className="grow" />
        <span className="preset-name">Editing a queued job — changes are saved back to the Lycan Worker.</span>
      </div>
    );
  }
  return (
    <div className="form-actions">
      {onQueue && (
        <button type="button" className="btn" onClick={onQueue} disabled={busy}>
          {queued ? "Added to Queue" : "Add to Queue"}
        </button>
      )}
      <button type="button" className="btn accent" onClick={onStart} disabled={busy}>
        {busy ? "Processing..." : <EmojiText text={label} />}
      </button>
      <span className="grow" />
      <span className="preset-name">Use the console panel to check progress and abort.</span>
    </div>
  );
}