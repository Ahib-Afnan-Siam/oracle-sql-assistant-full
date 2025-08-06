// src/utils/markdown.ts

export function convertToMarkdownTable(table: (string | number | null)[][]): string {
  if (!Array.isArray(table) || table.length === 0) return "";

  const header = table[0];
  const rows = table.slice(1);

  const markdownRows = [
    `| ${header.map((col) => col ?? "").join(" | ")} |`,
    `| ${header.map(() => "---").join(" | ")} |`,
    ...rows.map((row) => `| ${row.map((cell) => cell ?? "").join(" | ")} |`),
  ];

  return markdownRows.join("\n");
}
