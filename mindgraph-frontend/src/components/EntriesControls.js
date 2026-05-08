import { useEffect, useRef, useState } from "react";
import "../styles/entries.css";

const FILTER_DEFS = [
  { key: "mood",     label: "Mood",     type: "select" },
  { key: "person",   label: "Person",   type: "select" },
  { key: "date",     label: "Dates",    type: "daterange" },
  { key: "category", label: "Category", type: "select" },
  { key: "search",   label: "Search",   type: "text" },
];

// Hand-drawn SVG circle for active page number
function HandCircle() {
  return (
    <svg className="entries-page-circle" viewBox="0 0 26 26">
      <path
        d="M 13 2 C 19 2, 23 6, 23 13 C 23 19, 19 23, 13 23 C 7 23, 2 19, 2 13 C 2 7, 6 2, 13 2 Z"
        fill="none"
        stroke="#5c4a2a"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeDasharray="0.5 0.8"
      />
    </svg>
  );
}

export default function EntriesControls({
  filters,
  onFiltersChange,
  filterOptions,
  page,
  totalCount,
  pageSize,
  onPageChange,
  onLoadMore,
  loadingMore,
}) {
  const [openFilter, setOpenFilter] = useState(null);
  const [searchDraft, setSearchDraft] = useState(filters.search || "");
  const debounceRef = useRef(null);
  const popoverRef = useRef(null);

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const hasActiveFilter = Object.values(filters).some(Boolean);

  // Debounce search input
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (searchDraft !== filters.search) {
        onFiltersChange({ ...filters, search: searchDraft || undefined });
      }
    }, 400);
    return () => clearTimeout(debounceRef.current);
  }, [searchDraft]); // eslint-disable-line react-hooks/exhaustive-deps

  // Close popover on outside click
  useEffect(() => {
    if (!openFilter) return;
    function handler(e) {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) {
        setOpenFilter(null);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [openFilter]);

  function setFilter(key, val) {
    onFiltersChange({ ...filters, [key]: val || undefined });
  }

  function clearAll() {
    setSearchDraft("");
    onFiltersChange({});
    setOpenFilter(null);
  }

  function renderPopover(def) {
    if (def.type === "select") {
      const opts = filterOptions[def.key] || [];
      return (
        <select
          value={filters[def.key] || ""}
          onChange={(e) => { setFilter(def.key, e.target.value); setOpenFilter(null); }}
          autoFocus
        >
          <option value="">All</option>
          {opts.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      );
    }

    if (def.type === "daterange") {
      return (
        <div className="entries-date-range">
          <label>From</label>
          <input
            type="date"
            value={filters.date_from || ""}
            onChange={(e) => setFilter("date_from", e.target.value)}
          />
          <label style={{ marginTop: 6 }}>To</label>
          <input
            type="date"
            value={filters.date_to || ""}
            onChange={(e) => setFilter("date_to", e.target.value)}
          />
        </div>
      );
    }

    if (def.type === "text") {
      return (
        <input
          type="text"
          placeholder="Search entries..."
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
          autoFocus
        />
      );
    }

    return null;
  }

  // Build page number array with ellipsis
  function buildPageNums(current, total) {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    const pages = [];
    pages.push(1);
    if (current > 3) pages.push("...");
    for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) {
      pages.push(p);
    }
    if (current < total - 2) pages.push("...");
    pages.push(total);
    return pages;
  }

  const pageNums = buildPageNums(page, totalPages);

  return (
    <div className="entries-controls">
      {/* Filter tab row */}
      <div className="entries-filter-row">
        {FILTER_DEFS.map((def) => {
          const isActive = def.key === "date"
            ? !!(filters.date_from || filters.date_to)
            : !!(filters[def.key]);
          const isOpen = openFilter === def.key;

          return (
            <div key={def.key} style={{ position: "relative" }}>
              <button
                className={`entries-filter-tab${isActive ? " active" : ""}`}
                onClick={() => setOpenFilter(isOpen ? null : def.key)}
              >
                {def.label}
                {isActive && <span style={{ fontSize: 8, marginLeft: 2 }}>&#9679;</span>}
              </button>
              {isOpen && (
                <div className="entries-filter-popover" ref={popoverRef}>
                  {renderPopover(def)}
                </div>
              )}
            </div>
          );
        })}

        {hasActiveFilter && (
          <button
            className="entries-filter-clear"
            onClick={clearAll}
            title="Clear all filters"
          >
            &times;
          </button>
        )}
      </div>

      <hr className="entries-rule" />

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="entries-pagination">
          <button
            className="entries-page-nav"
            onClick={() => onPageChange(page - 1)}
            disabled={page === 1}
          >
            &larr; prev
          </button>

          <div className="entries-page-numbers">
            {pageNums.map((p, i) =>
              p === "..." ? (
                <span key={`ellipsis-${i}`} className="entries-page-ellipsis">...</span>
              ) : (
                <button
                  key={p}
                  className={`entries-page-num${p === page ? " active" : ""}`}
                  onClick={() => onPageChange(p)}
                >
                  {p === page && <HandCircle />}
                  <span style={{ position: "relative", zIndex: 1 }}>{p}</span>
                </button>
              )
            )}
          </div>

          <button
            className="entries-page-nav"
            onClick={() => onPageChange(page + 1)}
            disabled={page === totalPages}
          >
            next &rarr;
          </button>
        </div>
      )}

      {/* Load more */}
      {page < totalPages && (
        <button
          className="entries-load-more"
          onClick={onLoadMore}
          disabled={loadingMore}
        >
          {loadingMore ? "loading..." : "↓ load more"}
        </button>
      )}
    </div>
  );
}
