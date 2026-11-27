"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  Send,
  Square,
  Plus,
  Menu,
  X,
  Copy,
  Check,
  RotateCcw,
  ThumbsUp,
  ThumbsDown,
  Trash2,
  Edit3,
  ChevronDown,
  Info,
  ShieldAlert,
  ArrowRight,
  HelpCircle,
} from "lucide-react";
import AppShell from "@/components/AppShell";
import { FloatMascot, type MascotState } from "@/components/FloatMascot";
import { SafeMarkdown, sanitizeHref } from "@/lib/safe-markdown";
import type { CitationItem } from "@float/api-client";

const MAX_CHARS = 2000;

interface ConversationItem {
  id: string;
  title: string | null;
  created_at: string;
  last_message_at: string;
}

interface ChatMessage {
  id: string;
  sender: "user" | "assistant";
  text: string;
  status?: "success" | "clarification_needed" | "insufficient_evidence" | "refusal" | "degraded_fallback" | "partial_error";
  route?: string;
  citations?: CitationItem[];
  facts_used?: string[];
  trace_id?: string;
  timestamp: string;
  mascotState?: MascotState;
}

function formatISTTime(iso?: string): string {
  try {
    const d = iso ? new Date(iso) : new Date();
    return new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    }).format(d);
  } catch {
    return "";
  }
}

function mapLaneLabel(route?: string): string {
  if (!route) return "General Explanation";
  if (route === "personal_finance" || route === "credit_readiness" || route === "combined") {
    return "Personal Data (Read-Only Tools)";
  }
  if (route === "knowledge" || route === "protect") {
    return "Verified Knowledge Base (RAG)";
  }
  return "General Explanation";
}

function readDraft(convId: string | null): string {
  try {
    return localStorage.getItem(`float_chat_draft_${convId || "new"}`) || "";
  } catch {
    return "";
  }
}

function writeDraft(convId: string | null, value: string): void {
  try {
    const key = `float_chat_draft_${convId || "new"}`;
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {
    // ignore storage quota errors
  }
}

export default function FloatAiChatPage() {
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [hasConsent, setHasConsent] = useState<boolean | null>(null);
  const [consentChecking, setConsentChecking] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [rateLimitSec, setRateLimitSec] = useState<number>(0);

  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [feedbackState, setFeedbackState] = useState<Record<string, "up" | "down">>({});
  const [feedbackReasonFor, setFeedbackReasonFor] = useState<string | null>(null);
  const [feedbackReasonText, setFeedbackReasonText] = useState("");
  const [whyMsg, setWhyMsg] = useState<ChatMessage | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameText, setRenameText] = useState("");

  const [suggestedPrompts, setSuggestedPrompts] = useState<string[]>([
    "How do I report an unauthorized UPI payment on 1930?",
    "Explain the 50/30/20 monthly budgeting rule.",
    "What is the RBI 3-day zero liability rule?",
    "How can I improve my cash-flow stability?",
  ]);

  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const isSendingRef = useRef(false);
  const isComposingRef = useRef(false);
  const stickToBottomRef = useRef(true);

  useEffect(() => {
    setInput(readDraft(activeConvId));
  }, [activeConvId]);

  useEffect(() => {
    if (rateLimitSec <= 0) return;
    const id = setInterval(() => setRateLimitSec((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, [rateLimitSec]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const res = await fetch("/api/auth/me", { cache: "no-store" });
        if (res.status === 401) {
          setSessionExpired(true);
          setHasConsent(false);
        } else if (res.ok) {
          const data = await res.json();
          setHasConsent(Boolean(data.consent?.ai_data_processing_consent));
        } else {
          setHasConsent(false);
        }
      } catch {
        setHasConsent(false);
      } finally {
        setConsentChecking(false);
      }

      // Load conversations + dynamic prompt hints
      try {
        const cRes = await fetch("/api/backend/api/v1/assistant/conversations", { cache: "no-store" });
        if (cRes.ok) {
          const list = await cRes.json();
          if (Array.isArray(list)) setConversations(list);
        }
      } catch {
        // offline or empty
      }

      try {
        const [accRes, txRes] = await Promise.all([
          fetch("/api/backend/api/v1/plan/accounts"),
          fetch("/api/backend/api/v1/plan/transactions"),
        ]);
        const dynamicPrompts: string[] = [];
        const txs = txRes.ok ? await txRes.json() : [];
        if (Array.isArray(txs) && txs.length === 0) {
          dynamicPrompts.push("How do I upload a bank statement CSV safely?");
        } else {
          dynamicPrompts.push("Summarize my spending this month.");
        }
        const accs = accRes.ok ? await accRes.json() : [];
        if (Array.isArray(accs) && accs.length === 0) {
          dynamicPrompts.push("How do I set up my 50/30/20 monthly budget?");
        } else {
          dynamicPrompts.push("What bills are coming up soon?");
        }
        dynamicPrompts.push("What is the 1930 cybercrime helpline rule?");
        dynamicPrompts.push("What are the red flags of a digital arrest scam?");
        setSuggestedPrompts(dynamicPrompts.slice(0, 4));
      } catch {
        // keep default prompts
      }
    }
    bootstrap();
  }, []);

  useEffect(() => {
    if (stickToBottomRef.current && threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, sending]);

  function handleThreadScroll() {
    const el = threadRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const nearBottom = distanceFromBottom < 80;
    stickToBottomRef.current = nearBottom;
    setShowScrollBottom(!nearBottom);
  }

  function scrollToBottom() {
    if (!threadRef.current) return;
    stickToBottomRef.current = true;
    threadRef.current.scrollTop = threadRef.current.scrollHeight;
    setShowScrollBottom(false);
  }

  function handleInputChange(val: string) {
    const clamped = val.slice(0, MAX_CHARS);
    setInput(clamped);
    writeDraft(activeConvId, clamped);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(160, textareaRef.current.scrollHeight)}px`;
    }
  }

  async function selectConversation(convId: string) {
    setActiveConvId(convId);
    setDrawerOpen(false);
    try {
      const res = await fetch(`/api/backend/api/v1/assistant/conversations/${convId}/messages`, { cache: "no-store" });
      if (res.ok) {
        const rows = await res.json();
        setMessages(
          (rows || []).map((m: any) => ({
            id: m.id,
            sender: m.role === "user" ? "user" : "assistant",
            text: m.content,
            trace_id: m.trace_id || undefined,
            timestamp: formatISTTime(m.created_at),
            mascotState: "idle",
          }))
        );
      }
    } catch {
      // ignore
    }
  }

  function startNewChat() {
    setActiveConvId(null);
    setMessages([]);
    setWhyMsg(null);
    setDrawerOpen(false);
  }

  async function handleRenameConversation(convId: string) {
    if (!renameText.trim()) return;
    try {
      const res = await fetch(`/api/backend/api/v1/assistant/conversations/${convId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: renameText.trim() }),
      });
      if (res.ok) {
        const updated = await res.json();
        setConversations((prev) => prev.map((c) => (c.id === convId ? updated : c)));
      }
    } finally {
      setRenamingId(null);
      setRenameText("");
    }
  }

  async function handleDeleteConversation(convId: string) {
    try {
      const res = await fetch(`/api/backend/api/v1/assistant/conversations/${convId}`, { method: "DELETE" });
      if (res.ok) {
        setConversations((prev) => prev.filter((c) => c.id !== convId));
        if (activeConvId === convId) startNewChat();
      }
    } catch {
      // ignore
    }
  }

  async function handlePurgeAll() {
    try {
      const res = await fetch("/api/backend/api/v1/assistant/conversations", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true, confirmation_phrase: "DELETE_MY_CONVERSATIONS" }),
      });
      if (res.ok) {
        setConversations([]);
        startNewChat();
      }
    } catch {
      // ignore
    }
  }

  function handleStop() {
    abortRef.current?.abort();
    abortRef.current = null;
    setSending(false);
    isSendingRef.current = false;
  }

  async function sendQuestion(questionOverride?: string) {
    const q = (questionOverride ?? input).trim();
    if (!q || isSendingRef.current || q.length > MAX_CHARS) return;

    isSendingRef.current = true;
    setSending(true);
    setSessionExpired(false);

    if (!questionOverride) {
      setInput("");
      writeDraft(activeConvId, "");
      if (textareaRef.current) textareaRef.current.style.height = "auto";
    }

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: q,
      timestamp: formatISTTime(),
    };
    const pendingId = `ai-${Date.now() + 1}`;
    setMessages((prev) => [...prev, userMsg]);
    stickToBottomRef.current = true;

    const controller = new AbortController();
    abortRef.current = controller;

    let partialText = "";
    try {
      // Try real SSE streaming endpoint first; fall back to /chat on 501 or non-SSE
      const streamRes = await fetch("/api/backend/api/v1/assistant/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, conversation_id: activeConvId }),
        signal: controller.signal,
      });

      if (streamRes.status === 401) {
        setSessionExpired(true);
        writeDraft(activeConvId, q);
        return;
      }
      if (streamRes.status === 429) {
        const retryAfter = Number(streamRes.headers.get("Retry-After") || "30");
        setRateLimitSec(Number.isFinite(retryAfter) ? retryAfter : 30);
        setMessages((prev) => [
          ...prev,
          {
            id: pendingId,
            sender: "assistant",
            text: "Too many requests. Please wait a moment and try again.",
            status: "degraded_fallback",
            timestamp: formatISTTime(),
            mascotState: "alert",
          },
        ]);
        return;
      }

      const contentType = streamRes.headers.get("content-type") || "";
      if (streamRes.ok && contentType.includes("text/event-stream") && streamRes.body) {
        setMessages((prev) => [
          ...prev,
          { id: pendingId, sender: "assistant", text: "", timestamp: formatISTTime(), mascotState: "thinking" },
        ]);
        const reader = streamRes.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() || "";
          for (const frame of frames) {
            const eventLine = frame.split("\n").find((l) => l.startsWith("event:"));
            const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
            if (!dataLine) continue;
            const payload = JSON.parse(dataLine.slice(5).trim());
            if (eventLine?.includes("delta")) {
              partialText += payload.delta || "";
              setMessages((prev) => prev.map((m) => (m.id === pendingId ? { ...m, text: partialText } : m)));
            } else if (eventLine?.includes("done")) {
              const isAlert = payload.route === "protect" || payload.status === "refusal";
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === pendingId
                    ? {
                        ...m,
                        text: payload.answer || partialText,
                        status: payload.status,
                        route: payload.route,
                        citations: payload.citations || [],
                        facts_used: payload.facts_used || [],
                        trace_id: payload.trace_id,
                        mascotState: isAlert ? "alert" : "happy",
                      }
                    : m
                )
              );
            }
          }
        }
        return;
      }

      // Fallback to standard /chat endpoint
      const chatRes = await fetch("/api/backend/api/v1/assistant/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, conversation_id: activeConvId }),
        signal: controller.signal,
      });

      if (chatRes.status === 401) {
        setSessionExpired(true);
        writeDraft(activeConvId, q);
        return;
      }
      if (chatRes.status === 403) {
        setHasConsent(false);
        return;
      }
      if (chatRes.status === 429) {
        const retryAfter = Number(chatRes.headers.get("Retry-After") || "30");
        setRateLimitSec(Number.isFinite(retryAfter) ? retryAfter : 30);
        setMessages((prev) => [
          ...prev,
          {
            id: pendingId,
            sender: "assistant",
            text: "Rate limit reached. Please retry after the cooldown.",
            status: "degraded_fallback",
            timestamp: formatISTTime(),
            mascotState: "alert",
          },
        ]);
        return;
      }
      if (!chatRes.ok) {
        throw new Error(`HTTP ${chatRes.status}`);
      }

      const data = await chatRes.json();
      const isAlert = data.route === "protect" || data.status === "refusal";
      setMessages((prev) => [
        ...prev,
        {
          id: pendingId,
          sender: "assistant",
          text: data.answer,
          status: data.status,
          route: data.route,
          citations: data.citations || [],
          facts_used: data.facts_used || [],
          trace_id: data.trace_id,
          timestamp: formatISTTime(data.created_at),
          mascotState: isAlert ? "alert" : "happy",
        },
      ]);
    } catch (err: any) {
      if (err?.name === "AbortError") {
        if (partialText) {
          setMessages((prev) =>
            prev.map((m) => (m.id === pendingId ? { ...m, status: "partial_error", mascotState: "idle" } : m))
          );
        }
      } else {
        setMessages((prev) => {
          const exists = prev.some((m) => m.id === pendingId);
          if (exists) {
            return prev.map((m) =>
              m.id === pendingId
                ? {
                    ...m,
                    text: partialText || "Connection lost before Float.ai finished replying.",
                    status: "partial_error",
                    mascotState: "alert",
                  }
                : m
            );
          }
          return [
            ...prev,
            {
              id: pendingId,
              sender: "assistant",
              text: "Network error while contacting Float.ai. You can retry below.",
              status: "partial_error",
              timestamp: formatISTTime(),
              mascotState: "alert",
            },
          ];
        });
      }
    } finally {
      abortRef.current = null;
      setSending(false);
      isSendingRef.current = false;
    }
  }

  async function handleCopy(id: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 1500);
    } catch {
      // ignore clipboard errors
    }
  }

  async function handleFeedback(msg: ChatMessage, rating: "up" | "down", reason?: string) {
    setFeedbackState((prev) => ({ ...prev, [msg.id]: rating }));
    setFeedbackReasonFor(null);
    setFeedbackReasonText("");
    try {
      await fetch("/api/backend/api/v1/assistant/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating, trace_id: msg.trace_id || null, reason: reason || null }),
      });
    } catch {
      // ignore
    }
  }

  function handleRetryLast() {
    const lastUser = [...messages].reverse().find((m) => m.sender === "user");
    if (lastUser) sendQuestion(lastUser.text);
  }

  return (
    <AppShell>
      <div className="mx-auto flex h-[calc(100vh-8rem)] max-w-6xl gap-4">
        {/* Sidebar: Conversation List (Desktop + Mobile Drawer) */}
        <aside
          aria-label="Conversations"
          className={`${
            drawerOpen ? "fixed inset-y-0 left-0 z-50 flex w-72 bg-bg p-4 shadow-xl" : "hidden md:flex md:w-64"
          } flex-col rounded-2xl border border-line bg-card p-3 shrink-0`}
        >
          <div className="flex items-center justify-between gap-2 pb-3 border-b border-line">
            <button
              type="button"
              onClick={startNewChat}
              data-testid="new-chat-btn"
              className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-ink px-3 py-2 text-xs font-semibold text-bg hover:opacity-90"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>New chat</span>
            </button>
            {drawerOpen && (
              <button type="button" onClick={() => setDrawerOpen(false)} aria-label="Close sidebar" className="p-1.5 text-mute md:hidden">
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto py-2 space-y-1">
            {conversations.length === 0 ? (
              <p className="px-2 py-4 text-xs text-mute">No saved conversations yet.</p>
            ) : (
              conversations.map((c) => (
                <div
                  key={c.id}
                  className={`group flex items-center justify-between rounded-xl px-2.5 py-2 text-xs ${
                    activeConvId === c.id ? "bg-soft font-semibold text-ink" : "text-mute hover:bg-soft/60 hover:text-ink"
                  }`}
                >
                  {renamingId === c.id ? (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        handleRenameConversation(c.id);
                      }}
                      className="flex-1 flex gap-1"
                    >
                      <input
                        type="text"
                        value={renameText}
                        onChange={(e) => setRenameText(e.target.value)}
                        aria-label="Rename conversation"
                        className="w-full rounded border border-line bg-bg px-1.5 py-0.5 text-xs text-ink"
                      />
                      <button type="submit" className="text-accent font-semibold">OK</button>
                    </form>
                  ) : (
                    <>
                      <button type="button" onClick={() => selectConversation(c.id)} className="flex-1 truncate text-left">
                        {c.title || "Untitled chat"}
                      </button>
                      <div className="flex items-center gap-1 opacity-70 group-hover:opacity-100">
                        <button
                          type="button"
                          onClick={() => {
                            setRenamingId(c.id);
                            setRenameText(c.title || "");
                          }}
                          aria-label="Rename chat"
                          className="p-1 hover:text-ink"
                        >
                          <Edit3 className="h-3 w-3" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteConversation(c.id)}
                          aria-label="Delete chat"
                          className="p-1 hover:text-red-600"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))
            )}
          </div>

          {conversations.length > 0 && (
            <button
              type="button"
              onClick={handlePurgeAll}
              data-testid="purge-all-chats-btn"
              className="mt-2 w-full rounded-xl border border-line px-3 py-1.5 text-[11px] font-medium text-mute hover:text-red-600"
            >
              Purge all chats
            </button>
          )}
        </aside>

        {/* Main Chat Area */}
        <div className="relative flex flex-1 flex-col rounded-2xl border border-line bg-card overflow-hidden">
          {/* Top Bar */}
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={() => setDrawerOpen(true)}
                aria-label="Open conversations"
                className="rounded-lg border border-line p-1.5 text-mute md:hidden"
              >
                <Menu className="h-4 w-4" />
              </button>
              <FloatMascot state={sending ? "thinking" : "idle"} size="sm" decorative />
              <div>
                <h1 className="text-sm font-serif font-semibold text-ink">Float.ai</h1>
                <p className="text-[11px] text-mute" data-testid="ai-disclosure">
                  Float.ai is an AI assistant and can make mistakes.
                </p>
              </div>
            </div>
            {whyMsg && (
              <button
                type="button"
                onClick={() => setWhyMsg(null)}
                className="text-xs font-medium text-accent hover:underline"
              >
                Close explanation
              </button>
            )}
          </div>

          {/* Alerts: Session Expired, Consent Gate, Rate Limit */}
          {sessionExpired && (
            <div role="alert" className="mx-4 mt-3 flex items-center justify-between rounded-xl border border-red-300 bg-red-50 dark:bg-red-950/30 p-3 text-xs text-red-700 dark:text-red-300">
              <span>Your session expired. Sign in again — your draft is preserved.</span>
              <Link href="/login?return_to=%2Fchat" className="font-semibold underline">
                Log in
              </Link>
            </div>
          )}

          {!consentChecking && hasConsent === false && !sessionExpired && (
            <div role="alert" data-testid="consent-gate-banner" className="mx-4 mt-3 flex items-center justify-between gap-3 rounded-xl border border-amber-400/50 bg-amber-500/10 p-3 text-xs text-ink">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-amber-500 shrink-0" />
                <span>AI data processing consent is required before using Float.ai.</span>
              </div>
              <Link href="/consent" className="inline-flex items-center gap-1 font-semibold text-accent hover:underline shrink-0">
                <span>Grant Consent</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          )}

          {rateLimitSec > 0 && (
            <div role="status" data-testid="rate-limit-banner" className="mx-4 mt-3 rounded-xl border border-amber-400/50 bg-amber-500/10 p-2.5 text-xs text-ink">
              Rate limit active. Retry available in {rateLimitSec}s.
            </div>
          )}

          {/* Thread */}
          <div
            ref={threadRef}
            onScroll={handleThreadScroll}
            aria-live="polite"
            className="flex-1 overflow-y-auto px-4 py-6"
          >
            <div className="mx-auto max-w-3xl space-y-6">
              {messages.length === 0 ? (
                <div data-testid="chat-empty-state" className="py-8 text-center space-y-6">
                  <div className="flex flex-col items-center gap-3">
                    <FloatMascot state="idle" size="lg" label="Float.ai friendly floating buoy mascot" />
                    <h2 className="text-xl font-serif font-normal text-ink">How can Float.ai help today?</h2>
                    <p className="text-xs text-mute max-w-md">
                      Ask about your spending, recurring bills, RBI fraud rules (1930 helpline), or budgeting basics.
                    </p>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-left">
                    {suggestedPrompts.map((p) => (
                      <button
                        key={p}
                        type="button"
                        onClick={() => sendQuestion(p)}
                        disabled={hasConsent === false || sending}
                        className="rounded-2xl border border-line bg-bg p-3.5 text-xs font-medium text-ink hover:border-accent transition-colors disabled:opacity-50"
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((m) =>
                  m.sender === "user" ? (
                    <div key={m.id} className="flex justify-end">
                      <div className="max-w-[82%] rounded-2xl rounded-br-sm bg-ink px-4 py-3 text-sm text-bg">
                        <p className="whitespace-pre-wrap break-words">{m.text}</p>
                        <div className="mt-1 text-right text-[10px] opacity-70">{m.timestamp} IST</div>
                      </div>
                    </div>
                  ) : (
                    <div key={m.id} className="flex items-start gap-3">
                      <FloatMascot state={m.mascotState || "idle"} size="sm" decorative />
                      <div className="flex-1 min-w-0 space-y-2">
                        <div className="flex items-center gap-2 text-[11px] text-mute">
                          <span className="font-semibold text-ink">Float.ai</span>
                          <span>·</span>
                          <span>{m.timestamp} IST</span>
                          {m.route && (
                            <span className="rounded-full bg-soft px-2 py-0.5 text-[10px] font-medium text-ink">
                              {mapLaneLabel(m.route)}
                            </span>
                          )}
                        </div>

                        <SafeMarkdown content={m.text} />

                        {m.citations && m.citations.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 pt-1">
                            {m.citations.map((c) => {
                              const safeUrl = c.source_url ? sanitizeHref(c.source_url) : null;
                              return safeUrl ? (
                                <a
                                  key={c.chunk_id}
                                  href={safeUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="rounded-full border border-line bg-soft px-2.5 py-0.5 text-[11px] font-medium text-accent hover:underline"
                                >
                                  {c.source_title}
                                </a>
                              ) : (
                                <span key={c.chunk_id} className="rounded-full border border-line bg-soft px-2.5 py-0.5 text-[11px] text-mute">
                                  {c.source_title}
                                </span>
                              );
                            })}
                          </div>
                        )}

                        {(m.status === "partial_error" || m.status === "insufficient_evidence" || m.status === "degraded_fallback") && (
                          <button
                            type="button"
                            onClick={handleRetryLast}
                            className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink hover:bg-soft"
                          >
                            <RotateCcw className="h-3 w-3" />
                            <span>Retry</span>
                          </button>
                        )}

                        <div className="flex flex-wrap items-center gap-2 pt-1 text-mute">
                          <button
                            type="button"
                            onClick={() => handleCopy(m.id, m.text)}
                            aria-label="Copy message"
                            className="p-1 hover:text-ink"
                          >
                            {copiedId === m.id ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                          </button>
                          <button
                            type="button"
                            onClick={handleRetryLast}
                            aria-label="Regenerate response"
                            className="p-1 hover:text-ink"
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleFeedback(m, "up")}
                            aria-label="Thumbs up"
                            className={`p-1 ${feedbackState[m.id] === "up" ? "text-emerald-600" : "hover:text-ink"}`}
                          >
                            <ThumbsUp className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setFeedbackReasonFor(feedbackReasonFor === m.id ? null : m.id)}
                            aria-label="Thumbs down"
                            className={`p-1 ${feedbackState[m.id] === "down" ? "text-red-600" : "hover:text-ink"}`}
                          >
                            <ThumbsDown className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setWhyMsg(m)}
                            data-testid="why-answer-btn"
                            className="inline-flex items-center gap-1 text-[11px] font-medium hover:text-ink"
                          >
                            <HelpCircle className="h-3 w-3" />
                            <span>Why this answer?</span>
                          </button>
                        </div>

                        {feedbackReasonFor === m.id && (
                          <form
                            onSubmit={(e) => {
                              e.preventDefault();
                              handleFeedback(m, "down", feedbackReasonText);
                            }}
                            className="flex gap-2 pt-1"
                          >
                            <input
                              type="text"
                              value={feedbackReasonText}
                              onChange={(e) => setFeedbackReasonText(e.target.value)}
                              placeholder="Optional reason..."
                              aria-label="Feedback reason"
                              className="flex-1 rounded-lg border border-line bg-bg px-2.5 py-1 text-xs text-ink"
                            />
                            <button type="submit" className="rounded-lg bg-ink px-3 py-1 text-xs font-semibold text-bg">
                              Submit
                            </button>
                          </form>
                        )}
                      </div>
                    </div>
                  )
                )
              )}

              {sending && (
                <div data-testid="typing-indicator" className="flex items-center gap-3 text-xs text-mute">
                  <FloatMascot state="thinking" size="sm" decorative />
                  <span>Float.ai is thinking...</span>
                </div>
              )}
            </div>
          </div>

          {showScrollBottom && (
            <button
              type="button"
              onClick={scrollToBottom}
              aria-label="Scroll to bottom"
              className="absolute bottom-24 right-6 rounded-full border border-line bg-card p-2 shadow-md text-ink hover:bg-soft"
            >
              <ChevronDown className="h-4 w-4" />
            </button>
          )}

          {/* Why this answer? Drawer */}
          {whyMsg && (
            <div data-testid="why-answer-drawer" className="border-t border-line bg-soft/40 px-4 py-3 text-xs space-y-1">
              <div className="flex items-center gap-1.5 font-semibold text-ink">
                <Info className="h-3.5 w-3.5 text-accent" />
                <span>Why this answer?</span>
              </div>
              <div className="text-mute">
                Lane: <span className="font-medium text-ink">{mapLaneLabel(whyMsg.route)}</span>
                {whyMsg.facts_used && whyMsg.facts_used.length > 0 && (
                  <span> · Facts: {whyMsg.facts_used.join(", ")}</span>
                )}
              </div>
            </div>
          )}

          {/* Sticky Composer */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendQuestion();
            }}
            className="border-t border-line bg-card p-3 sm:p-4"
          >
            <div className="mx-auto max-w-3xl space-y-2">
              <div className="flex items-end gap-2 rounded-2xl border border-line bg-bg p-2">
                <textarea
                  ref={textareaRef}
                  rows={1}
                  value={input}
                  onChange={(e) => handleInputChange(e.target.value)}
                  onCompositionStart={() => {
                    isComposingRef.current = true;
                  }}
                  onCompositionEnd={() => {
                    isComposingRef.current = false;
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      if (e.nativeEvent.isComposing || isComposingRef.current) return;
                      e.preventDefault();
                      sendQuestion();
                    }
                  }}
                  disabled={hasConsent === false || sending}
                  placeholder="Ask Float.ai about spending, bills, or 1930 fraud rules..."
                  aria-label="Message Float.ai"
                  data-testid="chat-composer"
                  className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink placeholder:text-mute focus:outline-none disabled:opacity-50"
                />
                {sending ? (
                  <button
                    type="button"
                    onClick={handleStop}
                    data-testid="stop-chat-btn"
                    aria-label="Stop generating"
                    className="rounded-xl bg-red-600 p-2 text-white hover:bg-red-700"
                  >
                    <Square className="h-4 w-4" />
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!input.trim() || hasConsent === false || rateLimitSec > 0}
                    data-testid="send-chat-btn"
                    aria-label="Send message"
                    className="rounded-xl bg-ink p-2 text-bg hover:opacity-90 disabled:opacity-40"
                  >
                    <Send className="h-4 w-4" />
                  </button>
                )}
              </div>
              <div className="flex items-center justify-between px-1 text-[11px] text-mute">
                <span>Enter to send · Shift+Enter for new line</span>
                <span data-testid="char-counter">{input.length}/{MAX_CHARS}</span>
              </div>
            </div>
          </form>
        </div>
      </div>
    </AppShell>
  );
}
