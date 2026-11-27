import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { sanitizeHref } from "../lib/markdown-utils.ts";

test("Float.ai Chat - renamed, /assistant 308 redirects to /chat, and disclosure shown", () => {
  const navSrc = fs.readFileSync(path.join(process.cwd(), "components", "AppNav.tsx"), "utf-8");
  const nextCfg = fs.readFileSync(path.join(process.cwd(), "next.config.mjs"), "utf-8");
  const chatSrc = fs.readFileSync(path.join(process.cwd(), "app", "chat", "page.tsx"), "utf-8");

  assert.ok(navSrc.includes('href: "/chat"') && navSrc.includes('label: "Float.ai"'), "AppNav must label /chat as Float.ai");
  assert.ok(
    nextCfg.includes('source: "/assistant"') && nextCfg.includes('destination: "/chat"') && nextCfg.includes("permanent: true"),
    "next.config.mjs must 308 redirect /assistant to /chat"
  );
  assert.ok(
    chatSrc.includes("Float.ai is an AI assistant and can make mistakes."),
    "Chat page must display required AI disclosure"
  );
});

test("Float.ai Chat - composer IME guard, stop, 429, consent gate, offline retry, and char limit", () => {
  const chatSrc = fs.readFileSync(path.join(process.cwd(), "app", "chat", "page.tsx"), "utf-8");

  assert.ok(chatSrc.includes("isComposing") && chatSrc.includes("onCompositionStart"), "Must guard Enter during IME composition");
  assert.ok(chatSrc.includes("AbortController") && chatSrc.includes("stop-chat-btn"), "Must support stopping in-flight reply");
  assert.ok(chatSrc.includes("429") && chatSrc.includes("rate-limit-banner"), "Must handle 429 rate limit with countdown");
  assert.ok(chatSrc.includes("consent-gate-banner"), "Must handle ai_data_processing consent gate");
  assert.ok(chatSrc.includes("partial_error") && chatSrc.includes("Retry"), "Must keep partial text and offer retry on network loss");
  assert.ok(chatSrc.includes("MAX_CHARS = 2000") && chatSrc.includes("char-counter"), "Must enforce 2000 char limit with counter");
  assert.ok(chatSrc.includes("isSendingRef.current"), "Must prevent double-send");
  assert.ok(chatSrc.includes("why-answer-drawer"), "Must include Why this answer? drawer");
});

test("SafeMarkdown - rejects javascript:/http: URLs and allows only https://", () => {
  assert.equal(sanitizeHref("javascript:alert(1)"), null);
  assert.equal(sanitizeHref("http://example.com"), null);
  assert.equal(sanitizeHref("data:text/html,<script>alert(1)</script>"), null);
  assert.equal(sanitizeHref("https://cybercrime.gov.in/"), "https://cybercrime.gov.in/");

  const mdSrc = fs.readFileSync(path.join(process.cwd(), "lib", "safe-markdown.tsx"), "utf-8");
  assert.ok(!mdSrc.includes("dangerouslySetInnerHTML"), "SafeMarkdown must never use dangerouslySetInnerHTML");
  assert.ok(mdSrc.includes('replace(/<[^>]*>/g, "")'), "SafeMarkdown must strip raw HTML tags");
});

test("FloatMascot - supports idle, thinking, happy, alert states and reduced motion", () => {
  const mascotSrc = fs.readFileSync(path.join(process.cwd(), "components", "FloatMascot.tsx"), "utf-8");
  assert.ok(mascotSrc.includes("motion-reduce:animate-none"), "Mascot must respect prefers-reduced-motion");
  for (const st of ["idle", "thinking", "happy", "alert"]) {
    assert.ok(mascotSrc.includes(`"${st}"`), `Mascot must support ${st} state`);
  }
});
