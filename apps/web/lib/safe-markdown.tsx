import React from "react";
import { sanitizeHref } from "./markdown-utils";

export { sanitizeHref };

function renderInline(text: string): React.ReactNode[] {
  // Strip any raw HTML tags before tokenizing
  const clean = text.replace(/<[^>]*>/g, "");
  const tokens: React.ReactNode[] = [];
  const pattern = /(\[[^\]]+\]\([^)]+\)|`[^`]+`|\*\*[^*]+\*\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyIdx = 0;

  while ((match = pattern.exec(clean)) !== null) {
    if (match.index > lastIndex) {
      tokens.push(clean.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("[")) {
      const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (linkMatch) {
        const safeUrl = sanitizeHref(linkMatch[2]);
        if (safeUrl) {
          tokens.push(
            <a
              key={`lnk-${keyIdx++}`}
              href={safeUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent underline hover:opacity-80"
            >
              {linkMatch[1]}
            </a>
          );
        } else {
          tokens.push(linkMatch[1]);
        }
      }
    } else if (token.startsWith("`")) {
      tokens.push(
        <code key={`code-${keyIdx++}`} className="rounded bg-soft px-1.5 py-0.5 font-mono text-[12px] text-ink">
          {token.slice(1, -1)}
        </code>
      );
    } else if (token.startsWith("**")) {
      tokens.push(
        <strong key={`b-${keyIdx++}`} className="font-semibold text-ink">
          {token.slice(2, -2)}
        </strong>
      );
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < clean.length) {
    tokens.push(clean.slice(lastIndex));
  }
  return tokens;
}

export function SafeMarkdown({ content }: { content: string }) {
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;
  let blockKey = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    if (line.trim().startsWith("```")) {
      const codeLines: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i += 1;
      }
      i += 1;
      elements.push(
        <pre key={`pre-${blockKey++}`} className="overflow-x-auto rounded-xl border border-line bg-bg p-3 font-mono text-xs text-ink">
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    // Markdown table
    if (line.includes("|") && i + 1 < lines.length && /^\s*\|?[\s:-]+\|/.test(lines[i + 1])) {
      const headerCells = line.split("|").map((c) => c.trim()).filter(Boolean);
      i += 2; // skip header + separator
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|")) {
        rows.push(lines[i].split("|").map((c) => c.trim()).filter(Boolean));
        i += 1;
      }
      elements.push(
        <div key={`tbl-${blockKey++}`} className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-left text-xs">
            <thead className="bg-soft/60 text-ink">
              <tr>
                {headerCells.map((h, idx) => (
                  <th key={idx} className="px-3 py-2 font-semibold border-b border-line">
                    {renderInline(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rIdx) => (
                <tr key={rIdx} className="border-b border-line last:border-0">
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} className="px-3 py-2 text-ink">
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Bullet list
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i += 1;
      }
      elements.push(
        <ul key={`ul-${blockKey++}`} className="list-disc pl-5 space-y-1">
          {items.map((it, idx) => (
            <li key={idx}>{renderInline(it)}</li>
          ))}
        </ul>
      );
      continue;
    }

    if (line.trim() === "") {
      i += 1;
      continue;
    }

    elements.push(<p key={`p-${blockKey++}`}>{renderInline(line)}</p>);
    i += 1;
  }

  return <div className="space-y-2 text-sm leading-relaxed text-ink">{elements}</div>;
}
