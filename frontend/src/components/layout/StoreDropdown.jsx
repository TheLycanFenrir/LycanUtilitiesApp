import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "../common/SvgIcon.jsx";
import EmojiText from "../common/EmojiText.jsx";
import { svgBody } from "../../utils/icons/heroiconPaths.js";
import { toolIconFile } from "../../utils/paths/paths.js";
import wolfHead from "../../../public/assets/icons/wolf-head.svg?raw";

function WolfIcon() {
  return (
    <svg viewBox="0 0 512 512" className="svg-icon wolf" aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: svgBody(wolfHead) }} />
  );
}

/**
 * "Lycan Utilities Store" dropdown, styled like the Lycan Worker dropdown.
 *
 * * Internet must be enabled (settings > General > Allow Internet Access) for
 *   new downloads; the fetched catalog is persisted to the backend store file
 *   (userdata/lycan_utilities_store/lycan_utilities_store_fetchres.json).
 * * With internet disabled the popup shows only locally installed utilities
 *   and disables the download actions, so the store never pretends to work.
 * * Icons are the real utility PNGs the backend mirrors from the scanner's
 *   .cache into userdata - no hero icons for store items.
 */
export default function StoreDropdown({ call, open: externalOpen, onOpenChange, initialSearchQuery }) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = externalOpen !== undefined ? externalOpen : internalOpen;
  const setOpen = onOpenChange || setInternalOpen;
  const [store, setStore] = useState(null);
  const [query, setQuery] = useState(initialSearchQuery || "");
  const [notice, setNotice] = useState(null);
  const [detail, setDetail] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const wrapRef = useRef(null);
  const noticeTimer = useRef(null);
  const popupBodyRef = useRef(null);
  const highlightIdRef = useRef(null);

  useEffect(() => () => {
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
  }, []);

  // External opens (e.g. "Open Lycan Utilities Store" on the error tab) should
  // jump the page to the topbar store so the popup is actually visible, then
  // bring the entry that matches the requested utility into view.
  const wasOpen = useRef(open);
  useEffect(() => {
    const justOpened = !wasOpen.current && open;
    wasOpen.current = open;
    if (!justOpened) return;
    const timer = setTimeout(() => {
      wrapRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
    return () => clearTimeout(timer);
  }, [open]);

  const showNotice = useCallback((msg) => {
    setNotice(msg || null);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    if (msg) noticeTimer.current = setTimeout(() => setNotice(null), 4000);
  }, []);

  const fetchStore = useCallback(async () => {
    try {
      const data = await call("get_utilities_store");
      if (data) setStore(data);
    } catch {
      // Ignore transient bridge errors; the popup retries on next open.
    }
  }, [call]);

  // Reset query when the external store closes, and apply the requested
  // search query on each external open (e.g. from the error tab). Done during
  // render (adjust-state pattern) to avoid sync setState inside effects.
  const [prevExternalOpen, setPrevExternalOpen] = useState(externalOpen);
  if (externalOpen !== prevExternalOpen) {
    if (externalOpen === false) {
      setQuery("");
    } else if (externalOpen === true && initialSearchQuery) {
      setQuery(initialSearchQuery);
    }
    setPrevExternalOpen(externalOpen);
  }

  useEffect(() => {
    if (!open) return;
    const initTimer = setTimeout(() => fetchStore(), 0);
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(initTimer);
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, fetchStore]);

  const items = useMemo(() => {
    const list = (store && Array.isArray(store.items) && store.items) || [];
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (item) =>
        item.title.toLowerCase().includes(q) || item.description.toLowerCase().includes(q),
    );
  }, [store, query]);

  // The utility that triggered the store (from the error tab via the search
  // query) is highlighted so it's obvious which one needs fixing.
  const highlightId = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !store || !Array.isArray(store.items)) return null;
    const found = store.items.find(
      (item) => item.title.toLowerCase() === q || String(item.id).toLowerCase() === q,
    );
    return found ? found.id : null;
  }, [store, query]);

  // Keep the highlighted entry in the middle of the visible list.
  useEffect(() => {
    if (!open || !highlightId) return;
    const timer = setTimeout(() => {
      const body = popupBodyRef.current;
      const el = highlightIdRef.current;
      if (body && el) {
        const bodyRect = body.getBoundingClientRect();
        const elRect = el.getBoundingClientRect();
        if (elRect.top < bodyRect.top || elRect.bottom > bodyRect.bottom) {
          body.scrollTop += elRect.top - bodyRect.top - (bodyRect.height - elRect.height) / 2;
        }
      }
    }, 120);
    return () => clearTimeout(timer);
  }, [open, highlightId]);

  const internet = !!(store && store.internet);

  const runAction = async (item) => {
    setBusyId(item.id);
    try {
      const res = await call("store_download", item.id);
      if (res && res.ok) {
        const action = res.action === "update" ? "updated" : "downloaded";
        showNotice(res.free ? item.title + " " + action + " (free)." : item.title + " " + action + ".");
        setStore((s) =>
          s
            ? {
                ...s,
                items: s.items.map((it) =>
                  it.id === item.id ? { ...it, installed: true, version: res.version || it.version } : it,
                ),
              }
            : s,
        );
      } else if (res && res.reason === "internet_disabled") {
        showNotice("Internet access is disabled. Enable it in Settings > General to download utilities.");
      } else {
        showNotice("The store could not complete that download.");
      }
    } catch {
      showNotice("The store is temporarily unavailable.");
    } finally {
      setBusyId(null);
    }
  };

  const openDetail = async (item) => {
    try {
      const res = await call("store_learn_more", item.id);
      if (res && res.ok) setDetail(res);
      else showNotice("No details available for this utility.");
    } catch {
      showNotice("No details available for this utility.");
    }
  };

  return (
    <div className="store-wrap" ref={wrapRef}>
      <button
        type="button"
        className="store-toggle"
        title="Lycan Utilities Store"
        aria-label="Lycan Utilities Store"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <WolfIcon />
        <span className="store-toggle-label">Store</span>
        <span className="store-chevron"><Icon name="chevron-down" /></span>
      </button>
      {open ? (
        <div className="store-popup">
          <div className="store-head">
            <span className="store-title"><WolfIcon /> Lycan Utilities Store</span>
            <span className="grow" />
            <span className={"store-internet " + (internet ? "on" : "off")}>
              <span className="store-internet-dot" />
              {internet ? "Online" : "Offline"}
            </span>
          </div>
          {notice && <div className="store-notice" role="status"><EmojiText text={notice} /></div>}
          <div className="store-search">
            <Icon name="search" />
            <input
              type="text"
              value={query}
              placeholder="Search utilities..."
              aria-label="Search utilities"
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          {detail ? (
            <div className="store-detail">
              <div className="store-detail-head">
                <span className="store-detail-title"><EmojiText text={detail.title} /></span>
                <button
                  type="button"
                  className="worker-remove"
                  title="Back to the store list"
                  aria-label="Back to the store list"
                  onClick={() => setDetail(null)}
                >
                  <Icon name="x" />
                </button>
              </div>
              <p className="store-detail-desc"><EmojiText text={detail.description} /></p>
              <dl className="store-detail-meta">
                <div><dt>Version</dt><dd>{detail.version}</dd></div>
                <div><dt>Price</dt><dd>{detail.free ? "Free" : "Paid"}</dd></div>
                <div><dt>Author</dt><dd>{detail.credits}</dd></div>
                <div><dt>Size</dt><dd>{detail.size_estimate}</dd></div>
              </dl>
            </div>
          ) : !store ? (
            <div className="store-empty">Loading the catalog...</div>
          ) : items.length === 0 ? (
            <div className="store-empty">
              {query ? (
                <>
                  <img src="/assets/icons/wolf-sad.png" alt="" className="empty-icon" />
                  No utilities match your search.
                </>
              ) : "No utilities available."}
            </div>
          ) : (
            <div className="store-popup-body" ref={popupBodyRef}>
              {items.map((item) => (
<div
                  className={"store-item" + (item.id === highlightId ? " store-item-highlight" : "")}
                  key={item.id}
                  ref={item.id === highlightId ? highlightIdRef : null}
                >
                    <div className="store-item-icon">
                      {item.icon ? (
                        <img
                          src={toolIconFile(item.icon)}
                          alt=""
                          className="store-item-img"
                          onError={(e) => { e.currentTarget.style.display = "none"; }}
                        />
                      ) : (
                        <WolfIcon />
                      )}
                    </div>
                  <div className="store-item-main">
                    <div className="store-item-title-row">
                      <span className="store-item-title"><EmojiText text={item.title} /></span>
                      {item.installed ? (
                        <span className="chip store-chip-installed">Installed</span>
                      ) : (
                        <span className="chip store-chip-free">Free</span>
                      )}
                    </div>
                    <p className="store-item-desc"><EmojiText text={item.description} /></p>
                    <div className="store-item-meta">
                      <span className="store-item-version">v{item.version}</span>
                      {item.installed && item.free && <span className="store-item-free">free</span>}
                    </div>
                  </div>
                  <div className="store-item-actions">
                    <button
                      type="button"
                      className="btn tiny"
                      onClick={() => openDetail(item)}
                    >
                      Learn more
                    </button>
                    {internet ? (
                      <button
                        type="button"
                        className="btn tiny accent"
                        disabled={busyId === item.id}
                        onClick={() => runAction(item)}
                      >
                        {busyId === item.id
                          ? "..."
                          : item.installed
                            ? <><Icon name="arrow-path" /> Update</>
                            : <><Icon name="download" /> Download</>}
                      </button>
                    ) : !item.installed ? (
                      <span className="store-offline-hint" title="Enable Internet Access in Settings > General">Offline</span>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}

          {!internet && !detail ? (
            <div className="store-offline-note">
              Internet access is disabled, so only your installed utilities are listed.
              Enable "Allow Internet Access" in Settings &gt; General to browse and download from the store.
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}