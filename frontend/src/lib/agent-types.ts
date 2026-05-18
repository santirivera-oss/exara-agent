// Mirror of the backend's `AgentEvent` dataclass. Keep in sync with
// ai_agent/core/agent.py.

export type AgentEventType =
  | "thought"
  | "tool_call"
  | "tool_result"
  | "denied"
  | "final"
  | "error"
  | "step"
  | "preview"
  | "plan_submitted"
  | "content_delta"
  | "confirm_request";

export interface AgentEvent {
  type: AgentEventType;
  content?: string;
  tool?: string | null;
  args?: Record<string, unknown> | null;
  success?: boolean | null;
  step?: number | null;
  data?: Record<string, unknown> | null;
}

export interface SessionEvent {
  type: "session";
  session_id: string;
}

export type StreamEvent = AgentEvent | SessionEvent | { type: "done" };

// Internal UI message shape — we accumulate events into these for rendering.
export type UiMessage =
  | { kind: "user"; id: string; text: string }
  | { kind: "assistant"; id: string; text: string; streaming: boolean }
  | {
      kind: "tool_call";
      id: string;
      tool: string;
      args: Record<string, unknown>;
      preview?: string;
      result?: { success: boolean; output: string };
      denied?: string;
    }
  | { kind: "plan"; id: string; text: string }
  | { kind: "error"; id: string; text: string }
  | { kind: "step"; id: string; n: number }
  | { kind: "todos"; id: string; items: Array<{ content: string; status: string }> };
