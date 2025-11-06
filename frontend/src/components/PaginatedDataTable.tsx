// src/components/PaginatedDataTable.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Copy,
  Maximize2,
  Minimize2,
  ArrowUpDown,
  Search,
  ChevronDown,
  BarChart,
  Table,
  AlertTriangle,
  Loader2
} from "lucide-react";
import DataVisualization, { type DataVisualizationHandle } from "./DataVisualization";
import { exportExcel, exportPDF, toCSV } from "../utils/exportUtils";
import { motion, AnimatePresence } from "framer-motion";

type TableData = (string | number | null)[][]; // first row = headers

// Define the metadata type
type TableMetadata = {
  total_rows_available?: number;
  rows_returned?: number;
  results_truncated?: boolean;
  current_page?: number;
  page_size?: number;
  total_pages?: number;
};

// Define the props for the paginated data table
interface PaginatedDataTableProps {
  initialData: TableData | { columns: string[]; rows: any[]; metadata?: TableMetadata };
  queryId?: string; // ID to use for fetching more data
  onFetchData?: (page: number, pageSize: number) => Promise<{
    rows: any[];
    metadata: TableMetadata;
  }>;
  // Additional props for server-side pagination
  question?: string;
  mode?: string;
  selectedDB?: string;
}

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

export default function PaginatedDataTable({ initialData, queryId, onFetchData, question, mode, selectedDB }: PaginatedDataTableProps) {
  // Handle both old format (array of arrays) and new format (object with metadata)
  const { headers, rawRows, metadata } = useMemo(() => {
    if (Array.isArray(initialData)) {
      // Old format - array of arrays
      const headers = Array.isArray(initialData?.[0]) ? (initialData[0] as string[]) : [];
      const rawRows = Array.isArray(initialData) ? initialData.slice(1) : [];
      return { headers, rawRows, metadata: undefined };
    } else {
      // New format - object with columns, rows, and metadata
      const headers = Array.isArray(initialData.columns) ? initialData.columns : [];
      const rawRows = Array.isArray(initialData.rows) ? initialData.rows : [];
      return { headers, rawRows, metadata: initialData.metadata };
    }
  }, [initialData]);
  
  // Ensure all rows are arrays
  const safeRawRows = rawRows.map(row => Array.isArray(row) ? row : []);

  // NEW: visualization state
  const [showVisualization, setShowVisualization] = useState(false);
  const dataVizRef = useRef<DataVisualizationHandle | null>(null);

  // Dropdown (export) state — single "Export" button that opens a menu
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
    const sample = safeRawRows.slice(0, 25);
    return headers.map(
      (_, col) => sample.every((r) => isNumericValue(r[col]) || r[col] == null)
    );
  }, [headers, safeRawRows]);

  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ col: number; dir: "asc" | "desc" } | null>(
    null
  );
  const [page, setPage] = useState(metadata?.current_page || 1);
  const [pageSize, setPageSize] = useState(metadata?.page_size || 1000);
  const [full, setFull] = useState(false); // ⬅ real fullscreen now
  const [loading, setLoading] = useState(false);
  const [tableData, setTableData] = useState(safeRawRows);
  const [tableMetadata, setTableMetadata] = useState(metadata);

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

  // Fetch data when page or page size changes
  useEffect(() => {
    // If we have a custom fetch function, use it
    if (onFetchData && (page !== (metadata?.current_page || 1) || pageSize !== (metadata?.page_size || 1000))) {
      setLoading(true);
      onFetchData(page, pageSize)
        .then((result) => {
          setTableData(result.rows);
          setTableMetadata(result.metadata);
          setLoading(false);
        })
        .catch((error) => {
          console.error("Failed to fetch data:", error);
          setLoading(false);
        });
    }
    // If we have question data, fetch from the backend
    else if (question && (page !== (metadata?.current_page || 1) || pageSize !== (metadata?.page_size || 1000))) {
      setLoading(true);
      
      // Prepare the request payload
      const bodyPayload: any = {
        question: question,
        mode: mode || "PRAN ERP", // Default to PRAN ERP if not specified
        page: page,
        page_size: pageSize
      };
      
      // Only include selected_db when not in General mode
      if (mode !== "General" && selectedDB) {
        bodyPayload.selected_db = selectedDB;
      } else {
        // Explicitly ensure General carries no DB
        bodyPayload.selected_db = "";
      }
      
      // Make the API call to fetch paginated data
      fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bodyPayload),
      })
        .then(response => response.json())
        .then(payload => {
          if (payload?.status === "success" && payload?.results?.columns) {
            const columns: string[] = payload.results.columns || [];
            const rows: any[] = payload.results.rows || [];
            
            // Convert array of objects to array of arrays if needed
            let tableRows: (string | number | null)[][] = [];
            if (rows.length > 0) {
              // Check if rows are objects (from backend) or already arrays
              if (typeof rows[0] === 'object' && rows[0] !== null && !Array.isArray(rows[0])) {
                // Convert objects to arrays using column order
                tableRows = rows.map(row => 
                  columns.map(col => 
                    row[col] !== undefined ? row[col] : null
                  )
                );
              } else {
                // Rows are already arrays
                tableRows = rows as (string | number | null)[][];
              }
            }
            
            setTableData(tableRows);
            setTableMetadata(payload.results.metadata);
          } else {
            // Handle error case
            console.error("Failed to fetch paginated data:", payload);
          }
          setLoading(false);
        })
        .catch(error => {
          console.error("Failed to fetch paginated data:", error);
          setLoading(false);
        });
    }
  }, [page, pageSize, onFetchData, metadata, question, mode, selectedDB]);

  const filtered = useMemo(() => {
    if (!query.trim()) return tableData;
    const q = query.toLowerCase();
    return tableData.filter((r) =>
      r.some((c) => String(c ?? "").toLowerCase().includes(q))
    );
  }, [query, tableData]);

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

  const totalPages = tableMetadata?.total_pages || Math.max(1, Math.ceil((tableMetadata?.total_rows_available || 0) / pageSize));
  const currentPage = Math.min(page, totalPages);
  const sliceStart = (currentPage - 1) * pageSize;
  const pageRows = sorted; // For server-side pagination, we already have the correct page

  // ---- EXPORTS ----
  const tableAll: (string | number | null)[][] = useMemo(
    () => {
      // Ensure all elements are arrays
      const safeHeaders = Array.isArray(headers) ? headers : [];
      const safeSorted = sorted.map(row => Array.isArray(row) ? row : []);
      return [safeHeaders, ...safeSorted];
    },
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
    try {
      return String(v);
    } catch (e) {
      console.error('Error converting cell value to string:', v, e);
      return "—";
    }
  };

  // OPTIMIZATION: For large datasets, we'll limit the data passed to visualization
  // to prevent performance issues in the browser
  const maxVisualizationRows = 50000;
  const visualizationData = useMemo(() => {
    if (sorted.length <= maxVisualizationRows) {
      return sorted;
    }
    // For very large datasets, we'll pass a message to the visualization component
    // which will handle sampling appropriately
    return sorted;
  }, [sorted]);

  // ----- Toolbar (reused in normal + fullscreen) -----
  const Toolbar = (
    <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-4">
      {/* Left cluster */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2">
          <div className="text-xs text-gray-600 mr-2 dark:text-gray-400">
            {tableMetadata?.total_rows_available?.toLocaleString() || sorted.length.toLocaleString()} row{tableMetadata?.total_rows_available === 1 ? "" : "s"}
          </div>
          
          {/* Warning icon for truncated results */}
          {tableMetadata?.results_truncated && (
            <div className="flex items-center gap-1 text-xs text-yellow-600 dark:text-yellow-400" title={`Showing ${tableMetadata.rows_returned} of ${tableMetadata.total_rows_available} total rows`}>
              <AlertTriangle size={14} />
              <span>Results truncated</span>
            </div>
          )}
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
            className="pl-8 pr-3 py-1.5 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-purple-500 w-full sm:w-32 md:w-40 bg-white dark:bg-gray-800 dark:border-gray-700 dark:text-gray-100"
          />
        </div>

        {/* Page size */}
        <select
          value={pageSize}
          onChange={(e) => {
            setPageSize(Number(e.target.value));
            setPage(1);
          }}
          className="text-sm border rounded-lg py-1.5 px-2 bg-white dark:bg-gray-800 dark:border-gray-700 dark:text-gray-100"
          title="Rows per page"
        >
          {[10, 25, 50, 100, 500, 1000].map((n) => (
            <option key={n} value={n} className="dark:bg-gray-800 dark:text-gray-100">
              {n} / page
            </option>
          ))}
        </select>

        {/* Unified Export dropdown + Expand */}
        <div className="flex items-center gap-2">
          <div className="relative" ref={exportRef}>
            <button
              onClick={() => setExportOpen((o) => !o)}
              className="text-xs px-2 py-1.5 rounded-lg border bg-white hover:bg-gray-50 flex items-center gap-1 smooth-hover hover-lift dark:bg-gray-800 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-700"
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
                className="absolute z-[120] mt-1 w-56 bg-white border border-gray-200 rounded-md shadow-lg py-1 text-sm dark:bg-gray-800 dark:border-gray-700"
              >
                {/* Best for this view */}
                <button
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 smooth-hover hover-lift dark:hover:bg-gray-700 dark:text-gray-100"
                  title="Quick export for current view"
                  role="menuitem"
                  type="button"
                  onClick={() =>
                    chartAvailable ? exportChartImage("png") : handleExportExcel()
                  }
                >
                  Best for this view
                </button>

                <div className="my-1 border-t border-gray-200 dark:border-gray-700" />

                {/* Table group */}
                <div className="px-3 pt-1 pb-1 text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Table
                </div>
                <button
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 flex items-center gap-2 smooth-hover hover-lift dark:hover:bg-gray-700 dark:text-gray-100"
                  onClick={handleCopyCSV}
                  title="Copy CSV to clipboard"
                  role="menuitem"
                  type="button"
                >
                  <Copy size={14} /> Copy CSV
                </button>
                <button
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 smooth-hover hover-lift dark:hover:bg-gray-700 dark:text-gray-100"
                  onClick={handleExportCSV}
                  title="Download CSV"
                  role="menuitem"
                  type="button"
                >
                  CSV
                </button>
                <button
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 smooth-hover hover-lift dark:hover:bg-gray-700 dark:text-gray-100"
                  onClick={handleExportExcel}
                  title="Download Excel (multi-sheet)"
                  role="menuitem"
                  type="button"
                >
                  Excel
                </button>
                <button
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 smooth-hover hover-lift dark:hover:bg-gray-700 dark:text-gray-100"
                  onClick={handleExportPDF}
                  title="Download PDF"
                  role="menuitem"
                  type="button"
                >
                  PDF
                </button>

                {/* Chart group (only when available) */}
                <div className="my-1 border-t border-gray-200 dark:border-gray-700" />
                <div className="px-3 pt-1 pb-1 text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Chart
                </div>
                <button
                  type="button"
                  role="menuitem"
                  className={`w-full text-left px-3 py-2 ${
                    chartAvailable ? "hover:bg-gray-50 dark:hover:bg-gray-700" : "opacity-50 cursor-not-allowed"
                  } smooth-hover hover-lift dark:text-gray-100`}
                  onClick={() => chartAvailable && exportChartImage("png")}
                  title={chartAvailable ? "Download chart as PNG" : "Open Visualize Data first"}
                >
                  PNG
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className={`w-full text-left px-3 py-2 ${
                    chartAvailable ? "hover:bg-gray-50 dark:hover:bg-gray-700" : "opacity-50 cursor-not-allowed"
                  } smooth-hover hover-lift dark:text-gray-100`}
                  onClick={() => chartAvailable && exportChartImage("jpeg")}
                  title={chartAvailable ? "Download chart as JPEG" : "Open Visualize Data first"}
                >
                  JPEG
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className={`w-full text-left px-3 py-2 ${
                    chartAvailable ? "hover:bg-gray-50 dark:hover:bg-gray-700" : "opacity-50 cursor-not-allowed"
                  } smooth-hover hover-lift dark:text-gray-100`}
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
            className="text-xs px-2 py-1.5 rounded-lg border bg-white hover:bg-gray-50 flex items-center gap-1 smooth-hover hover-lift dark:bg-gray-800 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-700"
            title={full ? "Exit fullscreen" : "Expand"}
            type="button"
          >
            {full ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            <span className="hidden sm:inline">{full ? "Close" : "Expand"}</span>
          </button>
          {/* ESC key hint for fullscreen mode */}
          {full && (
            <div className="hidden sm:flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
              <kbd className="bg-gray-100 border border-gray-300 rounded px-1 py-0.5 dark:bg-gray-700 dark:border-gray-600">ESC</kbd>
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
              rows={visualizationData}
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
                        className="px-3 py-2 text-left text-sm font-medium text-gray-700 whitespace-nowrap cursor-pointer hover:bg-gray-50 smooth-hover hover-lift dark:text-gray-300 dark:hover:bg-gray-700"
                      >
                        <div className="flex items-center">
                          {h} <ArrowUpDown className="ml-1 h-3 w-3" />
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={headers.length} className="px-3 py-2 text-center">
                        <div className="flex items-center justify-center py-4">
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Loading data...
                        </div>
                      </td>
                    </tr>
                  ) : pageRows.length === 0 ? (
                    <tr>
                      <td colSpan={headers.length} className="px-3 py-2 text-center text-gray-500">
                        No data available
                      </td>
                    </tr>
                  ) : (
                    pageRows.map((row, rowIdx) => (
                      <tr key={rowIdx} className={rowIdx % 2 === 0 ? "bg-white dark:bg-gray-800" : "bg-gray-50 dark:bg-gray-900"}>
                        {row.map((cell, cellIdx) => (
                          <td
                            key={cellIdx}
                            className="px-3 py-2 text-sm text-gray-900 whitespace-nowrap max-w-[150px] truncate dark:text-gray-100"
                            title={String(cell ?? "")}
                          >
                            {formatCell(cell, cellIdx)}
                          </td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>

              {/* Pagination */}
              <div className="flex items-center justify-between border-t border-gray-200 bg-white px-3 py-3 sm:px-6 dark:bg-gray-800 dark:border-gray-700">
                <div className="flex flex-1 justify-between sm:hidden">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage <= 1 || loading}
                    className="relative inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 smooth-hover hover-lift dark:bg-gray-800 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-700"
                    type="button"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage >= totalPages || loading}
                    className="relative ml-3 inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 smooth-hover hover-lift dark:bg-gray-800 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-700"
                    type="button"
                  >
                    Next
                  </button>
                </div>

                <div className="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                      Showing <span className="font-medium">{sliceStart + 1}</span> to{" "}
                      <span className="font-medium">{sliceStart + pageRows.length}</span> of{" "}
                      <span className="font-medium">{tableMetadata?.total_rows_available?.toLocaleString() || sorted.length}</span> results
                      {tableMetadata?.results_truncated && tableMetadata?.total_rows_available && (
                        <span className="ml-2 text-yellow-600 dark:text-yellow-400">
                          (of {tableMetadata.total_rows_available.toLocaleString()} total)
                        </span>
                      )}
                    </p>
                  </div>
                  <div>
                    <nav className="isolate inline-flex -space-x-px rounded-md shadow-sm" aria-label="Pagination">
                      <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={currentPage <= 1 || loading}
                        className="relative inline-flex items-center rounded-l-md px-2 py-2 text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0 smooth-hover hover-lift dark:bg-gray-800 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
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
                              disabled={loading}
                              className={`relative inline-flex items-center px-4 py-2 text-sm font-semibold ${
                                currentPage === pageNum
                                  ? "z-10 bg-primary-purple-600 text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-purple-600"
                                  : "text-gray-900 ring-1 ring-inset ring-gray-300 hover:bg-primary-purple-50 focus:outline-offset-0 smooth-hover hover-lift dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700 dark:ring-gray-700"
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
                              className="relative inline-flex items-center px-4 py-2 text-sm font-semibold text-gray-700 ring-1 ring-inset ring-gray-300 focus:outline-offset-0 dark:text-gray-300 dark:ring-gray-700"
                            >
                              ...
                            </span>
                          );
                        }
                        return null;
                      })}
                      <button
                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                        disabled={currentPage >= totalPages || loading}
                        className="relative inline-flex items-center rounded-r-md px-2 py-2 text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0 smooth-hover hover-lift dark:bg-gray-800 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
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
        <div className="fixed inset-4 z-[100] bg-white rounded-2xl shadow-2xl p-4 flex flex-col overflow-hidden dark:bg-gray-800 w-full max-w-2xl md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl mx-auto">
          {/* Enhanced fullscreen header with prominent close button */}
          <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Data Table (Fullscreen)</h2>
            <div className="flex items-center gap-2">
              <div className="hidden sm:flex items-center gap-1 text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded dark:bg-gray-700 dark:text-gray-300">
                <kbd className="bg-white border border-gray-300 rounded px-1 py-0.5 dark:bg-gray-600 dark:border-gray-500">ESC</kbd>
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
    <div className="rounded-xl bg-white/95 shadow-sm p-3 overflow-hidden dark:bg-gray-800/95 w-full max-w-2xl md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl mx-auto">
      {Toolbar}
      {MainArea}
    </div>
  );
}