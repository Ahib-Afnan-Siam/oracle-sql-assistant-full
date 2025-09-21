// src/components/DataTable.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Download,
  Copy,
  Maximize2,
  Minimize2,
  ArrowUpDown,
  Search,
  ChevronDown,
  BarChart,
  Table
} from "lucide-react";
import DataVisualization, { type DataVisualizationHandle } from "./DataVisualization";
import { exportExcel, exportPDF, toCSV } from "../utils/exportUtils";
import { motion, AnimatePresence } from "framer-motion";

type TableData = (string | number | null)[][]; // first row = headers

function isNumericValue(v: unknown): boolean {
  if (typeof v === "number") return true;
  if (typeof v !== "string") return false;
  const trimmed = v.replace(/,/g, "").trim();
  return trimmed !== "" && !isNaN(Number(trimmed));
}

// Small helper: reliably trigger a file download
function triggerDownload(url: string, filename: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
  setTimeout(() => {
    document.body.removeChild(a);
    if (url.startsWith("blob:")) URL.revokeObjectURL(url);
  }, 200);
}

export default function DataTable({ data }: { data: TableData }) {
  const headers = (data?.[0] as string[]) || [];
  const rawRows = (data || []).slice(1);

  // NEW: visualization state
  const [showVisualization, setShowVisualization] = useState(false);
  const dataVizRef = useRef<DataVisualizationHandle | null>(null);

  // Dropdown (export) state — single “Export” button that opens a menu
  const [exportOpen, setExportOpen] = useState(false);
  const exportRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!exportRef.current) return;
      if (!exportRef.current.contains(e.target as Node)) setExportOpen(false);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  // auto-detect numeric columns by sampling
  const numericCols = useMemo(() => {
    const sample = rawRows.slice(0, 25);
    return headers.map(
      (_, col) => sample.every((r) => isNumericValue(r[col]) || r[col] == null)
    );
  }, [headers, rawRows]);

  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ col: number; dir: "asc" | "desc" } | null>(
    null
  );
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [full, setFull] = useState(false); // ⬅ real fullscreen now

  // Lock body scroll + ESC to close when fullscreen
  useEffect(() => {
    if (!full) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFull(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [full]);

  const filtered = useMemo(() => {
    if (!query.trim()) return rawRows;
    const q = query.toLowerCase();
    return rawRows.filter((r) =>
      r.some((c) => String(c ?? "").toLowerCase().includes(q))
    );
  }, [query, rawRows]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const { col, dir } = sort;
    const mul = dir === "asc" ? 1 : -1;
    const copy = [...filtered];
    copy.sort((a, b) => {
      const va = a[col];
      const vb = b[col];
      const na = isNumericValue(va) ? Number(String(va).replace(/,/g, "")) : null;
      const nb = isNumericValue(vb) ? Number(String(vb).replace(/,/g, "")) : null;
      if (na !== null && nb !== null) return (na - nb) * mul;
      return String(va ?? "").localeCompare(String(vb ?? "")) * mul;
    });
    return copy;
  }, [filtered, sort]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const sliceStart = (currentPage - 1) * pageSize;
  const pageRows = sorted.slice(sliceStart, sliceStart + pageSize);

  // ---- EXPORTS ----
  const tableAll: (string | number | null)[][] = useMemo(
    () => [headers, ...sorted],
    [headers, sorted]
  );
  const csvAll = useMemo(() => toCSV(tableAll), [tableAll]);

  const handleCopyCSV = async () => {
    await navigator.clipboard.writeText(csvAll);
    setExportOpen(false);
  };
  const handleExportCSV = () => {
    const a = document.createElement("a");
    a.href = `data:text/csv;charset=utf-8,${encodeURIComponent(csvAll)}`;
    a.download = "table.csv";
    a.click();
    setExportOpen(false);
  };
  const handleExportExcel = () => {
    exportExcel([{ name: "Data", rows: tableAll }], "table.xlsx");
    setExportOpen(false);
  };
  const handleExportPDF = () => {
    exportPDF({
      title: "Table Export",
      subtitle: `Rows: ${sorted.length.toLocaleString()}`,
      tables: [{ heading: "Main Table", rows: tableAll }],
      fileName: "table.pdf",
    });
    setExportOpen(false);
  };

  // Chart exports (use DataVisualization ref)
  const exportChartImage = (fmt: "png" | "jpeg") => {
    const type = fmt === "png" ? "image/png" : "image/jpeg";
    const dataUrl = dataVizRef.current?.getChartDataUrl(type, 0.95);
    if (!dataUrl) return;
    triggerDownload(dataUrl, `chart.${fmt}`);
    setExportOpen(false);
  };

  const exportChartAndTablePDF = () => {
    const dataUrl =
      dataVizRef.current?.getChartDataUrl("image/png", 0.95) ?? null;
    if (!dataUrl) return;
    exportPDF({
      title: "Chart Report",
      subtitle: headers.join(", "),
      charts: [{ title: "Visualization", dataUrl, widthPx: 520, heightPx: 280 }],
      tables: [{ heading: "Underlying Data", rows: tableAll }],
      fileName: "chart_report.pdf",
    });
    setExportOpen(false);
  };

  // availability
  const chartAvailable = showVisualization && !!dataVizRef.current?.isReady?.();

  // ---- /EXPORTS ----

  const handleHeaderClick = (idx: number) => {
    setPage(1);
    setSort((s) => {
      if (!s || s.col !== idx) return { col: idx, dir: "asc" };
      return s.dir === "asc" ? { col: idx, dir: "desc" } : null;
    });
  };

  const formatCell = (v: any, col: number) => {
    if (v == null || v === "") return "—";
    if (numericCols[col] && isNumericValue(v)) {
      const n = Number(String(v).replace(/,/g, ""));
      return n.toLocaleString();
    }
    return String(v);
  };

  // ----- Toolbar (reused in normal + fullscreen) -----
  const Toolbar = (
    <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-4">
      {/* Left cluster */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-xs text-gray-600 mr-2">
          {sorted.length.toLocaleString()} row{sorted.length === 1 ? "" : "s"}
        </div>

        {/* Search */}
        <div className="relative w-full sm:w-auto">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search…"
            className="pl-8 pr-3 py-1.5 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-purple-500 w-full sm:w-32 md:w-40"
          />
        </div>

        {/* Page size */}
        <select
          value={pageSize}
          onChange={(e) => {
            setPageSize(Number(e.target.value));
            setPage(1);
          }}
          className="text-sm border rounded-lg py-1.5 px-2"
          title="Rows per page"
        >
          {[10, 25, 50, 100].map((n) => (
            <option key={n} value={n}>
              {n} / page
            </option>
          ))}
        </select>

        {/* Unified Export dropdown + Expand */}
        <div className="flex items-center gap-2">
          <div className="relative" ref={exportRef}>
            <button
              onClick={() => setExportOpen((o) => !o)}
              className="text-xs px-2 py-1.5 rounded-lg border bg-white hover:bg-gray-50 flex items-center gap-1 smooth-hover hover-lift"
              title="Export options"
              type="button"
              aria-haspopup="menu"
              aria-expanded={exportOpen}
            >
              Export <ChevronDown size={14} />
            </button>

            {exportOpen && (
              <div
                role="menu"
                className="absolute z-[120] mt-1 w-56 bg-white border border-gray-200 rounded-md shadow-lg py-1 text-sm"
              >
                {/* Best for this view */}
                <button
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 smooth-hover hover-lift"
                  title="Quick export for current view"
                  role="menuitem"
                  type="button"
                  onClick={() =>
                    chartAvailable ? exportChartImage("png") : handleExportExcel()
                  }
                >
                  Best for this view
                </button>

                <div className="my-1 border-t border-gray-200" />

                {/* Table group */}
                <div className="px-3 pt-1 pb-1 text-[11px] uppercase tracking-wide text-gray-500">
                  Table
                </div>
                <button
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 flex items-center gap-2 smooth-hover hover-lift"
                  onClick={handleCopyCSV}
                  title="Copy CSV to clipboard"
                  role="menuitem"
                  type="button"
                >
                  <Copy size={14} /> Copy CSV
                </button>
                <button
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 smooth-hover hover-lift"
                  onClick={handleExportCSV}
                  title="Download CSV"
                  role="menuitem"
                  type="button"
                >
                  CSV
                </button>
                <button
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 smooth-hover hover-lift"
                  onClick={handleExportExcel}
                  title="Download Excel (multi-sheet)"
                  role="menuitem"
                  type="button"
                >
                  Excel
                </button>
                <button
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 smooth-hover hover-lift"
                  onClick={handleExportPDF}
                  title="Download PDF"
                  role="menuitem"
                  type="button"
                >
                  PDF
                </button>

                {/* Chart group (only when available) */}
                <div className="my-1 border-t border-gray-200" />
                <div className="px-3 pt-1 pb-1 text-[11px] uppercase tracking-wide text-gray-500">
                  Chart
                </div>
                <button
                  type="button"
                  role="menuitem"
                  className={`w-full text-left px-3 py-2 ${
                    chartAvailable ? "hover:bg-gray-50" : "opacity-50 cursor-not-allowed"
                  } smooth-hover hover-lift`}
                  onClick={() => chartAvailable && exportChartImage("png")}
                  title={chartAvailable ? "Download chart as PNG" : "Open Visualize Data first"}
                >
                  PNG
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className={`w-full text-left px-3 py-2 ${
                    chartAvailable ? "hover:bg-gray-50" : "opacity-50 cursor-not-allowed"
                  } smooth-hover hover-lift`}
                  onClick={() => chartAvailable && exportChartImage("jpeg")}
                  title={chartAvailable ? "Download chart as JPEG" : "Open Visualize Data first"}
                >
                  JPEG
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className={`w-full text-left px-3 py-2 ${
                    chartAvailable ? "hover:bg-gray-50" : "opacity-50 cursor-not-allowed"
                  } smooth-hover hover-lift`}
                  onClick={() => chartAvailable && exportChartAndTablePDF()}
                  title={
                    chartAvailable
                      ? "Export chart and table to a PDF"
                      : "Open Visualize Data first"
                  }
                >
                  PDF (Chart + Table)
                </button>
              </div>
            )}
          </div>

          <button
            onClick={() => setFull((v) => !v)}
            className="text-xs px-2 py-1.5 rounded-lg border bg-white hover:bg-gray-50 flex items-center gap-1 smooth-hover hover-lift"
            title={full ? "Exit fullscreen" : "Expand"}
            type="button"
          >
            {full ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            <span className="hidden sm:inline">{full ? "Close" : "Expand"}</span>
          </button>
          {/* ESC key hint for fullscreen mode */}
          {full && (
            <div className="hidden sm:flex items-center gap-1 text-xs text-gray-500">
              <kbd className="bg-gray-100 border border-gray-300 rounded px-1 py-0.5">ESC</kbd>
              <span>to exit</span>
            </div>
          )}
        </div>
      </div>

      {/* Right: Visualize toggle */}
      <div className="flex justify-between items-center w-full md:w-auto">
        {!showVisualization ? (
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowVisualization(true)}
            className="px-3 py-1 bg-primary-purple-600 text-white rounded hover:bg-primary-purple-700 text-sm w-full sm:w-auto flex items-center justify-center gap-1 smooth-hover hover-lift"
            type="button"
          >
            <BarChart size={16} />
            Visualize Data
          </motion.button>
        ) : (
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowVisualization(false)}
            className="px-3 py-1 bg-gray-700 text-white rounded hover:bg-gray-800 text-sm w-full sm:w-auto flex items-center justify-center gap-1 smooth-hover hover-lift"
            type="button"
          >
            <Table size={16} />
            Back to Table
          </motion.button>
        )}
      </div>
    </div>
  );

  // ----- Main area (reused in normal + fullscreen) -----
  const MainArea = (
    <>
      <AnimatePresence mode="wait">
        {showVisualization ? (
          <motion.div
            key="visualization"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3 }}
            className="w-full"
          >
            <DataVisualization
              ref={dataVizRef}
              columns={headers}
              rows={sorted}
            />
          </motion.div>
        ) : (
          <motion.div
            key="table"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{ duration: 0.3 }}
            className="w-full"
          >
            {/* ✅ Critical container: forces horizontal scroll inside the bubble */}
            <div className="w-full overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    {headers.map((h, idx) => (
                      <th
                        key={idx}
                        onClick={() => handleHeaderClick(idx)}
                        className="px-3 py-2 text-left text-sm font-medium text-gray-700 whitespace-nowrap cursor-pointer hover:bg-gray-50 smooth-hover hover-lift"
                      >
                        <div className="flex items-center">
                          {h} <ArrowUpDown className="ml-1 h-3 w-3" />
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row, rowIdx) => (
                    <tr key={rowIdx} className={rowIdx % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                      {row.map((cell, cellIdx) => (
                        <td
                          key={cellIdx}
                          className="px-3 py-2 text-sm text-gray-900 whitespace-nowrap max-w-[150px] truncate"
                          title={String(cell ?? "")}
                        >
                          {formatCell(cell, cellIdx)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination */}
              <div className="flex items-center justify-between border-t border-gray-200 bg-white px-3 py-3 sm:px-6">
                <div className="flex flex-1 justify-between sm:hidden">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage <= 1}
                    className="relative inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 smooth-hover hover-lift"
                    type="button"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage >= totalPages}
                    className="relative ml-3 inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 smooth-hover hover-lift"
                    type="button"
                  >
                    Next
                  </button>
                </div>

                <div className="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm text-gray-700">
                      Showing <span className="font-medium">{sliceStart + 1}</span> to{" "}
                      <span className="font-medium">{sliceStart + pageRows.length}</span> of{" "}
                      <span className="font-medium">{sorted.length}</span> results
                    </p>
                  </div>
                  <div>
                    <nav className="isolate inline-flex -space-x-px rounded-md shadow-sm" aria-label="Pagination">
                      <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={currentPage <= 1}
                        className="relative inline-flex items-center rounded-l-md px-2 py-2 text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0 smooth-hover hover-lift"
                        type="button"
                      >
                        Previous
                      </button>
                      {[...Array(totalPages)].map((_, i) => {
                        const pageNum = i + 1;
                        if (
                          pageNum === 1 ||
                          pageNum === totalPages ||
                          (pageNum >= currentPage - 1 && pageNum <= currentPage + 1)
                        ) {
                          return (
                            <button
                              key={pageNum}
                              onClick={() => setPage(pageNum)}
                              className={`relative inline-flex items-center px-4 py-2 text-sm font-semibold ${
                                currentPage === pageNum
                                  ? "z-10 bg-primary-purple-600 text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-purple-600"
                                  : "text-gray-900 ring-1 ring-inset ring-gray-300 hover:bg-primary-purple-50 focus:outline-offset-0 smooth-hover hover-lift"
                              }`}
                              type="button"
                            >
                              {pageNum}
                            </button>
                          );
                        } else if (pageNum === currentPage - 2 || pageNum === currentPage + 2) {
                          return (
                            <span
                              key={pageNum}
                              className="relative inline-flex items-center px-4 py-2 text-sm font-semibold text-gray-700 ring-1 ring-inset ring-gray-300 focus:outline-offset-0"
                            >
                              ...
                            </span>
                          );
                        }
                        return null;
                      })}
                      <button
                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                        disabled={currentPage >= totalPages}
                        className="relative inline-flex items-center rounded-r-md px-2 py-2 text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0 smooth-hover hover-lift"
                        type="button"
                      >
                        Next
                      </button>
                    </nav>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );

  // ----- Render normal vs fullscreen -----
  if (full) {
    return (
      <>
        {/* Backdrop (click to close) */}
        <div className="fixed inset-0 z-[90] bg-black/40" onClick={() => setFull(false)} />
        {/* Fullscreen container */}
        <div className="fixed inset-4 z-[100] bg-white rounded-2xl shadow-2xl p-4 flex flex-col overflow-hidden">
          {/* Enhanced fullscreen header with prominent close button */}
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-800">Data Table (Fullscreen)</h2>
            <div className="flex items-center gap-2">
              <div className="hidden sm:flex items-center gap-1 text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                <kbd className="bg-white border border-gray-300 rounded px-1 py-0.5">ESC</kbd>
                <span>to exit</span>
              </div>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => setFull(false)}
                className="flex items-center gap-1 bg-red-500 hover:bg-red-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium shadow-md smooth-hover hover-lift"
              >
                <Minimize2 size={16} />
                <span className="hidden sm:inline">Exit Fullscreen</span>
              </motion.button>
            </div>
          </div>
          {Toolbar}
          <div className="flex-1 min-h-0 overflow-auto">{MainArea}</div>
        </div>
      </>
    );
  }

  // Normal (inline) container
  return (
    <div className="rounded-xl bg-white/95 shadow-sm p-3 overflow-hidden">
      {Toolbar}
      {MainArea}
    </div>
  );
}
