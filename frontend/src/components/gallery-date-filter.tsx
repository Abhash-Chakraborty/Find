"use client";

import { Calendar, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { DateRangePreset, SortOrder } from "@/lib/api";

interface GalleryDateFilterProps {
  sortOrder: SortOrder;
  dateRange: DateRangePreset | undefined | null;
  dateStart: string | null;
  dateEnd: string | null;
  onSortOrderChange: (order: SortOrder) => void;
  onDateFilterChange: (
    preset: DateRangePreset | null,
    start: string | null,
    end: string | null,
  ) => void;
}

export function GalleryDateFilter({
  sortOrder,
  dateRange,
  dateStart,
  dateEnd,
  onSortOrderChange,
  onDateFilterChange,
}: GalleryDateFilterProps) {
  const [showSortMenu, setShowSortMenu] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [customStart, setCustomStart] = useState(dateStart || "");
  const [customEnd, setCustomEnd] = useState(dateEnd || "");
  const sortMenuRef = useRef<HTMLDivElement>(null);
  const datePickerRef = useRef<HTMLDivElement>(null);

  // Sync local state when props change (e.g., URL state restoration, browser history)
  useEffect(() => {
    setCustomStart(dateStart || "");
    setCustomEnd(dateEnd || "");
  }, [dateStart, dateEnd]);

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (sortMenuRef.current && !sortMenuRef.current.contains(target)) {
        setShowSortMenu(false);
      }
      if (datePickerRef.current && !datePickerRef.current.contains(target)) {
        setShowDatePicker(false);
      }
    };

    if (showSortMenu || showDatePicker) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
      };
    }
  }, [showSortMenu, showDatePicker]);

  const getDateRangeLabel = () => {
    if (!dateRange) return "All dates";
    if (dateRange === "last_30_days") return "Last 30 days";
    if (dateRange === "last_60_days") return "Last 60 days";
    if (dateRange === "last_90_days") return "Last 90 days";
    if (dateRange === "custom" && (customStart || customEnd)) {
      const parts = [];
      if (customStart) parts.push(customStart);
      if (customEnd) parts.push(customEnd);
      return parts.join(" → ");
    }
    return "Custom range";
  };

  const handleCustomDateApply = () => {
    if (customStart || customEnd) {
      onDateFilterChange("custom", customStart || null, customEnd || null);
    } else {
      onDateFilterChange(null, null, null);
    }
    setShowDatePicker(false);
  };

  const handleClearCustom = () => {
    setCustomStart("");
    setCustomEnd("");
    onDateFilterChange(null, null, null);
    setShowDatePicker(false);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Sort Order Dropdown */}
      <div className="relative" ref={sortMenuRef}>
        <button
          type="button"
          onClick={() => setShowSortMenu(!showSortMenu)}
          className="inline-flex items-center gap-2 rounded-full border border-[var(--frost)] bg-transparent px-3 py-2 text-xs font-medium text-[color:var(--silver)] transition hover:bg-[color:var(--frost-soft)] hover:text-[color:var(--near-white)]"
          title="Sort by upload date"
        >
          <span>
            {sortOrder === "newest" ? "Newest first" : "Oldest first"}
          </span>
          <ChevronDown
            className={`h-3.5 w-3.5 transition ${showSortMenu ? "rotate-180" : ""}`}
          />
        </button>

        {/* Sort dropdown menu */}
        {showSortMenu && (
          <div className="absolute right-0 top-full mt-1 z-10 rounded-lg border border-[var(--frost)] bg-[color:var(--surface)] shadow-lg">
            <button
              type="button"
              onClick={() => {
                onSortOrderChange("newest");
                setShowSortMenu(false);
              }}
              className={`block w-full rounded-t-lg px-4 py-2 text-left text-xs font-medium transition ${
                sortOrder === "newest"
                  ? "bg-[color:var(--frost-soft)] text-[color:var(--near-white)]"
                  : "text-[color:var(--silver)] hover:bg-[color:var(--frost-soft)]"
              }`}
            >
              Newest first
            </button>
            <button
              type="button"
              onClick={() => {
                onSortOrderChange("oldest");
                setShowSortMenu(false);
              }}
              className={`block w-full rounded-b-lg px-4 py-2 text-left text-xs font-medium transition ${
                sortOrder === "oldest"
                  ? "bg-[color:var(--frost-soft)] text-[color:var(--near-white)]"
                  : "text-[color:var(--silver)] hover:bg-[color:var(--frost-soft)]"
              }`}
            >
              Oldest first
            </button>
          </div>
        )}
      </div>

      {/* Date Range Dropdown */}
      <div className="relative" ref={datePickerRef}>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-full border border-[var(--frost)] bg-transparent px-3 py-2 text-xs font-medium text-[color:var(--silver)] transition hover:bg-[color:var(--frost-soft)] hover:text-[color:var(--near-white)]"
          onClick={() => setShowDatePicker(!showDatePicker)}
          title="Filter by date range"
        >
          <Calendar className="h-3.5 w-3.5" />
          <span>{getDateRangeLabel()}</span>
          <ChevronDown
            className={`h-3.5 w-3.5 transition ${showDatePicker ? "rotate-180" : ""}`}
          />
        </button>

        {/* Date dropdown menu */}
        {showDatePicker && (
          <div className="absolute right-0 top-full mt-1 z-10 w-64 rounded-lg border border-[var(--frost)] bg-[color:var(--surface)] shadow-lg">
            <div className="space-y-2 p-3">
              {/* Preset buttons */}
              {[
                { label: "All dates", value: null },
                { label: "Last 30 days", value: "last_30_days" as const },
                { label: "Last 60 days", value: "last_60_days" as const },
                { label: "Last 90 days", value: "last_90_days" as const },
              ].map((option) => (
                <button
                  key={option.label}
                  type="button"
                  onClick={() => {
                    onDateFilterChange(option.value, null, null);
                    setShowDatePicker(false);
                    setCustomStart("");
                    setCustomEnd("");
                  }}
                  className={`block w-full rounded px-3 py-2 text-left text-xs font-medium transition ${
                    dateRange === option.value && !customStart && !customEnd
                      ? "bg-[color:var(--frost-soft)] text-[color:var(--near-white)]"
                      : "text-[color:var(--silver)] hover:bg-[color:var(--frost-soft)]"
                  }`}
                >
                  {option.label}
                </button>
              ))}

              <fieldset className="border-t border-[var(--frost)] pt-3">
                <legend className="mb-2 text-xs font-medium text-[color:var(--silver)]">
                  Custom date range
                </legend>
                <div className="space-y-2">
                  <label htmlFor="custom-date-start" className="sr-only">
                    Start date
                  </label>
                  <input
                    id="custom-date-start"
                    type="date"
                    value={customStart}
                    onChange={(e) => setCustomStart(e.target.value)}
                    className="w-full rounded border border-[var(--frost)] bg-[color:var(--surface-soft)] px-2 py-1 text-xs text-[color:var(--near-white)] placeholder-[color:var(--muted)]"
                    placeholder="Start date"
                  />
                  <label htmlFor="custom-date-end" className="sr-only">
                    End date
                  </label>
                  <input
                    id="custom-date-end"
                    type="date"
                    value={customEnd}
                    onChange={(e) => setCustomEnd(e.target.value)}
                    className="w-full rounded border border-[var(--frost)] bg-[color:var(--surface-soft)] px-2 py-1 text-xs text-[color:var(--near-white)] placeholder-[color:var(--muted)]"
                    placeholder="End date"
                  />
                </div>
              </fieldset>

              {/* Action buttons */}
              <div className="border-t border-[var(--frost)] pt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowDatePicker(false)}
                  className="flex-1 rounded px-2 py-1 text-xs font-medium text-[color:var(--silver)] hover:bg-[color:var(--frost-soft)]"
                >
                  Cancel
                </button>
                {(customStart || customEnd) && (
                  <button
                    type="button"
                    onClick={handleClearCustom}
                    className="flex-1 rounded px-2 py-1 text-xs font-medium text-[color:var(--silver)] hover:bg-[color:var(--frost-soft)]"
                  >
                    Clear
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleCustomDateApply}
                  disabled={!customStart && !customEnd}
                  className="flex-1 rounded bg-[color:var(--blue)] px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
                >
                  Apply
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
