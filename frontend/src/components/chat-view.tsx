"use client";

import { useEffect, useRef, useState } from "react";
import {
  streamChat, health, togglePlanMode, compactSession, sessionStats, resolveConfirm,
  type BackendInfo,
} from "@/lib/agent-client";
import type { AgentEvent, UiMessage } from "@/lib/agent-types";
import { MessageList } from "./message-list";
import { SidePanel } from "./side-panel";
import { ConfirmModal, type PendingConfirm } from "./confirm-modal";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

/**
 * Reduces a stream of AgentEvent into a list of UiMessage we can render.
 * Mirrors the CLI renderer in ai_agent/cli.py — same conventions.
 */
function appendEvent(messages: UiMessage[], evt: AgentEvent): UiMessage[] {
  const id = () => crypto.randomUUID();

  switch (evt.type) {
    case "content_delta": {
      // Append to an in-flight assistant streaming message, or start a new one.
      const last = messages[messages.length - 1];
      if (last && last.kind === "assistant" && last.streaming) {
        return [
          ...messages.slice(0, -1),
          { ...last, text: last.text + (evt.content ?? "") },
        ];
      }
      return [
        ...messages,
        { kind: "assistant", id: id(), text: evt.content ?? "", streaming: true },
      ];
    }
    case "final": {
      // If we streamed, finalise the streaming message. Otherwise create one.
      const last = messages[messages.length - 1];
      if (last && last.kind === "assistant" && last.streaming) {
        return [
          ...messages.slice(0, -1),
          { ...last, streaming: false, text: last.text || (evt.content ?? "") },
        ];
      }
      return [
        ...messages,
        { kind: "assistant", id: id(), text: evt.content ?? "", streaming: false },
      ];
    }
    case "tool_call": {
      return [
        ...messages,
        {
          kind: "tool_call",
          id: id(),
          tool: evt.tool ?? "?",
          args: (evt.args ?? {}) as Record<string, unknown>,
        },
      ];
    }
    case "preview": {
      // Attach preview to the most recent matching tool_call (same tool name).
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.kind === "tool_call" && m.tool === evt.tool && !m.preview) {
          const updated: UiMessage = { ...m, preview: evt.content ?? "" };
          return [...messages.slice(0, i), updated, ...messages.slice(i + 1)];
        }
      }
      return messages;
    }
    case "tool_result": {
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.kind === "tool_call" && m.tool === evt.tool && !m.result) {
          const updated: UiMessage = {
            ...m,
            result: { success: !!evt.success, output: evt.content ?? "" },
          };
          return [...messages.slice(0, i), updated, ...messages.slice(i + 1)];
        }
      }
      return messages;
    }
    case "denied": {
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.kind === "tool_call" && m.tool === evt.tool && !m.denied && !m.result) {
          const updated: UiMessage = { ...m, denied: evt.content ?? "denied" };
          return [...messages.slice(0, i), updated, ...messages.slice(i + 1)];
        }
      }
      return messages;
    }
    case "plan_submitted":
      return [...messages, { kind: "plan", id: id(), text: evt.content ?? "" }];
    case "error":
      return [...messages, { kind: "error", id: id(), text: evt.content ?? "" }];
    case "step":
      return [...messages, { kind: "step", id: id(), n: evt.step ?? 0 }];
    default:
      return messages;
  }
}

export function ChatView() {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [backend, setBackend] = useState<BackendInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [planMode, setPlanMode] = useState(false);
  const [autoConfirm, setAutoConfirm] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Keep a ref to the current session id so the confirm modal can resolve against
  // it even when invoked from inside an async closure that captured an older value.
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // Probe backend on mount
  useEffect(() => {
    health()
      .then(setBackend)
      .catch((e) => setError(`backend unreachable: ${e.message}`));
  }, []);

  async function send(rawText?: string) {
    const text = (rawText ?? input).trim();
    if (!text || busy) return;
    if (rawText === undefined) setInput("");
    setBusy(true);
    setError(null);
    setMessages((prev) => [...prev, { kind: "user", id: crypto.randomUUID(), text }]);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamChat({
        message: text,
        sessionId,
        autoConfirm,
        signal: controller.signal,
        onEvent: (evt) => {
          if (evt.type === "session") {
            setSessionId(evt.session_id);
            return;
          }
          if (evt.type === "done") return;
          if (evt.type === "confirm_request") {
            const a = evt as AgentEvent;
            setPendingConfirm({
              confirmationId: (a.data?.confirmation_id as string) ?? "",
              tool: a.tool ?? "?",
              args: (a.args ?? {}) as Record<string, unknown>,
              reason: a.content ?? "",
              preview: (a.data?.preview as string | null) ?? null,
            });
            // Don't render the confirm_request as a message — the modal handles it.
            return;
          }
          setMessages((prev) => appendEvent(prev, evt as AgentEvent));
        },
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg !== "BodyStreamBuffer was aborted") {
        setError(msg);
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  async function handleSlash(cmd: string) {
    if (busy) return;
    setError(null);
    try {
      if (cmd === "/clear") {
        setMessages([]);
        setSessionId(null);
        setPlanMode(false);
        return;
      }
      if (!sessionId) {
        setError("Send a message first to create a session.");
        return;
      }
      if (cmd === "/plan") {
        const r = await togglePlanMode(sessionId);
        setPlanMode(r.plan_mode);
        const id = crypto.randomUUID();
        setMessages((prev) => [
          ...prev,
          { kind: "assistant", id, text: `plan mode ${r.plan_mode ? "ON" : "OFF"}`, streaming: false },
        ]);
        return;
      }
      if (cmd === "/compact") {
        const r = await compactSession(sessionId);
        const id = crypto.randomUUID();
        setMessages((prev) => [
          ...prev,
          {
            kind: "assistant",
            id,
            text: r.collapsed > 0
              ? `compacted ${r.collapsed} messages (now ${r.messages} in context)`
              : "nothing to compact yet",
            streaming: false,
          },
        ]);
        return;
      }
      if (cmd === "/stats") {
        const s = await sessionStats(sessionId);
        const id = crypto.randomUUID();
        setMessages((prev) => [
          ...prev,
          {
            kind: "assistant",
            id,
            text: `**stats**\n- messages: ${s.messages}\n- by role: \`${JSON.stringify(s.by_role)}\`\n- model: \`${s.model ?? "?"}\`\n- plan_mode: ${s.plan_mode}`,
            streaming: false,
          },
        ]);
        setPlanMode(s.plan_mode);
        return;
      }
      if (cmd === "/init") {
        await send(
          "Analyse this workspace and write CLAUDE.md describing project name, stack, structure, common commands, and any DO-NOTs an agent should know. Keep it under 100 lines.",
        );
        return;
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function handleResume(id: string) {
    setSessionId(id);
    setMessages([]); // history will reload through chat replies; for now just reset display
  }

  async function resolvePending(allow: boolean) {
    const pending = pendingConfirm;
    if (!pending) return;
    const sid = sessionIdRef.current;
    setPendingConfirm(null);
    if (!sid) return;
    try {
      await resolveConfirm(sid, pending.confirmationId, allow);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100">
      <SidePanel sessionId={sessionId} onSlashCommand={handleSlash} onResume={handleResume} />

      <div className="flex flex-1 flex-col">
        {/*
          Header: flex-wrap so badges drop to a second line on narrow screens
          instead of overflowing or scrolling horizontally.
        */}
        <header className="flex flex-wrap items-center justify-between gap-y-2 border-b border-slate-800 px-3 py-2 text-sm sm:px-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono font-semibold">ai-agent</span>
            {backend && (
              <>
                <Badge variant="secondary">{backend.provider}</Badge>
                {/* Hide the long workspace path on small screens — it's noise on mobile */}
                <Badge variant="outline" className="hidden font-mono text-xs sm:inline-flex">
                  {backend.workspace.split(/[\\/]/).slice(-2).join("/")}
                </Badge>
              </>
            )}
            {planMode && (
              <Badge className="bg-yellow-700 text-yellow-100">plan mode</Badge>
            )}
            {sessionId && (
              <Badge variant="outline" className="font-mono text-xs">
                {sessionId.slice(0, 8)}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* a11y: label is bound to the input via htmlFor / id, so screen
                readers announce "auto-confirm, checkbox" instead of just
                "checkbox". */}
            <label
              htmlFor="auto-confirm"
              className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400 select-none"
            >
              <input
                id="auto-confirm"
                type="checkbox"
                checked={autoConfirm}
                onChange={(e) => setAutoConfirm(e.target.checked)}
                className="accent-emerald-500"
              />
              auto-confirm
            </label>
            {busy && (
              <Button size="sm" variant="destructive" onClick={stop}>
                stop
              </Button>
            )}
          </div>
        </header>

        {error && (
          /* a11y: role=alert + aria-live=assertive so screen readers announce
             this immediately when it appears. */
          <div
            role="alert"
            aria-live="assertive"
            className="mx-4 mt-2 rounded border border-red-700 bg-red-950 p-2 text-sm text-red-200"
          >
            {error}
          </div>
        )}

        <div className="flex-1 overflow-hidden">
          <MessageList messages={messages} />
        </div>

        <div className="border-t border-slate-800 p-3">
          {/* a11y: visually-hidden label associated with the textarea — keeps
              screen-reader UX intact without changing the visual design. */}
          <label htmlFor="agent-input" className="sr-only">
            Mensaje al agente
          </label>
          <div className="flex gap-2">
            <Textarea
              id="agent-input"
              aria-label="Mensaje al agente"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={planMode ? "you (plan): pídele que diseñe..." : "Pregunta algo al agente..."}
              className="min-h-[60px] resize-none bg-slate-900 text-slate-100"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              disabled={busy}
            />
            <Button onClick={() => send()} disabled={busy || !input.trim()} aria-label="Send message">
              send
            </Button>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Enter para enviar · Shift+Enter para nueva línea
          </p>
        </div>
      </div>

      <ConfirmModal pending={pendingConfirm} onResolve={resolvePending} />
    </div>
  );
}
