import { useRef, useState } from "react";
import { Icon, WolfIcon } from "../components/common/SvgIcon.jsx";
import { highlightWithEmoji } from "../components/settings/highlight.jsx";
import EmojiText, { Emoji } from "../components/common/EmojiText.jsx";
import useBluePulse from "../hooks/useCyanPulse.js";
import { toolIconFile } from "../utils/paths/paths.js";
import UtilityCardList from "../components/UtilityCardList/UtilityCardList.jsx";

const PILLS = [
  ["all", "All", "grid"],
  ["az", "A-Z", "list"],
  ["fav", "Favorites", "star"],
  ["used", "Last Used", "clock"],
];

const SORT_KEY = "lycan.dashboard.sort";
function readSort() {
  try {
    const v = localStorage.getItem(SORT_KEY);
    return PILLS.some(([key]) => key === v) ? v : "all";
  } catch {
    return "all";
  }
}

function sortList(list, sort) {
  const arr = [...list];
  switch (sort) {
    case "az":
      return arr.sort((a, b) => a.title.localeCompare(b.title));
    case "used":
      return arr.sort((a, b) => (b.last_used || 0) - (a.last_used || 0));
    case "fav":
      return arr.sort((a, b) => (b.favorite ? 1 : 0) - (a.favorite ? 1 : 0));
    default:
      return arr;
  }
}

function filterList(list, query) {
  const q = (query || "").toLowerCase();
  if (!q) return list;
  return list.filter((t) =>
    [t.title, t.description, (t.tags || []).join(" ")].join(" ").toLowerCase().includes(q),
  );
}

function CardBody({ tool, query, onToggleFavorite }) {
  const [imgOk, setImgOk] = useState(Boolean(tool.icon_file));
  return (
    <>
      <div className="card-icon">
        {tool.icon_file && imgOk ? (
          <img src={toolIconFile(tool.icon_file)} alt="" onError={() => setImgOk(false)} />
        ) : tool.icon ? (
          <Emoji emoji={tool.icon} size={30} />
        ) : (
          <WolfIcon />
        )}
      </div>
      <div className="card-body">
        <span className="card-title">{highlightWithEmoji(tool.title, query)}</span>
      </div>
      <button
        type="button"
        className={"card-star" + (tool.favorite ? " on" : "")}
        title="Toggle favorite"
        aria-label={tool.favorite ? "Remove from favorites" : "Add to favorites"}
        onClick={(e) => {
          e.stopPropagation();
          e.preventDefault();
          onToggleFavorite(tool);
        }}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <Icon name="star" />
      </button>
    </>
  );
}

export default function HomeDashboard({ tools = [], app, onOpenTool, onToggleFavorite }) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState(readSort);
  const pickSort = (key) => {
    setSort(key);
    try {
      localStorage.setItem(SORT_KEY, key);
    } catch {
      // storage unavailable
    }
  };
  const bannerRef = useRef(null);
  useBluePulse(bannerRef);
  const list = sortList(filterList(tools, search), sort);
  return (
    <div className="page">
      <div className="container">
        <div className="banner">
          <h1 ref={bannerRef} className="banner-title"><EmojiText text={(app && app.title) || "Lycan Utilities"} /></h1>
          {app && app.subtitle ? <p className="banner-sub"><EmojiText text={app.subtitle} /></p> : null}
        </div>
        <div className="toolbar">
          <div className="search">
            <span className="search-icon"><Icon name="search" /></span>
            <input
              type="text"
              placeholder="Search tools or tags..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search ? (
              <button
                type="button"
                className="search-clear"
                aria-label="Clear search"
                onClick={() => setSearch("")}
              >
                <Icon name="x" />
              </button>
            ) : null}
          </div>
          <div className="sort-pills">
            {PILLS.map(([key, label, icon]) => (
              <button
                key={key}
                type="button"
                className={"pill" + (sort === key ? " active" : "")}
                onClick={() => pickSort(key)}
              >
                <Icon name={icon} />
                {label}
              </button>
            ))}
          </div>
        </div>
        <UtilityCardList
          items={list}
          getKey={(t) => t.id}
          onItemClick={onOpenTool}
          getTooltip={(t) => (t.description ? t.description : undefined)}
          renderCard={(tool) => <CardBody tool={tool} query={search} onToggleFavorite={onToggleFavorite} />}
          emptyState={
            <div className="empty-note">
              <div className="image-container">
                <img src="/assets/icons/wolf-sad.png" alt="Sad Wolf" className="empty-icon" />
                <div
                  className="overlay-blur"
                  style={{ backgroundImage: `url(/assets/icons/wolf-sad.png)` }}
                />
              </div>
              <p className="white-text">Utility search results not found</p>
            </div>
          }
        />
      </div>
    </div>
  );
}