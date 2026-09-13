import { fieldRow } from "../utils/fieldRow.js";

export default function PathRow({
  inputId, listId, label, placeholder,
  value, onChange, onBlur, onBrowse, history,
}) {
  return (
    <>
      {fieldRow(
        label,
        <input
          id={inputId}
          type="text"
          placeholder={placeholder}
          list={listId}
          value={value}
          onChange={onChange}
          onBlur={onBlur}
        />,
        <div className="inline-actions">
          <button type="button" className="btn" onClick={onBrowse}>
            Browse...
          </button>
        </div>,
      )}
      <datalist id={listId}>
        {history.map((item) => <option key={item} value={item} />)}
      </datalist>
    </>
  );
}