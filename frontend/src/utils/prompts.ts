// src/utils/prompts.ts
export type DBKey = "source_db_1" | "source_db_2";

const PROMPTS: Record<DBKey, string[]> = {
  source_db_1: [
    "Show floor-wise production and provide a summary",
    // "List the employee names and summarize their salaries",
    "Show the company’s average efficiency over the last 30 days in ascending order",
    "Show floor-wise average efficiency over the last 30 days in ascending order",
    "Show floor-wise average efficiency and DHU for last month",
    "Show floor-wise average efficiency and DHU for the last day",
    "Show the floor with the lowest efficiency in the last 30 days",
    "Show the company-wise efficiency trend for last month",
    "Show the floor-wise efficiency trend for last month",
  ],
  source_db_2: [
    //"Give me report on orders audit",
    //"Show me the summary of import payments",
  ],
};

export const getPrompts = (db: string): string[] => {
  return PROMPTS[(db as DBKey)] ?? PROMPTS.source_db_2;
};
