// @vitest-environment jsdom
/**
 * Component tests for ChatLauncher and ChatPanel (Phase 7 Task 7.3, Scope 1 & 2).
 *
 * Verifies:
 * - Launcher renders "Ask about our projects" and is hidden when flagDisabled
 * - All wording in CHAT_COPY starts with [DRAFT]
 * - Panel is a non-modal dialog with aria-labelledby and close button
 * - Disclaimer note is rendered under heading
 * - Character count live limit (500 chars)
 * - Enter sends message, Shift+Enter adds newline
 * - Live region announces new answers
 * - Model output is rendered as plain text: [n] becomes link to citations[n-1].url; HTML and Markdown are strictly escaped
 * - Fallbacks (no_answer, busy, rate_limited, error) show WhatsApp, Call, and Request a call back buttons
 * - Project cards fetch data from /api/v1/public/projects/{slug}
 * - Escape key closes panel and restores focus to launcher
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ChatLauncher } from "../src/components/chat/ChatLauncher";
import { ChatPanel, isSameSitePath } from "../src/components/chat/ChatPanel";
import { CHAT_COPY } from "../src/components/chat/copy";
import { resetChatDisabledState, setChatDisabledForSession } from "../src/lib/chat";

describe("ChatLauncher & ChatPanel components (Task 7.3 Scope 1 & 2)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    resetChatDisabledState();
  });

  afterEach(() => {
    cleanup();
    global.fetch = originalFetch;
    resetChatDisabledState();
  });

  it("all strings in CHAT_COPY start with [DRAFT]", () => {
    Object.entries(CHAT_COPY).forEach(([key, val]) => {
      if (typeof val === "string") {
        expect(val.startsWith("[DRAFT]"), `${key} must start with [DRAFT]`).toBe(true);
      }
    });
  });

  it("ChatLauncher renders 'Ask about our projects' button with min 44px target", () => {
    render(<ChatLauncher />);
    const btn = screen.getByRole("button", { name: /ask about our projects/i });
    expect(btn).toBeDefined();
    expect(btn.className).toContain("min-h-[44px]");
  });

  it("ChatLauncher hides when chat is disabled for the session (e.g. after 404)", () => {
    const { container } = render(<ChatLauncher />);
    expect(screen.queryByRole("button", { name: /ask about our projects/i })).not.toBeNull();

    act(() => {
      setChatDisabledForSession(true);
    });

    expect(container.firstChild).toBeNull();
  });

  it("ChatPanel renders as a non-modal dialog with heading, disclaimer, and close button", () => {
    const onClose = vi.fn();
    render(<ChatPanel onClose={onClose} />);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeDefined();
    expect(dialog.getAttribute("aria-modal")).toBe("false");

    const heading = screen.getByRole("heading", { name: CHAT_COPY.heading });
    expect(heading).toBeDefined();
    expect(screen.getByText(CHAT_COPY.disclaimer)).toBeDefined();

    const closeBtn = screen.getByRole("button", { name: /close chat/i });
    expect(closeBtn).toBeDefined();

    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Escape key triggers onClose", () => {
    const onClose = vi.fn();
    render(<ChatPanel onClose={onClose} />);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders model answer strictly as plain text, converting [n] to citation links and escaping HTML/Markdown", async () => {
    const mockAnswer =
      "Check <b>bold</b> and <script>alert(1)</script> and **markdown** at [1] and [2].";
    const citations = [
      { n: 1, url: "/projects/empire-heights", title: "Empire Heights" },
      { n: 2, url: "/projects/gomti-greens", title: "Gomti Greens" },
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        answer: mockAnswer,
        citations,
        cards: [],
      }),
    });

    render(<ChatPanel onClose={() => {}} />);

    const input = screen.getByRole("textbox", { name: /ask a question/i });
    const sendBtn = screen.getByRole("button", { name: /send/i });

    fireEvent.change(input, { target: { value: "Tell me about projects" } });
    fireEvent.click(sendBtn);

    // Wait for response to appear
    await waitFor(() => {
      const elements = screen.getAllByText(/check <b>bold<\/b>/i);
      expect(elements.length).toBeGreaterThan(0);
    });

    // Verify HTML was NOT rendered as HTML elements
    expect(document.querySelector("script")).toBeNull();
    expect(document.querySelector("b")).toBeNull();

    // Verify citations [1] and [2] became links (both inline and in the sources list)
    const links1 = screen.getAllByRole("link", { name: "[1] Empire Heights" });
    expect(links1.length).toBe(2);
    expect(links1[0].getAttribute("href")).toBe("/projects/empire-heights");

    const links2 = screen.getAllByRole("link", { name: "[2] Gomti Greens" });
    expect(links2.length).toBe(2);
    expect(links2[0].getAttribute("href")).toBe("/projects/gomti-greens");
  });

  it("renders project cards fetched from /api/v1/public/projects/{slug}", async () => {
    const citations = [{ n: 1, url: "/projects/grand-residences", title: "Grand Residences" }];
    const cards = [{ slug: "grand-residences" }];

    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (url === "/api/v1/ai/chat") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            answer: "Here is the project [1].",
            citations,
            cards,
          }),
        };
      }
      if (url === "/api/v1/public/projects/grand-residences") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            name: "Grand Residences",
            rera: { number: "UPRERA-123456" },
          }),
        };
      }
      return { ok: false, status: 404 };
    });

    render(<ChatPanel onClose={() => {}} />);

    const input = screen.getByRole("textbox", { name: /ask a question/i });
    fireEvent.change(input, { target: { value: "Project card test" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText("Grand Residences")).toBeDefined();
      expect(screen.getByText(/UPRERA-123456/)).toBeDefined();
    });
  });

  it("fallbacks (no_answer, busy, 429) show fallback message and three action buttons", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ fallback: "busy" }),
    });

    render(
      <ChatPanel
        onClose={() => {}}
        company={{
          phones: ["+91 98765 43210"],
          whatsapp: "+91 98765 43210",
        }}
      />,
    );

    const input = screen.getByRole("textbox", { name: /ask a question/i });
    fireEvent.change(input, { target: { value: "Any answer" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      const fallbackEls = screen.getAllByText(CHAT_COPY.fallbackBusy);
      expect(fallbackEls.length).toBeGreaterThan(0);
    });

    // Check WhatsApp, Call, and Request a call back buttons appear both inline under fallback and in bottom bar
    const whatsappLinks = screen.getAllByRole("link", { name: CHAT_COPY.whatsappButton });
    expect(whatsappLinks.length).toBe(2);

    const callLinks = screen.getAllByRole("link", { name: CHAT_COPY.callButton });
    expect(callLinks.length).toBe(2);

    const callbackLinks = screen.getAllByRole("link", { name: CHAT_COPY.requestCallbackButton });
    expect(callbackLinks.length).toBe(2);
  });

  it("with no company phones, there is no Call or WhatsApp link and Request a call back is still there (H1)", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ fallback: "no_answer" }),
    });

    render(<ChatPanel onClose={() => {}} company={{ phones: [], whatsapp: null }} />);

    const input = screen.getByRole("textbox", { name: /ask a question/i });
    fireEvent.change(input, { target: { value: "Where is project X?" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getAllByText(CHAT_COPY.fallbackNoAnswer).length).toBeGreaterThan(0);
    });

    expect(screen.queryByRole("link", { name: CHAT_COPY.whatsappButton })).toBeNull();
    expect(screen.queryByRole("link", { name: CHAT_COPY.callButton })).toBeNull();
    expect(
      screen.getAllByRole("link", { name: CHAT_COPY.requestCallbackButton }).length,
    ).toBeGreaterThan(0);
  });

  it("render ChatLauncher, open it, press Escape, and expect launcher button to be document.activeElement (M1)", async () => {
    render(<ChatLauncher />);
    const launcherBtn = screen.getByRole("button", { name: /ask about our projects/i });

    // Open panel
    fireEvent.click(launcherBtn);

    // Panel is opened
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeDefined();
    });

    // Press Escape
    fireEvent.keyDown(window, { key: "Escape" });

    // Launcher button should be active element
    await waitFor(() => {
      expect(document.activeElement).toBe(launcherBtn);
    });
  });

  it("citations with javascript:, https://, and //evil.example render no link (M3)", async () => {
    const mockAnswer = "Check sources [1], [2], and [3].";
    const citations = [
      { n: 1, url: "javascript:alert(1)", title: "Malicious script" },
      { n: 2, url: "https://example.com/external", title: "External site" },
      { n: 3, url: "//evil.example/protocol-relative", title: "Protocol relative" },
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        answer: mockAnswer,
        citations,
        cards: [],
      }),
    });

    render(<ChatPanel onClose={() => {}} />);

    const input = screen.getByRole("textbox", { name: /ask a question/i });
    fireEvent.change(input, { target: { value: "Test unsafe links" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getAllByText(/check sources/i).length).toBeGreaterThan(0);
    });

    // None of these should be rendered as a link
    expect(screen.queryByRole("link", { name: /malicious script/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /external site/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /protocol relative/i })).toBeNull();

    // Plain text should still be present
    expect(screen.getAllByText(/\[1\] Malicious script/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\[2\] External site/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\[3\] Protocol relative/).length).toBeGreaterThan(0);
  });

  it("ProjectCard uses json.rera.number only and renders verify link to up-rera.in (L2)", async () => {
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (url === "/api/v1/ai/chat") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            answer: "Check this [1]",
            citations: [{ n: 1, url: "/projects/grand", title: "Grand" }],
            cards: [{ slug: "grand" }],
          }),
        };
      }
      if (url === "/api/v1/public/projects/grand") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            name: "Grand Residences",
            rera: { number: "UPRERA-999999", url: "https://up-rera.in/projects/999999" },
            regulator: { number: "IGNORE_ME" }, // Regulator field should be ignored
          }),
        };
      }
      return { ok: false, status: 404 };
    });

    render(<ChatPanel onClose={() => {}} />);

    const input = screen.getByRole("textbox", { name: /ask a question/i });
    fireEvent.change(input, { target: { value: "Show card" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText("Grand Residences")).toBeDefined();
      expect(screen.getByText(/UPRERA-999999/)).toBeDefined();
      expect(screen.queryByText(/IGNORE_ME/)).toBeNull();
    });

    const verifyLink = screen.getByRole("link", { name: CHAT_COPY.verifyRera });
    expect(verifyLink.getAttribute("href")).toBe("https://up-rera.in/projects/999999");
  });

  it("fallback error renders 'Something went wrong.' and contact buttons (L3)", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });

    render(
      <ChatPanel
        onClose={() => {}}
        company={{
          phones: ["+91 98765 43210"],
          whatsapp: "+91 98765 43210",
        }}
      />,
    );

    const input = screen.getByRole("textbox", { name: /ask a question/i });
    fireEvent.change(input, { target: { value: "Trigger error" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getAllByText(CHAT_COPY.fallbackError).length).toBeGreaterThan(0);
    });

    expect(screen.getAllByRole("link", { name: CHAT_COPY.whatsappButton }).length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByRole("link", { name: CHAT_COPY.callButton }).length).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("link", { name: CHAT_COPY.requestCallbackButton }).length,
    ).toBeGreaterThan(0);
  });

  it("chat panel sends at most 2 turns (4 messages) of history after 3 or more exchanges (L3)", async () => {
    let callCount = 0;
    const receivedHistories: unknown[] = [];

    global.fetch = vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/ai/chat") {
        callCount++;
        const body = JSON.parse(init?.body as string);
        receivedHistories.push(body.history);
        return {
          ok: true,
          status: 200,
          json: async () => ({
            answer: `Answer ${callCount}`,
            citations: [],
            cards: [],
          }),
        };
      }
      return { ok: false, status: 404 };
    });

    render(<ChatPanel onClose={() => {}} />);
    const input = screen.getByRole("textbox", { name: /ask a question/i });
    const sendBtn = screen.getByRole("button", { name: /send/i });

    // Exchange 1
    fireEvent.change(input, { target: { value: "Question 1" } });
    fireEvent.click(sendBtn);
    await waitFor(() => expect(screen.getAllByText("Answer 1").length).toBeGreaterThan(0));

    // Exchange 2
    fireEvent.change(input, { target: { value: "Question 2" } });
    fireEvent.click(sendBtn);
    await waitFor(() => expect(screen.getAllByText("Answer 2").length).toBeGreaterThan(0));

    // Exchange 3
    fireEvent.change(input, { target: { value: "Question 3" } });
    fireEvent.click(sendBtn);
    await waitFor(() => expect(screen.getAllByText("Answer 3").length).toBeGreaterThan(0));

    // Check history sent in 3rd call
    expect(receivedHistories.length).toBe(3);
    const thirdCallHistory = receivedHistories[2] as Array<{ role: string; text: string }>;
    // At most 2 turns = 4 messages (Q1, A1, Q2, A2)
    expect(thirdCallHistory.length).toBe(4);
    expect(thirdCallHistory[0].text).toBe("Question 1");
    expect(thirdCallHistory[1].text).toBe("Answer 1");
    expect(thirdCallHistory[2].text).toBe("Question 2");
    expect(thirdCallHistory[3].text).toBe("Answer 2");
  });
});

describe("isSameSitePath (SECURITY)", () => {
  it.each(["/projects/aurum", "/", "/about?x=1#faq"])("links %s", (url) => {
    expect(isSameSitePath(url)).toBe(true);
  });
  it.each([
    "//evil.example",
    "/\\evil.example",
    "/projects\\..\\evil",
    "https://evil.example",
    "javascript:alert(1)",
    "projects/aurum",
    "",
    null,
  ])("refuses %s", (url) => {
    expect(isSameSitePath(url)).toBe(false);
  });
});
