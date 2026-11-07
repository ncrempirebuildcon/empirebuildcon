"use client";
/**
 * Lazy-loading launcher button for the AI chat assistant (Phase 7 Task 7.3, Scope 1).
 *
 * Implements:
 * - Small button fixed bottom-right on desktop, above MobileActionBar on phones.
 * - Min touch target 44x44 px.
 * - Dynamically loads ChatPanel via next/dynamic only when first pressed.
 * - Subscribes to chat disabled state (e.g. 404 from API); hides itself for the session.
 * - Restores focus to the launcher button when the panel closes.
 */
import dynamic from "next/dynamic";
import { useRef, useState, useSyncExternalStore } from "react";
import type { PublicSite } from "@/lib/public/api";
import { isChatDisabledForSession, subscribeChatDisabled } from "@/lib/chat";
import { CHAT_COPY } from "./copy";

const ChatPanel = dynamic(() => import("./ChatPanel"), { ssr: false });

export interface ChatLauncherProps {
  company?: PublicSite["company"];
  isProduction?: boolean;
}

export function ChatLauncher({ company, isProduction = false }: ChatLauncherProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [hasOpenedOnce, setHasOpenedOnce] = useState(false);
  const launcherRef = useRef<HTMLButtonElement | null>(null);

  // Sync disabled state across the session
  const isDisabled = useSyncExternalStore(
    subscribeChatDisabled,
    isChatDisabledForSession,
    () => false,
  );

  const handleToggle = () => {
    if (!isOpen) {
      setHasOpenedOnce(true);
      setIsOpen(true);
    } else {
      setIsOpen(false);
      launcherRef.current?.focus();
    }
  };

  const handleClose = () => {
    setIsOpen(false);
    launcherRef.current?.focus();
  };

  if (isDisabled) {
    return null;
  }

  return (
    <>
      {!isOpen && (
        <button
          ref={launcherRef}
          type="button"
          onClick={handleToggle}
          aria-expanded={isOpen}
          aria-label={CHAT_COPY.launcherLabel}
          className="fixed bottom-[calc(64px+env(safe-area-inset-bottom)+12px)] right-4 z-40 inline-flex min-h-[44px] items-center gap-2 rounded-full border border-gold-500/40 bg-noir-800/95 px-4 py-2.5 text-xs font-bold text-sand-100 shadow-xl backdrop-blur-md hover:border-gold-400 hover:text-gold-300 focus-visible:outline-2 focus-visible:outline-gold-400 md:bottom-6 md:right-6"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="text-gold-400"
            aria-hidden="true"
          >
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          <span>{CHAT_COPY.launcherLabel}</span>
        </button>
      )}

      {hasOpenedOnce && isOpen && (
        <ChatPanel onClose={handleClose} company={company} isProduction={isProduction} />
      )}
    </>
  );
}

export default ChatLauncher;
