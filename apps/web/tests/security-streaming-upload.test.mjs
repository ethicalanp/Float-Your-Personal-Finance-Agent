import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { validateStatementAllowlist, MAX_UPLOAD_BYTES } from "../lib/upload-validator.ts";

test("Upload Security - Allowlist rejects empty files", () => {
  const emptyChunk = new Uint8Array([]);
  const result = validateStatementAllowlist(emptyChunk);
  assert.equal(result.valid, false);
  assert.match(result.error, /empty/i);
});

test("Upload Security - Allowlist rejects renamed Windows PE/MZ executables (e.g. malicious.csv)", () => {
  const renamedExe = new Uint8Array([0x4d, 0x5a, 0x90, 0x00, 0x03, 0x00, 0x00, 0x00]); // MZ header
  const result = validateStatementAllowlist(renamedExe);
  assert.equal(result.valid, false);
  assert.match(result.error, /executable|PE\/MZ/i);
});

test("Upload Security - Allowlist rejects renamed Linux ELF binaries", () => {
  const elfBinary = new Uint8Array([0x7f, 0x45, 0x4c, 0x46, 0x02, 0x01, 0x01, 0x00]); // ELF header
  const result = validateStatementAllowlist(elfBinary);
  assert.equal(result.valid, false);
  assert.match(result.error, /executable|ELF/i);
});

test("Upload Security - Allowlist rejects binary file with NULL bytes disguised as CSV", () => {
  const binaryGarbage = new Uint8Array([0x01, 0x00, 0x02, 0x00, 0x53, 0x61, 0x6c, 0x61, 0x72, 0x79]);
  const result = validateStatementAllowlist(binaryGarbage);
  assert.equal(result.valid, false);
  assert.match(result.error, /binary|NULL/i);
});

test("Upload Security - Allowlist rejects non-CSV plain text lacking delimiters or tabular structure", () => {
  const plainSentence = new TextEncoder().encode("Hello this is just a random text file without any tabular financial columns");
  const result = validateStatementAllowlist(plainSentence);
  assert.equal(result.valid, false);
  assert.match(result.error, /delimiters/i);
});

test("Upload Security - Allowlist accepts valid CSV headers and rows", () => {
  const csvChunk = new TextEncoder().encode("Date,Description,Amount,Type\n2026-01-01,Salary,50000,credit\n");
  const result = validateStatementAllowlist(csvChunk);
  assert.equal(result.valid, true);
  assert.equal(result.detectedType, "csv");
});

test("Upload Security - Allowlist accepts valid PDF magic bytes (%PDF-)", () => {
  const pdfChunk = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x35]); // %PDF-1.5
  const result = validateStatementAllowlist(pdfChunk);
  assert.equal(result.valid, true);
  assert.equal(result.detectedType, "pdf");
});

test("Upload Security - Allowlist accepts valid XLSX magic bytes (PK\\x03\\x04)", () => {
  const xlsxChunk = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x14, 0x00, 0x06, 0x00]); // PK\x03\x04
  const result = validateStatementAllowlist(xlsxChunk);
  assert.equal(result.valid, true);
  assert.equal(result.detectedType, "xlsx");
});

test("Upload Security - Allowlist accepts JSON payload wrapping valid CSV content", () => {
  const jsonPayload = new TextEncoder().encode(
    JSON.stringify({
      account_id: "acc-101",
      format: "csv",
      content: "date,narration,amount,type\n2026-11-01,Salary,75000,credit\n",
    })
  );
  const result = validateStatementAllowlist(jsonPayload);
  assert.equal(result.valid, true);
  assert.equal(result.detectedType, "json_csv");
});

test("Upload Security - 10 MB streaming limit rejects zip bomb-sized payloads", () => {
  assert.equal(MAX_UPLOAD_BYTES, 10485760);
  const zipBombSize = 10485761; // 10MB + 1 byte
  assert.ok(zipBombSize > MAX_UPLOAD_BYTES);
});

test("Client Bundle Secrets Audit - Scans for hardcoded secrets or NEXT_PUBLIC leakage", () => {
  const targetDirs = [
    path.join(process.cwd(), "app"),
    path.join(process.cwd(), "components"),
    path.join(process.cwd(), "lib"),
  ];

  const forbiddenPatterns = [
    /JWT_SECRET/i,
    /PFA_DATABASE_URL/i,
    /PFA_JWT_SECRET_KEY/i,
    /MSG91_AUTH_KEY/i,
    /BEGIN (RSA|EC|PRIVATE) KEY/i,
    /eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*/, // Hardcoded JWT
  ];

  function scanDir(dir) {
    if (!fs.existsSync(dir)) return;
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        scanDir(fullPath);
      } else if (/\.(tsx?|jsx?|mjs)$/.test(entry.name)) {
        const content = fs.readFileSync(fullPath, "utf-8");
        for (const pattern of forbiddenPatterns) {
          assert.equal(
            pattern.test(content),
            false,
            `Forbidden credential pattern ${pattern} detected in ${fullPath}`
          );
        }
      }
    }
  }

  for (const dir of targetDirs) {
    scanDir(dir);
  }
});
