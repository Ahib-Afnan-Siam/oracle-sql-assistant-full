import React, { useEffect, useMemo, useState } from "react";
import { Download, Copy, Maximize2, Minimize2, ArrowUpDown, Search } from "lucide-react";
import DataVisualization from "./DataVisualization";

type TableData = (string | number | null)[][]; // first row = headers

function toCSV(rows: (string | number | null)[][]): string {
  return rows
    .map((r) =>
      r
        .map((v) => {
          const s = v === null || v === undefined ? "" : String(v);
          // escape quotes / commas / newlines
          if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
          return s;
        })
        .join(",")
    )
    .join("\n");
}

function isNumericValue(v: unknown): boolean {
  if (typeof v === "number") return true;
  if (typeof v !== "string") return false;
  const trimmed = v.replace(/,/g, "").trim();
  return trimmed !== "" && !isNaN(Number(trimmed));
}

export default function DataTable({ data }: { data: TableData }) {
  const headers = (data?.[0] as string[]) || [];
  const rawRows = (data || []).slice(1);

  // NEW: visualization state
  const [showVisualization, setShowVisualization] = useState(false);

  // Add debugging
  useEffect(() => {
    if (showVisualization) {
      console.log("Visualization state changed to true");
      console.log("Columns:", headers);
      console.log("Rows:", rawRows);
    }
  }, [showVisualization, headers, rawRows]);

  // auto-detect numeric columns by sampling
  const numericCols = useMemo(() => {
    const sample = rawRows.slice(0, 25);
    return headers.map((_, col) => sample.every((r) => isNumericValue(r[col]) || r[col] == null));
  }, [headers, rawRows]);

  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ col: number; dir: "asc" | "desc" } | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [full, setFull] = useState(false);

  const filtered = useMemo(() => {
    if (!query.trim()) return rawRows;
    const q = query.toLowerCase();
    return rawRows.filter((r) => r.some((c) => String(c ?? "").toLowerCase().includes(q)));
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

  const csvAll = useMemo(() => toCSV([headers, ...sorted]), [headers, sorted]);

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
    const str = String(v);
    // Add an ellipsis hint for long text that will be truncated visually
    return str.length > 30 ? str + " ⋯" : str;
  };

  // convenience aliases for visualization props
  const columns = headers;
  const rows = sorted;

  return (
    <div className={`border rounded-xl bg-white/95 shadow-sm ${full ? "p-4" : "p-3"}`}>
      {/* Toolbar with existing controls + Visualize button */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-4">
        {/* Left cluster: existing toolbar controls */}
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
              className="pl-8 pr-3 py-1.5 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 w-full sm:w-32 md:w-40"
            />
          </div>

          {/* Page size */}
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.value));
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

          {/* Copy / CSV / Expand - stacked vertically on mobile */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => navigator.clipboard.writeText(csvAll)}
              className="text-xs px-2 py-1.5 rounded-lg border bg-white hover:bg-gray-50 flex items-center gap-1"
              title="Copy CSV to clipboard"
            >
              <Copy size={14} /> <span className="hidden sm:inline">Copy</span>
            </button>
            <a
              href={`data:text/csv;charset=utf-8,${encodeURIComponent(csvAll)}`}
              download="table.csv"
              className="text-xs px-2 py-1.5 rounded-lg border bg-white hover:bg-gray-50 flex items-center gap-1"
              title="Download CSV"
            >
              <Download size={14} /> <span className="hidden sm:inline">CSV</span>
            </a>
            <button
              onClick={() => setFull((v) => !v)}
              className="text-xs px-2 py-1.5 rounded-lg border bg-white hover:bg-gray-50 flex items-center gap-1"
              title={full ? "Exit fullscreen" : "Expand"}
            >
              {full ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              <span className="hidden sm:inline">{full ? "Close" : "Expand"}</span>
            </button>
          </div>
        </div>
        <div className="flex justify-between items-center w-full md:w-auto">
          {/* Right: NEW Visualize button */}
          {!showVisualization ? (
            <button
              onClick={() => setShowVisualization(true)}
              className="px-3 py-1 bg-[#3b0764] text-white rounded hover:bg-[#4c0a85] text-sm w-full sm:w-auto"
            >
              Visualize Data
            </button>
          ) : (
            <button
              onClick={() => setShowVisualization(false)}
              className="px-3 py-1 bg-gray-700 text-white rounded hover:bg-gray-800 text-sm w-full sm:w-auto"
            >
              Back to Table
            </button>
          )}
        </div>
      </div>

      {/* MAIN AREA: conditional render (Visualization vs Table) */}
      {showVisualization ? (
        <DataVisualization
          columns={columns}
          rows={rows}
          onBackToTable={() => setShowVisualization(false)}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead>
              <tr>
                {headers.map((h, idx) => (
                  <th
                    key={idx}
                    onClick={() => handleHeaderClick(idx)}
                    className="px-4 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-gray-50"
                  >
                    <div className="flex items-center">
                      {h}
                      <ArrowUpDown className="ml-1 h-3 w-3" />
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {pageRows.map((row, rowIdx) => (
                <tr key={rowIdx} className={rowIdx % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                  {row.map((cell, cellIdx) => (
                    <td
                      key={cellIdx}
                      className="px-4 py-2 whitespace-nowrap text-sm font-medium text-gray-700"
                    >
                      {formatCell(cell, cellIdx)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          <div className="flex items-center justify-between border-t border-gray-200 bg-white px-4 py-3 sm:px-6">
            <div className="flex flex-1 justify-between sm:hidden">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={currentPage <= 1}
                className="relative inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Previous
              </button>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages}
                className="relative ml-3 inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
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
                <nav
                  className="isolate inline-flex -space-x-px rounded-md shadow-sm"
                  aria-label="Pagination"
                >
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={currentPage <= 1}
                    className="relative inline-flex items-center rounded-l-md px-2 py-2 text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0"
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
                              ? "z-10 bg-[#3b0764] text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3b0764]"
                              : "text-gray-900 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:outline-offset-0"
                          }`}
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
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage >= totalPages}
                    className="relative inline-flex items-center rounded-r-md px-2 py-2 text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0"
                  >
                    Next
                  </button>
                </nav>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
