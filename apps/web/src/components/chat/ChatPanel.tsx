"use client";
/**
 * Interactive Chat Assistant panel (Phase 7 Task 7.3, Scope 2).
 *
 * Implements:
 * - Non-modal dialog (role="dialog", aria-modal="false", aria-labelledby).
 * - Disclaimer notice under heading.
 * - Input text box with 500-character limit and character counter.
 * - Enter to send, Shift+Enter for newline.
 * - Polite live region announcing each new answer.
 * - COMPLIANCE: Answers rendered strictly as plain text. Only [n] markers become links to citations[n-1].url.
 * - Project cards fetched via /api/v1/public/projects/{slug}, never from model output.
 * - Fallbacks (no_answer, busy, 429, error) followed by WhatsApp, Call and Request a call back buttons.
 * - The same three contact buttons always sit at the bottom of the panel.
 * - Escape key closes panel and restores focus.
 */
import Link from "next/link";
import { useEffect, useRef, useState, useTransition } from "react";
import { Button } from "@empire/ui";
import { buildTelLink, buildWhatsAppLink, filterValue } from "@/lib/public/format";
import type { PublicSite } from "@/lib/public/api";
import { askAssistant, type ChatCard, type ChatCitation, type ChatTurn } from "@/lib/chat";
import { CHAT_COPY } from "./copy";
import { ProjectCard } from "./ProjectCard";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: ChatCitation[];
  cards?: ChatCard[];
  fallbackKind?: "no_answer" | "busy" | "rate_limited" | "error";
}

export interface ChatPanelProps {
  onClose: () => void;
  company?: PublicSite["company"];
  isProduction?: boolean;
}

const MAX_MESSAGE_LENGTH = 500;

export function ChatPanel({ onClose, company, isProduction = false }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [history, setHistory] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [liveAnnouncement, setLiveAnnouncement] = useState("");
  const [, startTransition] = useTransition();

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  // Close on Escape key (when focus is within this panel)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && panelRef.current?.contains(document.activeElement)) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Scroll to bottom on new message
  useEffect(() => {
    if (typeof messagesEndRef.current?.scrollIntoView === "function") {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, busy]);

  const rawPhone = company?.phones?.[0] ? filterValue(company.phones[0], isProduction) : null;
  const rawWhatsApp = company?.whatsapp ? filterValue(company.whatsapp, isProduction) : null;
  const effectiveWhatsApp = rawWhatsApp || rawPhone;
  const pagePath = typeof window !== "undefined" ? window.location.pathname : "/";

  const telHref = buildTelLink(rawPhone, isProduction);
  const whatsappHref = buildWhatsAppLink(
    effectiveWhatsApp,
    company?.whatsapp_message,
    pagePath,
    isProduction,
  );

  const handleSend = async () => {
    const trimmed = draft.trim();
    if (!trimmed || busy) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      text: trimmed,
    };

    setMessages((prev) => [...prev, userMsg]);
    setDraft("");
    setBusy(true);

    const res = await askAssistant({
      message: trimmed,
      history,
      page: pagePath,
    });

    startTransition(() => {
      setBusy(false);
      let assistantMsg: ChatMessage;

      if (res.kind === "answer") {
        assistantMsg = {
          id: `asst-${Date.now()}`,
          role: "assistant",
          text: res.answer,
          citations: res.citations,
          cards: res.cards,
        };
        setHistory((prev) => [
          ...prev,
          { role: "user", text: trimmed },
          { role: "assistant", text: res.answer },
        ]);
        setLiveAnnouncement(res.answer);
      } else if (res.kind === "no_answer") {
        assistantMsg = {
          id: `asst-${Date.now()}`,
          role: "assistant",
          text: CHAT_COPY.fallbackNoAnswer,
          fallbackKind: "no_answer",
        };
        setLiveAnnouncement(CHAT_COPY.fallbackNoAnswer);
      } else if (res.kind === "busy") {
        assistantMsg = {
          id: `asst-${Date.now()}`,
          role: "assistant",
          text: CHAT_COPY.fallbackBusy,
          fallbackKind: "busy",
        };
        setLiveAnnouncement(CHAT_COPY.fallbackBusy);
      } else if (res.kind === "rate_limited") {
        assistantMsg = {
          id: `asst-${Date.now()}`,
          role: "assistant",
          text: CHAT_COPY.fallbackRateLimited,
          fallbackKind: "rate_limited",
        };
        setLiveAnnouncement(CHAT_COPY.fallbackRateLimited);
      } else {
        assistantMsg = {
          id: `asst-${Date.now()}`,
          role: "assistant",
          text: CHAT_COPY.fallbackError,
          fallbackKind: "error",
        };
        setLiveAnnouncement(CHAT_COPY.fallbackError);
      }

      setMessages((prev) => [...prev, assistantMsg]);
    });
  };

  /**
   * COMPLIANCE: Renders model text as strictly plain text, converting only [n]
   * markers to citation links. HTML and Markdown are not evaluated.
   */
  const renderMessageContent = (msg: ChatMessage) => {
    if (msg.role === "user") {
      return <span>{msg.text}</span>;
    }

    const citations = msg.citations || [];
    const parts = msg.text.split(/(\[\d+\])/g);

    return (
      <div className="space-y-2">
        <div className="text-xs leading-relaxed text-sand-200">
          {parts.map((part, index) => {
            const match = part.match(/^\[(\d+)\]$/);
            if (match && match[1]) {
              const num = parseInt(match[1], 10);
              const citation = citations.find((c) => c.n === num) || citations[num - 1];
              if (citation) {
                const isSafe =
                  typeof citation.url === "string" &&
                  citation.url.startsWith("/") &&
                  !citation.url.startsWith("//");
                if (isSafe) {
                  return (
                    <Link
                      key={index}
                      href={citation.url}
                      title={citation.title}
                      className="inline-flex min-h-[44px] items-center px-0.5 font-bold text-gold-400 underline hover:text-gold-300"
                    >
                      [{num}] {citation.title}
                    </Link>
                  );
                }
                return (
                  <span key={index}>
                    [{num}] {citation.title}
                  </span>
                );
              }
            }
            return <span key={index}>{part}</span>;
          })}
        </div>

        {/* Citations list */}
        {citations.length > 0 && (
          <div className="mt-2 border-t border-noir-700/60 pt-2 text-xs">
            <span className="text-[11px] font-bold text-sand-400">
              {CHAT_COPY.citationsHeading}:
            </span>
            <ul className="mt-1 space-y-1">
              {citations.map((c) => {
                const isSafe =
                  typeof c.url === "string" && c.url.startsWith("/") && !c.url.startsWith("//");
                return (
                  <li key={c.n}>
                    {isSafe ? (
                      <Link
                        href={c.url}
                        className="inline-flex min-h-[44px] items-center text-gold-400 underline hover:text-gold-300"
                      >
                        [{c.n}] {c.title}
                      </Link>
                    ) : (
                      <span className="inline-flex min-h-[44px] items-center text-sand-300">
                        [{c.n}] {c.title}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Project Cards (loaded strictly from API) */}
        {msg.cards && msg.cards.length > 0 && (
          <div className="mt-2 space-y-2">
            {msg.cards.map((card) => (
              <ProjectCard key={card.slug} slug={card.slug} />
            ))}
          </div>
        )}

        {/* Action buttons following any fallback */}
        {msg.fallbackKind && (
          <div className="mt-3 flex flex-wrap gap-2 pt-2">
            {whatsappHref && (
              <a
                href={whatsappHref}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-[44px] items-center justify-center rounded-pill bg-palm-bg px-3 text-xs font-bold text-palm hover:brightness-110"
              >
                {CHAT_COPY.whatsappButton}
              </a>
            )}
            {telHref && (
              <a
                href={telHref}
                className="inline-flex min-h-[44px] items-center justify-center rounded-pill border border-gold-500/40 px-3 text-xs font-bold text-gold-300 hover:bg-gold-500/10"
              >
                {CHAT_COPY.callButton}
              </a>
            )}
            <Link
              href="/contact#visit"
              className="inline-flex min-h-[44px] items-center justify-center rounded-pill bg-gold-500 px-3 text-xs font-extrabold text-noir-900 hover:bg-gold-400"
            >
              {CHAT_COPY.requestCallbackButton}
            </Link>
          </div>
        )}
      </div>
    );
  };

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="false"
      aria-labelledby="chat-heading"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
      className="fixed bottom-[calc(64px+env(safe-area-inset-bottom)+8px)] left-3 right-3 z-40 flex max-h-[calc(100dvh-80px)] flex-col rounded-2xl border border-gold-500/40 bg-noir-800/98 shadow-2xl backdrop-blur-md sm:left-auto sm:right-4 sm:w-96 md:bottom-6 md:right-6 md:max-h-[36rem]"
    >
      {/* Header */}
      <div className="flex items-start justify-between border-b border-noir-700/80 p-4">
        <div>
          <h2 id="chat-heading" className="font-display text-sm font-bold text-sand-100">
            {CHAT_COPY.heading}
          </h2>
          <p className="mt-1 text-[11px] leading-relaxed text-sand-400">{CHAT_COPY.disclaimer}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={CHAT_COPY.closeAriaLabel}
          className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-full text-sand-400 hover:text-sand-100 focus-visible:outline-2 focus-visible:outline-gold-400"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Polite live region for announcing assistant replies */}
      <div aria-live="polite" className="sr-only">
        {liveAnnouncement}
      </div>

      {/* Messages */}
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`rounded-2xl px-3.5 py-2.5 max-w-[88%] text-xs ${
                m.role === "user"
                  ? "bg-gold-500/20 text-sand-100"
                  : "bg-noir-900/90 text-sand-200 border border-noir-700/70"
              }`}
            >
              {renderMessageContent(m)}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex items-start">
            <div className="rounded-2xl border border-noir-700/70 bg-noir-900/90 px-3.5 py-2.5 text-xs text-sand-400">
              {CHAT_COPY.loadingMessage}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Permanent contact buttons at the bottom of the panel */}
      <div className="border-t border-noir-700/60 bg-noir-900/40 p-2.5">
        <div className="flex items-center gap-1.5">
          {whatsappHref && (
            <a
              href={whatsappHref}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-pill bg-palm-bg px-2 text-[11px] font-bold text-palm hover:brightness-110"
            >
              {CHAT_COPY.whatsappButton}
            </a>
          )}
          {telHref && (
            <a
              href={telHref}
              className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-pill border border-gold-500/40 px-2 text-[11px] font-bold text-gold-300 hover:bg-gold-500/10"
            >
              {CHAT_COPY.callButton}
            </a>
          )}
          <Link
            href="/contact#visit"
            className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-pill bg-gold-500 px-2 text-[11px] font-extrabold text-noir-900 hover:bg-gold-400"
          >
            {CHAT_COPY.requestCallbackButton}
          </Link>
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-noir-700/80 p-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <textarea
              ref={inputRef}
              rows={2}
              maxLength={MAX_MESSAGE_LENGTH}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void handleSend();
                }
              }}
              placeholder={CHAT_COPY.inputPlaceholder}
              aria-label={CHAT_COPY.inputAriaLabel}
              className="w-full resize-none rounded-xl border border-noir-600 bg-noir-900 px-3 py-2 text-xs text-sand-100 placeholder:text-sand-500 focus:border-gold-400 focus:outline-none"
            />
            {draft.length > 400 && (
              <span className="absolute bottom-2 right-2 text-[10px] text-sand-500">
                {draft.length}/{MAX_MESSAGE_LENGTH}
              </span>
            )}
          </div>
          <Button
            variant="primary"
            disabled={!draft.trim() || busy}
            loading={busy}
            onClick={() => void handleSend()}
            className="min-h-11 self-end px-4 text-xs"
          >
            {CHAT_COPY.sendButton}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default ChatPanel;
