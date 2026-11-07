/**
 * Client-side assistant chat API client (Phase 7 Task 7.3, Scope 3).
 *
 * Implements the POST /api/v1/ai/chat contract in handbook/tasks/phase-7/PLAN.md:
 * - Request: message (<= 500 chars), history (at most last 2 turns, <= 1000 chars/text), page.
 * - Replies:
 *   - 200 answer: { answer, citations, cards }
 *   - 200 fallback: { fallback: "no_answer" }
 *   - 200 fallback: { fallback: "busy" }
 *   - 404: feature flag off; disables chat for the visit
 *   - 429: rate limited; { retry_after_seconds }
 *   - 422 / 500 / network error: error
 */

export interface ChatCitation {
  n: number;
  url: string;
  title: string;
}

export interface ChatCard {
  slug: string;
}

export interface ChatTurn {
  role: "user" | "assistant";
  text: string;
}

export type ChatResponse =
  | { kind: "answer"; answer: string; citations: ChatCitation[]; cards: ChatCard[] }
  | { kind: "no_answer" }
  | { kind: "busy" }
  | { kind: "rate_limited"; retryAfterSeconds?: number }
  | { kind: "error"; message?: string; flagDisabled?: boolean };

export interface AskAssistantOptions {
  message: string;
  history?: ChatTurn[];
  page?: string;
}

const MAX_MESSAGE_LENGTH = 500;
const MAX_HISTORY_TURNS = 2; // at most 2 turns (up to 4 messages)
const MAX_TURN_TEXT_LENGTH = 1000;

let isChatDisabled = false;
const disabledSubscribers = new Set<(disabled: boolean) => void>();

export function isChatDisabledForSession(): boolean {
  return isChatDisabled;
}

export function setChatDisabledForSession(disabled: boolean): void {
  isChatDisabled = disabled;
  disabledSubscribers.forEach((listener) => {
    try {
      listener(disabled);
    } catch {
      // Ignore subscriber errors
    }
  });
}

export function subscribeChatDisabled(listener: (disabled: boolean) => void): () => void {
  disabledSubscribers.add(listener);
  return () => {
    disabledSubscribers.delete(listener);
  };
}

export function resetChatDisabledState(): void {
  isChatDisabled = false;
  disabledSubscribers.clear();
}

/**
 * Truncates history to at most the last 2 turns (up to 4 items) and caps each text at 1000 chars.
 */
function sanitizeHistory(history?: ChatTurn[]): ChatTurn[] {
  if (!history || !Array.isArray(history) || history.length === 0) {
    return [];
  }
  // At most 2 turns = up to last 4 messages
  const maxMessages = MAX_HISTORY_TURNS * 2;
  const recent = history.slice(-maxMessages);
  return recent.map((item) => ({
    role: item.role === "assistant" ? "assistant" : "user",
    text: (item.text || "").slice(0, MAX_TURN_TEXT_LENGTH),
  }));
}

/**
 * Sends a message to the AI chat API (/api/v1/ai/chat).
 */
export async function askAssistant(options: AskAssistantOptions): Promise<ChatResponse> {
  if (isChatDisabled) {
    return { kind: "error", flagDisabled: true };
  }

  const rawMsg = options.message || "";
  const trimmedMsg = rawMsg.trim();
  if (!trimmedMsg) {
    return { kind: "error", message: "Message cannot be empty" };
  }

  const message = trimmedMsg.slice(0, MAX_MESSAGE_LENGTH);
  const history = sanitizeHistory(options.history);
  const page = options.page || (typeof window !== "undefined" ? window.location.pathname : "/");

  try {
    const res = await fetch("/api/v1/ai/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ message, history, page }),
    });

    if (res.status === 404) {
      setChatDisabledForSession(true);
      return { kind: "error", flagDisabled: true };
    }

    if (res.status === 429) {
      let retryAfter: number | undefined;
      try {
        const body = await res.json();
        if (typeof body?.retry_after_seconds === "number") {
          retryAfter = body.retry_after_seconds;
        }
      } catch {
        // Fall back without retry_after
      }
      return { kind: "rate_limited", retryAfterSeconds: retryAfter };
    }

    if (!res.ok) {
      return { kind: "error" };
    }

    const data = await res.json();
    if (!data || typeof data !== "object") {
      return { kind: "error" };
    }

    if (data.fallback === "no_answer") {
      return { kind: "no_answer" };
    }

    if (data.fallback === "busy") {
      return { kind: "busy" };
    }

    if (typeof data.answer === "string") {
      const citations: ChatCitation[] = Array.isArray(data.citations)
        ? data.citations.filter(
            (c: unknown): c is ChatCitation =>
              typeof c === "object" &&
              c !== null &&
              typeof (c as ChatCitation).n === "number" &&
              typeof (c as ChatCitation).url === "string",
          )
        : [];

      const cards: ChatCard[] = Array.isArray(data.cards)
        ? data.cards.filter(
            (cd: unknown): cd is ChatCard =>
              typeof cd === "object" && cd !== null && typeof (cd as ChatCard).slug === "string",
          )
        : [];

      return {
        kind: "answer",
        answer: data.answer,
        citations,
        cards,
      };
    }

    return { kind: "error" };
  } catch {
    return { kind: "error" };
  }
}
