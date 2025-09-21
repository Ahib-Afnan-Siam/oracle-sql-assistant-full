// src/utils/exportUtils.ts
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import * as XLSX from "xlsx";

export type Table2D = (string | number | null)[][];
export type ChartSnapshot = { title?: string; dataUrl: string; widthPx?: number; heightPx?: number };

// -------------------------------------------------------------
// CSV (you already have this in DataTable, but keep a shared version)
// -------------------------------------------------------------
export function toCSV(rows: Table2D): string {
  return rows
    .map((r) =>
      r
        .map((v) => {
          const s = v === null || v === undefined ? "" : String(v);
          if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
          return s;
        })
        .join(","),
    )
    .join("\n");
}

// -------------------------------------------------------------
// EXCEL (multi-sheet)
// sheets: { name: "Sheet1", rows: Table2D }[]
// -------------------------------------------------------------
export function exportExcel(
  sheets: { name: string; rows: Table2D }[],
  filename = "report.xlsx",
) {
  const wb = XLSX.utils.book_new();

  for (const { name, rows } of sheets) {
    const ws = XLSX.utils.aoa_to_sheet(rows);
    // Optional: set column widths (auto-ish)
    const maxCols = Math.max(...rows.map((r) => r.length));
    const colWidths = Array.from({ length: maxCols }).map((_, c) => {
      const maxLen = Math.max(
        ...rows.map((r) => (r?.[c] ? String(r[c]).length : 0)),
        8,
      );
      return { wch: Math.min(40, Math.max(10, maxLen + 2)) };
    });
    (ws as any)["!cols"] = colWidths;
    XLSX.utils.book_append_sheet(wb, ws, sanitizeSheetName(name));
  }

  XLSX.writeFile(wb, filename);
}

function sanitizeSheetName(name: string) {
  return name.replace(/[\\/?*[\]:]/g, "_").slice(0, 31) || "Sheet";
}

// -------------------------------------------------------------
// PDF (tables + charts)
// - tables: array of Table2D (first row = header)
// - charts: array of base64 PNGs from Chart.js (optional)
// -------------------------------------------------------------
export function exportPDF(opts: {
  title?: string;
  subtitle?: string;
  tables?: { heading?: string; rows: Table2D }[];
  charts?: ChartSnapshot[];
  fileName?: string;
}) {
  const {
    title = "Report",
    subtitle,
    tables = [],
    charts = [],
    fileName = "report.pdf",
  } = opts;

  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const marginX = 40;
  let y = 56;

  // Title
  doc.setFont("helvetica", "bold");
  doc.setFontSize(18);
  doc.text(title, marginX, y);
  y += 22;

  if (subtitle) {
    doc.setFont("helvetica", "normal");
    doc.setFontSize(11);
    doc.text(subtitle, marginX, y);
    y += 20;
  }

  // Charts (snapshots)
  for (const chart of charts) {
    const w = chart.widthPx ?? 520; // scale to fit A4 width minus margins
    const h = chart.heightPx ?? 280;

    // new page if not enough space
    if (y + h + 20 > doc.internal.pageSize.getHeight()) {
      doc.addPage();
      y = 56;
    }

    if (chart.title) {
      doc.setFont("helvetica", "bold");
      doc.setFontSize(12);
      doc.text(chart.title, marginX, y);
      y += 16;
    }

    doc.addImage(chart.dataUrl, "PNG", marginX, y, Math.min(pageW - marginX * 2, w), h);
    y += h + 16;
  }

  // Tables
  for (const t of tables) {
    const [headers, ...rows] = t.rows;
    const head = [headers?.map((h) => (h == null ? "" : String(h))) ?? []];
    const body = rows.map((r) => r.map((v) => (v == null ? "" : String(v))));

    if (t.heading) {
      // add heading text before the table
      if (y + 20 > doc.internal.pageSize.getHeight()) {
        doc.addPage();
        y = 56;
      }
      doc.setFont("helvetica", "bold");
      doc.setFontSize(12);
      doc.text(t.heading, marginX, y);
      y += 12;
    }

    autoTable(doc, {
      startY: y,
      head,
      body,
      margin: { left: marginX, right: marginX },
      styles: { fontSize: 9, cellPadding: 4 },
      headStyles: { fillColor: [59, 7, 100] }, // matches your purple brand
      theme: "striped",
      didDrawPage: (data) => {
        // Footer page number
        const str = `Page ${doc.getNumberOfPages()}`;
        doc.setFontSize(9);
        doc.text(str, pageW - marginX, doc.internal.pageSize.getHeight() - 16, { align: "right" });
      },
    });

    // update y for next block
    y = (doc as any).lastAutoTable.finalY + 18;
  }

  doc.save(fileName);
}
