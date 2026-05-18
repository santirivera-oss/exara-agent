"use client";

import { AgentEvent, StreamEvent } from "./agent-types";

const DEFAULT_BASE = "http://127.0.0.1:8765";

export interface ChatStreamOptions {
  message: string;
  sessionId?: string | null;
  baseUrl?: string;
  signal?: AbortSignal;
  /** When true, high-risk tools auto-allow without prompting. Default: false. */
  autoConfirm?: boolean;
  onEvent: (event: StreamEvent) => void;
}

/**
 * Stream events from the agent's /chat/stream endpoint.
 *
 * The backend emits Server-Sent Events with each AgentEvent serialised as JSON.
 * We use `fetch` + `ReadableStream` (not EventSource) because EventSource
 * cannot POST a body. The body parsing handles SSE's "data: ...\n\n" framing.
 */
export async function streamChat({
  message,
  sessionId,
  baseUrl = DEFAULT_BASE,
  signal,
  autoConfirm = false,
  onEvent,
}: ChatStreamOptions): Promise<void> {
  const response = await fetch(`${baseUrl}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: sessionId ?? null,
      auto_confirm: autoConfirm,
    }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }
  if (!response.body) {
    throw new Error("response has no body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Split on the SSE record separator
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!raw.startsWith("data:")) continue;
      const payload = raw.slice(5).trim();
      if (payload === "[DONE]") {
        onEvent({ type: "done" });
        return;
      }
      try {
        const parsed = JSON.parse(payload);
        onEvent(parsed as StreamEvent);
      } catch (e) {
        console.warn("failed to parse SSE payload", payload, e);
      }
    }
  }
}

export interface BackendInfo {
  status: string;
  provider: string;
  workspace: string;
}

export async function health(baseUrl = DEFAULT_BASE): Promise<BackendInfo> {
  const r = await fetch(`${baseUrl}/health`);
  if (!r.ok) throw new Error(`backend HTTP ${r.status}`);
  return r.json();
}

export async function listTools(baseUrl = DEFAULT_BASE): Promise<{ name: string; description: string }[]> {
  const r = await fetch(`${baseUrl}/tools`);
  if (!r.ok) throw new Error(`backend HTTP ${r.status}`);
  return r.json();
}

export async function togglePlanMode(sessionId: string, baseUrl = DEFAULT_BASE): Promise<{ plan_mode: boolean }> {
  const r = await fetch(`${baseUrl}/sessions/${sessionId}/plan`, { method: "POST" });
  if (!r.ok) throw new Error(`backend HTTP ${r.status}`);
  return r.json();
}

export async function compactSession(sessionId: string, baseUrl = DEFAULT_BASE): Promise<{ collapsed: number; messages: number }> {
  const r = await fetch(`${baseUrl}/sessions/${sessionId}/compact`, { method: "POST" });
  if (!r.ok) throw new Error(`backend HTTP ${r.status}`);
  return r.json();
}

export interface SessionStats {
  messages: number;
  by_role: Record<string, number>;
  plan_mode: boolean;
  model: string | null;
}

export async function sessionStats(sessionId: string, baseUrl = DEFAULT_BASE): Promise<SessionStats> {
  const r = await fetch(`${baseUrl}/sessions/${sessionId}/stats`);
  if (!r.ok) throw new Error(`backend HTTP ${r.status}`);
  return r.json();
}

export async function resolveConfirm(
  sessionId: string,
  confirmationId: string,
  allow: boolean,
  baseUrl = DEFAULT_BASE,
): Promise<void> {
  const r = await fetch(`${baseUrl}/sessions/${sessionId}/confirm/${confirmationId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ allow }),
  });
  if (!r.ok) throw new Error(`backend HTTP ${r.status}`);
}

export type { AgentEvent };
