import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import styles from "./UtilityCardList.module.css";

const EXIT_MS = 260;
const FLIP_MS = 280;

function rectOf(el) {
  const r = el.getBoundingClientRect();
  return { left: r.left, top: r.top, width: r.width, height: r.height };
}

/**
 * Diff the last rendered `cards` against the incoming `items` and produce a
 * reconciled list with statuses:
 *   - "enter"   -> freshly shown card, plays the stacking entrance animation
 *   - "steady"  -> card staying visible (candidate for FLIP position moves)
 *   - "leave"   -> card about to be hidden, kept mounted until its exit
 *                  animation finishes
 *
 * Existing cards keep their DOM slot so leaving cards animate out in place
 * while neighbors are still laid out around them. Pure reorders keep the new
 * `items` order and carry each card's current status over.
 */
function reconcile(prev, items, keyOf) {
  const itemList = items.map((item) => ({ id: keyOf(item), item }));
  const prevIds = new Set(prev.map((c) => c.id));
  const nextIds = new Set(itemList.map((c) => c.id));
  const byKey = new Map(prev.map((c) => [c.id, c]));
  const isReorder = nextIds.size === prevIds.size && itemList.every((c) => prevIds.has(c.id));

  if (isReorder) {
    return itemList.map(({ id, item }) => {
      const old = byKey.get(id);
      return { id, item, status: old && old.status === "leave" ? "enter" : old ? old.status : "enter" };
    });
  }

  const itemById = new Map(itemList.map((c) => [c.id, c.item]));
  const result = [];
  for (const c of prev) {
    if (itemById.has(c.id)) {
      result.push({ id: c.id, item: itemById.get(c.id), status: c.status === "leave" ? "enter" : c.status });
      itemById.delete(c.id);
    } else if (c.status !== "leave") {
      result.push({ ...c, status: "leave" });
    }
  }
  for (const [id, item] of itemById) result.push({ id, item, status: "enter" });
  return result;
}

/**
 * Utility Card Stack List.
 *
 * Animates the dashboard grid purely with CSS transitions/keyframes plus a
 * minimal FLIP pass for repositioning:
 *   1. entrance  - new cards stack in (scale + translateY + fade),
 *   2. exit      - removed cards scale down / fade / drift up before unmount,
 *   3. moves     - remaining cards glide to their new slots instead of snapping.
 *
 * Only `transform` and `opacity` are animated (GPU friendly), and the FLIP
 * inversion is applied for a single frame then transitioned back to identity.
 */
export default function UtilityCardList({
  items = [],
  getKey,
  renderCard,
  onItemClick,
  getTooltip,
  className = "",
  emptyState = null,
  ariaLabel = "Utility list",
}) {
  const keyOf = useMemo(() => getKey || ((item) => (item == null ? "" : String(item.id))), [getKey]);
  const [cards, setCards] = useState(() => items.map((item) => ({ id: keyOf(item), item, status: "enter" })));
  const listRef = useRef(null);
  const elRefs = useRef(new Map());
  const prevRects = useRef(new Map());
  const leaveTimers = useRef(new Map());

  const cardsKey = cards.map((c) => `${c.id}:${c.status}`).join("|");

  // Track prop changes: show/hide/reorder cards. Reconcile during render (the
  // documented "adjust state when a prop changes" pattern) so leaving cards
  // animate out in place before being unmounted. Compare by reference: the
  // dashboard rebuilds its list array when tool data changes (e.g. favorite
  // toggles), and reconcile swaps in those fresh item references in place.
  const [prevItems, setPrevItems] = useState(items);
  if (prevItems !== items) {
    setPrevItems(items);
    setCards((prev) => reconcile(prev, items, keyOf));
  }

  const removeCard = useCallback((id) => {
    const t = leaveTimers.current.get(id);
    if (t) {
      clearTimeout(t);
      leaveTimers.current.delete(id);
    }
    setCards((prev) => prev.filter((c) => c.id !== id));
    prevRects.current.delete(id);
    elRefs.current.delete(id);
  }, []);

  // Schedule unmount for leaving cards after their exit animation window.
  useEffect(() => {
    for (const c of cards) {
      if (c.status === "leave") {
        if (!leaveTimers.current.has(c.id)) {
          leaveTimers.current.set(c.id, setTimeout(() => removeCard(c.id), EXIT_MS));
        }
      } else if (leaveTimers.current.has(c.id)) {
        clearTimeout(leaveTimers.current.get(c.id));
        leaveTimers.current.delete(c.id);
      }
    }
  }, [cards, removeCard]);

  // FLIP: after every committed status change, invert moved cards to their old
  // slot for one frame, then let the transition glide them into their new slot.
  useLayoutEffect(() => {
    const listEl = listRef.current;
    const inverted = [];
    for (const card of cards) {
      if (card.status !== "steady") continue;
      const el = elRefs.current.get(card.id);
      const prev = prevRects.current.get(card.id);
      if (!el || !prev) continue;
      const r = el.getBoundingClientRect();
      const dx = prev.left - r.left;
      const dy = prev.top - r.top;
      if (dx !== 0 || dy !== 0) {
        el.classList.add(styles.moving);
        el.style.transform = `translate3d(${dx}px, ${dy}px, 0)`;
        inverted.push(el);
      }
    }
    if (inverted.length && listEl) {
      void listEl.offsetHeight; // force reflow
      requestAnimationFrame(() => {
        for (const el of inverted) {
          el.style.transform = "";
          el.classList.remove(styles.moving);
        }
      });
    }
    const t = setTimeout(() => {
      for (const card of cards) {
        if (card.status !== "steady") continue;
        const el = elRefs.current.get(card.id);
        if (el) prevRects.current.set(card.id, rectOf(el));
      }
    }, FLIP_MS + 40);
    return () => clearTimeout(t);
  }, [cardsKey, cards]);

  // Cleanup timers/refs on unmount.
  useEffect(
    () => () => {
      leaveTimers.current.forEach((t) => clearTimeout(t));
      leaveTimers.current.clear();
      elRefs.current.clear();
      prevRects.current.clear();
    },
    [],
  );

  const settleBase = (card) => {
    const el = elRefs.current.get(card.id);
    if (el) prevRects.current.set(card.id, rectOf(el));
  };

  return (
    <div ref={listRef} role="list" aria-label={ariaLabel} className={`${styles.list} ${className}`}>
      {cards.map((card) => (
        <div
          key={card.id}
          role="listitem"
          data-tooltip={getTooltip ? getTooltip(card.item) : undefined}
          tabIndex={onItemClick && card.status !== "leave" ? 0 : undefined}
          aria-label={getTooltip ? getTooltip(card.item) : undefined}
          ref={(node) => {
            if (node) elRefs.current.set(card.id, node);
            else elRefs.current.delete(card.id);
          }}
          className={`${styles.card} ${
            card.status === "enter" ? styles.enter : card.status === "leave" ? styles.leave : styles.steady
          }`}
          onClick={() => {
            if (card.status === "leave") return;
            onItemClick?.(card.item);
          }}
          onKeyDown={(e) => {
            if (card.status === "leave") return;
            if (e.target !== e.currentTarget) return;
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onItemClick?.(card.item);
            }
          }}
          onAnimationEnd={(e) => {
            if (e.target !== elRefs.current.get(card.id)) return;
            if (card.status === "enter") {
              setCards((prev) =>
                prev.map((c) => (c.id === card.id && c.status === "enter" ? { ...c, status: "steady" } : c)),
              );
              settleBase(card);
            } else if (card.status === "leave") {
              removeCard(card.id);
            }
          }}
        >
          {renderCard ? renderCard(card.item, card) : <span>{String(card.item?.title || card.id)}</span>}
        </div>
      ))}
      {cards.length === 0 && emptyState}
    </div>
  );
}