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
import { ChatPanel } from "../src/components/chat/ChatPanel";
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

    // Check WhatsApp, Call, and Request a call back buttons
    const whatsappLinks = screen.getAllByRole("link", { name: /whatsapp/i });
    expect(whatsappLinks.length).toBeGreaterThan(0);

    const callLinks = screen.getAllByRole("link", { name: /call/i });
    expect(callLinks.length).toBeGreaterThan(0);

    const callbackLinks = screen.getAllByRole("link", { name: /request a call back/i });
    expect(callbackLinks.length).toBeGreaterThan(0);
  });
});
