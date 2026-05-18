"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { listTools } from "@/lib/agent-client";

interface ToolMeta {
  name: string;
  description: string;
}

interface SessionMeta {
  id: string;
  name: string | null;
  workspace: string;
  created_at: number;
}

interface Props {
  sessionId: string | null;
  onSlashCommand: (cmd: string) => void;
  onResume: (id: string) => void;
  baseUrl?: string;
}

const DEFAULT_BASE = "http://127.0.0.1:8765";

export function SidePanel({ sessionId, onSlashCommand, onResume, baseUrl = DEFAULT_BASE }: Props) {
  const [tools, setTools] = useState<ToolMeta[] | null>(null);
  const [sessions, setSessions] = useState<SessionMeta[] | null>(null);
  const [section, setSection] = useState<"actions" | "tools" | "sessions">("actions");

  useEffect(() => {
    listTools().then(setTools).catch(() => setTools([]));
    fetch(`${baseUrl}/sessions`)
      .then((r) => r.json())
      .then(setSessions)
      .catch(() => setSessions([]));
  }, [baseUrl, sessionId]); // refresh sessions when a new one is created

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-slate-800 bg-slate-950 text-slate-200">
      <div className="border-b border-slate-800 px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
        controls
      </div>

      <nav className="flex border-b border-slate-800 text-xs">
        {(["actions", "tools", "sessions"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setSection(s)}
            className={`flex-1 px-2 py-1.5 capitalize transition-colors ${
              section === s
                ? "border-b border-emerald-500 bg-slate-900 text-emerald-300"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {s}
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto p-2 text-xs">
        {section === "actions" && (
          <div className="space-y-1.5">
            <SidebarAction label="Plan mode" hint="toggle read-only planning" onClick={() => onSlashCommand("/plan")} />
            <SidebarAction label="Compact" hint="summarise old history" onClick={() => onSlashCommand("/compact")} />
            <SidebarAction label="Init CLAUDE.md" hint="ask agent to describe repo" onClick={() => onSlashCommand("/init")} />
            <SidebarAction label="New session" hint="start fresh" onClick={() => onSlashCommand("/clear")} />
            <SidebarAction label="Stats" hint="message count, model, mode" onClick={() => onSlashCommand("/stats")} />
            <p className="mt-3 text-[10px] text-slate-500">
              These trigger the agent with a slash command — same as typing /plan in the textarea.
            </p>
          </div>
        )}

        {section === "tools" && (
          <div className="space-y-1.5">
            {tools === null && <Skeleton />}
            {tools?.length === 0 && <p className="text-slate-500">no tools</p>}
            {tools?.map((t) => (
              <details key={t.name} className="rounded border border-slate-800 px-2 py-1">
                <summary className="cursor-pointer truncate font-mono text-emerald-300">{t.name}</summary>
                <p className="mt-1 text-[11px] text-slate-400">{t.description}</p>
              </details>
            ))}
          </div>
        )}

        {section === "sessions" && (
          <div className="space-y-1">
            {sessions === null && <Skeleton />}
            {sessions?.length === 0 && <p className="text-slate-500">no past sessions</p>}
            {sessions?.map((s) => (
              <button
                key={s.id}
                onClick={() => onResume(s.id)}
                className={`flex w-full flex-col items-start rounded px-2 py-1 text-left transition-colors hover:bg-slate-800 ${
                  s.id === sessionId ? "bg-slate-800" : ""
                }`}
              >
                <span className="font-mono text-[11px] text-emerald-300">{s.id.slice(0, 12)}</span>
                <span className="text-[10px] text-slate-500">
                  {new Date(s.created_at * 1000).toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {sessionId && (
        <div className="border-t border-slate-800 p-2 text-[10px] text-slate-500">
          active <Badge variant="outline" className="ml-1 font-mono">{sessionId.slice(0, 8)}</Badge>
        </div>
      )}
    </aside>
  );
}

function SidebarAction({ label, hint, onClick }: { label: string; hint: string; onClick: () => void }) {
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      className="h-auto w-full flex-col items-start gap-0 py-1.5 text-left hover:bg-slate-800"
    >
      <span className="text-xs text-slate-200">{label}</span>
      <span className="text-[10px] text-slate-500">{hint}</span>
    </Button>
  );
}

function Skeleton() {
  return (
    <div className="space-y-1">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-7 animate-pulse rounded bg-slate-900" />
      ))}
    </div>
  );
}
