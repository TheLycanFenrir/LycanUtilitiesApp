import { useRef, useState } from "react";
import { Icon } from "../components/common/SvgIcon.jsx";
import { highlight } from "../components/settings/highlight.jsx";
import useCyanPulse from "../hooks/useCyanPulse.js";

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

function Card({ tool, onOpen, onToggleFavorite, query }) {
  const [imgOk, setImgOk] = useState(Boolean(tool.icon_file));
  return (
    <article
      className="card"
      data-tooltip={tool.description || undefined}
      onClick={onOpen}
    >
      <div className="card-icon">
        {tool.icon_file && imgOk ? (
          <img src={"assets/icons/" + tool.icon_file} alt="" onError={() => setImgOk(false)} />
        ) : (
          <span style={{ fontSize: 30 }}>{tool.icon || "?"}</span>
        )}
      </div>
      <div className="card-body">
        <span className="card-title">{highlight(tool.title, query)}</span>
      </div>
      <button
        type="button"
        className={"card-star" + (tool.favorite ? " on" : "")}
        title="Toggle favorite"
        onClick={(e) => {
          e.stopPropagation();
          e.preventDefault();
          onToggleFavorite(tool);
        }}
      >
        <Icon name="star" />
      </button>
    </article>
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
  useCyanPulse(bannerRef);
  const list = sortList(filterList(tools, search), sort);
  return (
    <div className="page">
      <div className="container">
        <div className="banner">
          <h1 ref={bannerRef} className="banner-title">{(app && app.title) || "Lycan Utilities"}</h1>
          {app && app.subtitle ? <p className="banner-sub">{app.subtitle}</p> : null}
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
        <div className="card-grid">
          {list.length === 0 ? (
            <div className="empty-note">Utility search results not found</div>
          ) : (
            list.map((tool) => (
              <Card
                key={tool.id}
                tool={tool}
                query={search}
                onOpen={() => onOpenTool(tool)}
                onToggleFavorite={onToggleFavorite}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}