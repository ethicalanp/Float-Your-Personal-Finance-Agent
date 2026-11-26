"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  Send,
  Bot,
  User,
  ShieldCheck,
  AlertTriangle,
  Info,
  ExternalLink,
  BookOpen,
  ArrowRight,
  RefreshCw,
} from "lucide-react";
import AppShell from "@/components/AppShell";
import { getApiClient } from "@/lib/api";
import type { CitationItem } from "@float/api-client";

interface Message {
  id: string;
  sender: "user" | "assistant";
  text: string;
  status?: "answered" | "insufficient_evidence" | "refusal" | "degraded_fallback" | "rate_limited";
  citations?: CitationItem[];
  timestamp: string;
}

const SUGGESTED_QUESTIONS = [
  "What is the RBI 3-day zero liability rule for cyber fraud?",
  "How do I report an unauthorized UPI payment?",
  "What is the National Cybercrime Helpline number?",
  "What are the red flags of a digital arrest scam?",
];

export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      sender: "assistant",
      text: "Hello! I am your Float financial assistant. You can ask me about official banking rules, fraud recovery, cybercrime helplines (such as 1930), and your cash flow.",
      status: "answered",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [hasConsent, setHasConsent] = useState<boolean | null>(null);
  const [consentChecking, setConsentChecking] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const api = getApiClient();

  useEffect(() => {
    async function checkConsent() {
      try {
        const res = await fetch("/api/auth/me");
        if (res.ok) {
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
    }
    checkConsent();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(questionText?: string) {
    const q = (questionText || input).trim();
    if (!q || loading) return;

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: q,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      // Call knowledge RAG endpoint first for grounded answer
      const res = await api.assistant.askKnowledge({ question: q });

      let assistantStatus: Message["status"] = "answered";
      if (res.status === "insufficient_evidence") assistantStatus = "insufficient_evidence";
      else if (res.status === "refusal") assistantStatus = "refusal";
      else if (res.status === "degraded_fallback") assistantStatus = "degraded_fallback";

      const botMsg: Message = {
        id: `bot-${Date.now()}`,
        sender: "assistant",
        text: res.answer,
        status: assistantStatus,
        citations: res.citations || [],
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch (err: any) {
      const isRateLimited = err.status === 429 || err.code === "BUDGET_EXCEEDED";
      const isConsentErr = err.status === 403 || err.message?.toLowerCase().includes("consent");

      if (isConsentErr) {
        setHasConsent(false);
      }

      const errMsg: Message = {
        id: `err-${Date.now()}`,
        sender: "assistant",
        text: isRateLimited
          ? "Daily AI query limit reached. Please check back tomorrow or refer directly to National Cybercrime Helpline 1930."
          : isConsentErr
            ? "AI data processing consent is required to converse with Float Assistant. Please enable consent."
            : "The assistant service is temporarily degraded. For urgent fraud assistance, please call 1930 directly.",
        status: isRateLimited ? "rate_limited" : "degraded_fallback",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  }

  // Safe formatting without raw HTML
  function renderFormattedText(text: string) {
    return (
      <div className="space-y-1.5 whitespace-pre-wrap leading-relaxed text-xs">
        {text.split("\n\n").map((para, i) => (
          <p key={i}>{para}</p>
        ))}
      </div>
    );
  }

  return (
    <AppShell>
      <div className="space-y-4">
        {/* Header */}
        <div>
          <span className="cnl-kicker text-xs font-semibold text-accent uppercase tracking-wider">
            Grounded AI Guidance
          </span>
          <h1 className="text-3xl font-serif font-normal text-ink sm:text-4xl">
            Float Assistant
          </h1>
          <p className="mt-1 text-xs text-mute">
            Answers citing official RBI, I4C, and NPCI directives. No LLM arithmetic on money.
          </p>
        </div>

        {/* Consent Required Notice */}
        {!consentChecking && hasConsent === false && (
          <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4 sm:p-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between dark:border-amber-900/50 dark:bg-amber-950/20">
            <div className="flex items-center gap-3">
              <ShieldCheck className="h-5 w-5 text-amber-700 dark:text-amber-400 shrink-0" />
              <div>
                <h4 className="text-xs font-bold text-amber-950 dark:text-amber-200">
                  AI Processing Consent Needed
                </h4>
                <p className="text-xs text-amber-800 dark:text-amber-300">
                  Under DPDP Act 2023, grant consent for Float to process questions and provide grounded assistance.
                </p>
              </div>
            </div>
            <Link
              href="/consent"
              className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-white hover:bg-accent/90 shrink-0"
            >
              <span>Enable Consent</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}

        {/* Chat Window Container */}
        <div className="rounded-3xl border border-line bg-card shadow-sm flex flex-col h-[580px] overflow-hidden">
          {/* Messages Scroll Area */}
          <div
            className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4"
            role="log"
            aria-live="polite"
            aria-label="Conversation history"
          >
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.sender === "assistant" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent mt-0.5">
                    <Bot className="h-4 w-4" />
                  </div>
                )}

                <div
                  className={`max-w-[85%] sm:max-w-[75%] rounded-2xl p-4 shadow-sm ${msg.sender === "user"
                    ? "bg-ink text-bg"
                    : "bg-soft/50 border border-line text-ink"
                    }`}
                >
                  {/* Status Indicator for Assistant */}
                  {msg.sender === "assistant" && msg.status && (
                    <div className="mb-2 flex items-center gap-1.5">
                      {msg.status === "answered" && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-400">
                          <BookOpen className="h-3 w-3" /> Grounded in Official Sources
                        </span>
                      )}
                      {msg.status === "insufficient_evidence" && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-amber-700 dark:text-amber-400">
                          <AlertTriangle className="h-3 w-3" /> Insufficient Evidence
                        </span>
                      )}
                      {msg.status === "refusal" && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-red-700 dark:text-red-400">
                          <ShieldCheck className="h-3 w-3" /> Policy Guardrail
                        </span>
                      )}
                      {msg.status === "degraded_fallback" && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-amber-700 dark:text-amber-400">
                          <Info className="h-3 w-3" /> Degraded Fallback Mode
                        </span>
                      )}
                      {msg.status === "rate_limited" && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-rose-700 dark:text-rose-400">
                          <AlertTriangle className="h-3 w-3" /> 429 Daily Limit
                        </span>
                      )}
                    </div>
                  )}

                  {/* Body text safely rendered */}
                  {renderFormattedText(msg.text)}

                  {/* Citation Cards */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-3 border-t border-line/60 pt-2.5 space-y-1.5">
                      <span className="text-[10px] font-semibold text-mute uppercase tracking-wider">
                        Citations & Verified References:
                      </span>
                      <div className="grid grid-cols-1 gap-1.5">
                        {msg.citations.map((c, idx) => (
                          <div
                            key={c.chunk_id || idx}
                            className="flex items-center justify-between rounded-lg border border-line bg-card p-2 text-[11px]"
                          >
                            <div className="truncate pr-2">
                              {c.publisher && (
                                <span className="font-bold text-accent mr-1">[{c.publisher}]</span>
                              )}
                              <span className="font-medium text-ink">{c.source_title}</span>
                            </div>
                            {c.source_url?.startsWith("https://") && (
                              <a
                                href={c.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-accent hover:underline shrink-0 font-medium"
                              >
                                <span>Verify</span>
                                <ExternalLink className="h-2.5 w-2.5" />
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="mt-2 text-right text-[10px] text-faint">{msg.timestamp}</div>
                </div>

                {msg.sender === "user" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-ink/10 text-ink mt-0.5">
                    <User className="h-4 w-4" />
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent/10 text-accent">
                  <Bot className="h-4 w-4 animate-pulse" />
                </div>
                <div className="rounded-2xl border border-line bg-soft/40 p-4 text-xs text-mute flex items-center gap-2">
                  <RefreshCw className="h-3 w-3 animate-spin text-accent" />
                  <span>Searching verified regulatory knowledge base...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Suggested Questions */}
          <div className="border-t border-line bg-soft/20 px-4 py-2.5 overflow-x-auto flex gap-2">
            <span className="text-[10px] text-faint shrink-0 self-center font-medium">Try asking:</span>
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => handleSend(q)}
                disabled={loading}
                className="rounded-full border border-line bg-card px-3 py-1 text-[11px] text-mute whitespace-nowrap hover:border-accent hover:text-ink disabled:opacity-50 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>

          {/* Chat Composer */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="border-t border-line bg-card p-3 sm:p-4 flex gap-2"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a question about bank regulations, scam recovery, or cash flow..."
              disabled={loading}
              className="flex-1 rounded-xl border border-line bg-soft/50 px-4 py-2.5 text-xs text-ink placeholder-faint focus:border-accent focus:bg-card focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center justify-center rounded-xl bg-accent px-4 py-2.5 text-white hover:bg-accent/90 disabled:opacity-50 transition-colors shadow-sm"
              title="Send question"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>

        {/* Legal Disclaimer */}
        <p className="text-center text-[11px] text-faint max-w-2xl mx-auto">
          Float AI provides educational information grounded in official RBI, NPCI, and I4C regulatory notices. It does not provide certified financial, legal, or investment advice.
        </p>
      </div>
    </AppShell>
  );
}
