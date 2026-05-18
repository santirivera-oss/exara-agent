"use client";

import { useEffect, useRef } from "react";
import type { UiMessage } from "@/lib/agent-types";
import { ToolCallCard } from "./tool-call-card";
import { Markdown } from "./markdown";
import { Badge } from "@/components/ui/badge";

interface Props {
  messages: UiMessage[];
}

export function MessageList({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Stick to bottom as new events arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <div className="h-full overflow-y-auto px-4 py-3">
      {messages.length === 0 && (
        <div className="mt-12 text-center text-sm text-slate-500">
          empty — say hi to the agent
        </div>
      )}
      <ul className="space-y-3">
        {messages.map((m) => (
          <li key={m.id}>{renderMessage(m)}</li>
        ))}
      </ul>
      <div ref={bottomRef} />
    </div>
  );
}

function renderMessage(m: UiMessage) {
  switch (m.kind) {
    case "user":
      return (
        <div className="ml-12 rounded-lg bg-slate-800 px-3 py-2 text-sm">
          <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-400">you</div>
          <div className="whitespace-pre-wrap">{m.text}</div>
        </div>
      );
    case "assistant":
      return (
        <div className="mr-12 rounded-lg bg-slate-900 px-3 py-2 text-sm">
          <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wider text-emerald-400">
            <span>agent</span>
            {m.streaming && <span className="animate-pulse">streaming…</span>}
          </div>
          {m.streaming ? (
            <div className="whitespace-pre-wrap font-light">{m.text}</div>
          ) : (
            <Markdown>{m.text}</Markdown>
          )}
        </div>
      );
    case "tool_call":
      return <ToolCallCard message={m} />;
    case "plan":
      return (
        <div className="rounded border border-yellow-700 bg-yellow-950/50 px-3 py-2 text-sm">
          <div className="mb-1 text-[10px] uppercase tracking-wider text-yellow-400">plan submitted</div>
          <div className="whitespace-pre-wrap font-light">{m.text}</div>
        </div>
      );
    case "error":
      return (
        <div className="rounded border border-red-700 bg-red-950/50 px-3 py-2 text-sm text-red-200">
          <div className="mb-1 text-[10px] uppercase tracking-wider text-red-400">error</div>
          <div className="whitespace-pre-wrap font-light">{m.text}</div>
        </div>
      );
    case "step":
      return (
        <div className="flex items-center gap-2 py-1 text-xs text-slate-500">
          <hr className="flex-1 border-slate-800" />
          <Badge variant="outline" className="font-mono text-[10px]">step {m.n}</Badge>
          <hr className="flex-1 border-slate-800" />
        </div>
      );
    case "todos":
      return (
        <div className="rounded border border-amber-700 bg-amber-950/30 px-3 py-2 text-sm">
          <div className="mb-1 text-[10px] uppercase tracking-wider text-amber-400">todos</div>
          <ul className="space-y-0.5 font-mono text-xs">
            {m.items.map((it, i) => (
              <li key={i}>
                <span className="mr-2 text-amber-300">
                  {it.status === "completed" ? "(x)" : it.status === "in_progress" ? "(~)" : "( )"}
                </span>
                {it.content}
              </li>
            ))}
          </ul>
        </div>
      );
  }
}
