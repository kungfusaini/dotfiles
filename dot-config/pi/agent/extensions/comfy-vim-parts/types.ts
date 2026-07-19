export type Mode = "insert" | "normal" | "visual" | "visualLine";
export type CursorPos = { line: number; col: number };
export type FlashTarget = CursorPos & { label: string };
