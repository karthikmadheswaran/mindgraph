import { useEffect, useRef, useState } from "react";
import "../styles/entries.css";

const FILTER_DEFS = [
  { key: "mood",     label: "Mood",     type: "select" },
  { key: "person",   label: "Person",   type: "select" },
  { key: "date",     label: "Dates",    type: "daterange" },
  { key: "category", label: "Category", type: "select" },
  { key: "search",   label: "Search",   type: "text" },
];

// Filters only (Journal v2). Pagination moved to the timeline's infinite
// scroll — the old page-number strip and "load more" button used to render
// SIMULTANEOUSLY (bug), and both are gone with it.
export default function EntriesControls({
  filters,
  onFiltersChange,
  filterOptions,
}) {
  const [openFilter, setOpenFilter] = useState(null);
  const [searchDraft, setSearchDraft] = useState(filters.search || "");
  const debounceRef = useRef(null);
  const popoverRef = useRef(null);

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
    </div>
  );
}
