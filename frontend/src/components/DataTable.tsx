import React, { useMemo, useState } from "react";
import { Download, Copy, Maximize2, Minimize2, ArrowUpDown, Search } from "lucide-react";

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
    return String(v);
  };

  const TableCore = (
    <div className={`border rounded-xl bg-white/95 shadow-sm ${full ? "p-4" : "p-3"}`}>
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className="text-xs text-gray-600 mr-auto">
          {sorted.length.toLocaleString()} row{sorted.length === 1 ? "" : "s"}
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search…"
            className="pl-8 pr-3 py-1.5 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
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

        {/* Copy / CSV / Expand */}
        <button
          onClick={() => navigator.clipboard.writeText(csvAll)}
          className="text-xs px-2 py-1.5 rounded-lg border bg-white hover:bg-gray-50 flex items-center gap-1"
          title="Copy CSV to clipboard"
        >
          <Copy size={14} /> Copy
        </button>
        <a
          href={`data:text/csv;charset=utf-8,${encodeURIComponent(csvAll)}`}
          download="table.csv"
          className="text-xs px-2 py-1.5 rounded-lg border bg-white hover:bg-gray-50 flex items-center gap-1"
          title="Download CSV"
        >
          <Download size={14} /> CSV
        </a>
        <button
          onClick={() => setFull((v) => !v)}
          className="text-xs px-2 py-1.5 rounded-lg border bg-white hover:bg-gray-50 flex items-center gap-1"
          title={full ? "Exit fullscreen" : "Expand"}
        >
          {full ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          {full ? "Close" : "Expand"}
        </button>
      </div>

      {/* Table container */}
      <div className={`${full ? "max-h-[70vh]" : "max-h-72"} overflow-auto rounded-lg border`}>
        <table className="table-fixed w-full border-collapse">
          <thead className="bg-gray-100 sticky top-0 z-10">
            <tr>
              {headers.map((h, i) => (
                <th
                  key={i}
                  className={`px-3 py-2 text-left text-xs font-semibold text-gray-700 border-b border-gray-200 whitespace-nowrap ${
                    i === 0 ? "sticky left-0 bg-gray-100 z-10" : ""
                  } ${numericCols[i] ? "text-right" : "text-left"}`}
                >
                  <button
                    onClick={() => handleHeaderClick(i)}
                    className="inline-flex items-center gap-1 hover:opacity-80"
                    title="Sort"
                  >
                    <span>{h}</span>
                    <ArrowUpDown className="h-3.5 w-3.5 text-gray-400" />
                    {sort?.col === i ? (
                      <span className="text-[10px] text-gray-500">{sort.dir === "asc" ? "▲" : "▼"}</span>
                    ) : null}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, r) => (
              <tr key={r} className={r % 2 === 0 ? "bg-white" : "bg-gray-50 hover:bg-gray-100"}>
                {row.map((cell, c) => (
                  <td
                    key={c}
                    className={`px-3 py-2 text-sm border-b border-gray-200 align-top ${
                      c === 0 ? "sticky left-0 bg-inherit z-0" : ""
                    } ${numericCols[c] ? "text-right tabular-nums" : "text-left"} truncate`}
                    title={String(cell ?? "")}
                  >
                    {formatCell(cell, c)}
                  </td>
                ))}
              </tr>
            ))}
            {pageRows.length === 0 && (
              <tr>
                <td className="px-3 py-6 text-sm text-gray-500 text-center" colSpan={headers.length}>
                  No rows.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-3 text-xs text-gray-600">
        <div>
          Showing{" "}
          <strong>
            {sorted.length === 0 ? 0 : sliceStart + 1}-{Math.min(sorted.length, sliceStart + pageSize)}
          </strong>{" "}
          of <strong>{sorted.length}</strong>
        </div>
        <div className="flex items-center gap-1">
          <button
            className="px-2 py-1 rounded border disabled:opacity-40"
            onClick={() => setPage(1)}
            disabled={currentPage <= 1}
          >
            ⏮
          </button>
          <button
            className="px-2 py-1 rounded border disabled:opacity-40"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
          >
            ◀
          </button>
          <span className="px-2">
            Page <strong>{currentPage}</strong> / {totalPages}
          </span>
          <button
            className="px-2 py-1 rounded border disabled:opacity-40"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages}
          >
            ▶
          </button>
          <button
            className="px-2 py-1 rounded border disabled:opacity-40"
            onClick={() => setPage(totalPages)}
            disabled={currentPage >= totalPages}
          >
            ⏭
          </button>
        </div>
      </div>
    </div>
  );

  // Fullscreen overlay when expanded
  if (full) {
    return (
      <>
        <div className="fixed inset-0 bg-black/40 z-40" onClick={() => setFull(false)} />
        <div className="fixed inset-4 md:inset-10 z-50">{TableCore}</div>
      </>
    );
  }

  return TableCore;
}
