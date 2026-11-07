// @vitest-environment jsdom
/**
 * Unit tests for chat client (Phase 7 Task 7.3, Scope 3).
 *
 * Verifies:
 * - reply types: answer, no_answer, busy, rate_limited, error
 * - contract limits: message length capped at 500 chars, history capped at last 2 turns (1000 chars each)
 * - 404 response flags chat as disabled to hide the launcher
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  askAssistant,
  isChatDisabledForSession,
  resetChatDisabledState,
  subscribeChatDisabled,
  type ChatTurn,
} from "../src/lib/chat";

describe("askAssistant client (Task 7.3 Scope 3)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    resetChatDisabledState();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    resetChatDisabledState();
  });

  it("handles successful 200 answer with citations and cards", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        answer: "Empire Heights has 3 BHK available [1].",
        citations: [{ n: 1, url: "/projects/empire-heights", title: "Empire Heights" }],
        cards: [{ slug: "empire-heights" }],
      }),
    });

    const res = await askAssistant({
      message: "3 BHK availability?",
      history: [],
      page: "/projects",
    });

    expect(res.kind).toBe("answer");
    if (res.kind === "answer") {
      expect(res.answer).toBe("Empire Heights has 3 BHK available [1].");
      expect(res.citations).toEqual([
        { n: 1, url: "/projects/empire-heights", title: "Empire Heights" },
      ]);
      expect(res.cards).toEqual([{ slug: "empire-heights" }]);
    }
  });

  it("handles 200 fallback: no_answer", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ fallback: "no_answer" }),
    });

    const res = await askAssistant({
      message: "What is the weather today?",
      history: [],
      page: "/",
    });

    expect(res.kind).toBe("no_answer");
  });

  it("handles 200 fallback: busy", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ fallback: "busy" }),
    });

    const res = await askAssistant({
      message: "Pricing details",
      history: [],
      page: "/",
    });

    expect(res.kind).toBe("busy");
  });

  it("handles 429 rate limited response with retry_after_seconds", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({ retry_after_seconds: 45 }),
    });

    const res = await askAssistant({
      message: "Fast messages",
      history: [],
      page: "/",
    });

    expect(res.kind).toBe("rate_limited");
    if (res.kind === "rate_limited") {
      expect(res.retryAfterSeconds).toBe(45);
    }
  });

  it("handles 404 response by setting chat as disabled and notifying subscribers", async () => {
    const listener = vi.fn();
    const unsub = subscribeChatDisabled(listener);

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Not found" }),
    });

    expect(isChatDisabledForSession()).toBe(false);

    const res = await askAssistant({
      message: "Hello",
      history: [],
      page: "/",
    });

    expect(res.kind).toBe("error");
    if (res.kind === "error") {
      expect(res.flagDisabled).toBe(true);
    }
    expect(isChatDisabledForSession()).toBe(true);
    expect(listener).toHaveBeenCalledWith(true);

    unsub();
  });

  it("handles network error or 500 response", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("Network failed"));

    const res = await askAssistant({
      message: "Hello",
      history: [],
      page: "/",
    });

    expect(res.kind).toBe("error");
    if (res.kind === "error") {
      expect(res.flagDisabled).toBeFalsy();
    }
  });

  it("enforces contract limits: message capped at 500 chars and history at last 2 turns (1000 chars each)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ fallback: "no_answer" }),
    });
    global.fetch = fetchMock;

    const longMessage = "a".repeat(600);
    const longTurnText = "x".repeat(1200);

    const history: ChatTurn[] = [
      { role: "user", text: "turn 1 user" },
      { role: "assistant", text: "turn 1 assistant" },
      { role: "user", text: "turn 2 user" },
      { role: "assistant", text: "turn 2 assistant" },
      { role: "user", text: longTurnText },
      { role: "assistant", text: "turn 3 assistant" },
    ];

    await askAssistant({
      message: longMessage,
      history,
      page: "/projects/empire-heights",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const callArgs = fetchMock.mock.calls[0];
    expect(callArgs).toBeDefined();
    if (!callArgs) throw new Error("Expected fetch to be called");
    expect(callArgs[0]).toBe("/api/v1/ai/chat");

    const init = callArgs[1] as RequestInit;
    const payload = JSON.parse(init.body as string);
    expect(payload.message.length).toBe(500);
    expect(payload.page).toBe("/projects/empire-heights");

    // History: at most last 2 turns (4 messages)
    expect(payload.history.length).toBe(4);
    // Each text capped at 1000 chars
    expect(payload.history[2].text.length).toBe(1000);
  });
});
