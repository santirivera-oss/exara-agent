"use client";

import { useState } from "react";
import type { UiMessage } from "@/lib/agent-types";
import { Badge } from "@/components/ui/badge";

type ToolCallMessage = Extract<UiMessage, { kind: "tool_call" }>;

const STATUS = {
  pending: { label: "running…", classes: "border-slate-700 bg-slate-900 text-slate-300" },
  success: { label: "ok", classes: "border-emerald-700 bg-emerald-950/40 text-emerald-200" },
  failed: { label: "failed", classes: "border-red-700 bg-red-950/40 text-red-200" },
  denied: { label: "denied", classes: "border-orange-700 bg-orange-950/40 text-orange-200" },
};

export function ToolCallCard({ message: m }: { message: ToolCallMessage }) {
  const [open, setOpen] = useState(false);

  const status = m.denied
    ? "denied"
    : m.result
    ? m.result.success
      ? "success"
      : "failed"
    : "pending";
  const s = STATUS[status];

  const argsSummary = formatArgs(m.args);

  return (
    <div className={`rounded border px-3 py-2 text-sm ${s.classes}`}>
      <div className="flex items-center justify-between gap-2">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex flex-1 items-center gap-2 text-left font-mono text-xs hover:opacity-80"
        >
          <span className="opacity-60">{open ? "▼" : "▶"}</span>
          <span className="font-semibold">{m.tool}</span>
          <span className="truncate opacity-70">({argsSummary})</span>
        </button>
        <Badge variant="outline" className="font-mono text-[10px]">
          {s.label}
        </Badge>
      </div>

      {open && (
        <div className="mt-2 space-y-2 text-xs">
          <pre className="overflow-x-auto rounded bg-black/30 p-2 text-[11px]">
            {JSON.stringify(m.args, null, 2)}
          </pre>
          {m.preview && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wider text-cyan-400">preview</div>
              <pre className="overflow-x-auto rounded bg-black/30 p-2 text-[11px]">
                {colorDiff(m.preview)}
              </pre>
            </div>
          )}
          {m.denied && (
            <div className="rounded border border-orange-800 bg-orange-950/30 p-2 text-orange-200">
              {m.denied}
            </div>
          )}
          {m.result && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wider opacity-70">
                {m.result.success ? "result" : "error"}
              </div>
              <pre className="overflow-x-auto rounded bg-black/30 p-2 text-[11px]">
                {m.result.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function formatArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (entries.length === 0) return "";
  return entries
    .map(([k, v]) => `${k}=${formatValue(v)}`)
    .join(", ");
}

function formatValue(v: unknown): string {
  if (typeof v === "string") {
    return v.length > 40 ? `"${v.slice(0, 40)}…"` : `"${v}"`;
  }
  if (Array.isArray(v)) return `[${v.length} items]`;
  if (typeof v === "object" && v !== null) return "{…}";
  return String(v);
}

function colorDiff(text: string): React.ReactNode {
  // Simple +/- line colouring. JSX list output.
  return text.split("\n").map((line, i) => {
    let cls = "";
    if (line.startsWith("+")) cls = "text-emerald-300";
    else if (line.startsWith("-")) cls = "text-red-300";
    else if (line.startsWith("@@")) cls = "text-cyan-300";
    return (
      <span key={i} className={cls}>
        {line}
        {"\n"}
      </span>
    );
  });
}
