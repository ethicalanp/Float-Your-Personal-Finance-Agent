/**
 * Allowlist validation for financial statement uploads.
 * Replaces blocklists with a strict allowlist of supported types:
 * - PDF (%PDF-)
 * - XLSX (PK\x03\x04)
 * - CSV / Plain Text (Printable ASCII / UTF-8 with standard delimiters, no binary NULLs)
 * - JSON payload containing valid CSV content
 * 
 * Rejects empty files, executables (even if renamed .csv), zip bombs (>10MB), and unsupported binary formats.
 */

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // 10 MB

export interface ValidationResult {
  valid: boolean;
  detectedType?: "pdf" | "xlsx" | "csv" | "json_csv";
  error?: string;
}

/**
 * Validates the initial chunk of an uploaded file or JSON payload against the strict allowlist.
 */
export function validateStatementAllowlist(chunk: Uint8Array): ValidationResult {
  if (!chunk || chunk.length === 0) {
    return { valid: false, error: "Empty file: File must contain valid statement data." };
  }

  // 1. PDF Allowlist: Magic bytes %PDF- (0x25, 0x50, 0x44, 0x46, 0x2D)
  if (
    chunk.length >= 4 &&
    chunk[0] === 0x25 &&
    chunk[1] === 0x50 &&
    chunk[2] === 0x44 &&
    chunk[3] === 0x46
  ) {
    return { valid: true, detectedType: "pdf" };
  }

  // 2. XLSX Allowlist: Magic bytes PK\x03\x04 (0x50, 0x4B, 0x03, 0x04)
  if (
    chunk.length >= 4 &&
    chunk[0] === 0x50 &&
    chunk[1] === 0x4b &&
    chunk[2] === 0x03 &&
    chunk[3] === 0x04
  ) {
    return { valid: true, detectedType: "xlsx" };
  }

  // Explicitly reject known executable signatures before checking text sanity (defense-in-depth)
  // DOS MZ executable (PE) - e.g. renamed .exe to .csv
  if (chunk.length >= 2 && chunk[0] === 0x4d && chunk[1] === 0x5a) {
    return { valid: false, error: "Executable binary detected (PE/MZ). Executable files are strictly forbidden." };
  }

  // ELF executable
  if (chunk.length >= 4 && chunk[0] === 0x7f && chunk[1] === 0x45 && chunk[2] === 0x4c && chunk[3] === 0x46) {
    return { valid: false, error: "Executable binary detected (ELF). Executable files are strictly forbidden." };
  }

  // Mach-O / Java Class
  if (chunk.length >= 4 && chunk[0] === 0xca && chunk[1] === 0xfe && chunk[2] === 0xba && chunk[3] === 0xbe) {
    return { valid: false, error: "Binary class/executable detected." };
  }

  // 3. JSON Payload wrapping statement content: Starts with '{'
  const firstNonWhitespaceIndex = chunk.findIndex((b) => b !== 0x20 && b !== 0x09 && b !== 0x0a && b !== 0x0d);
  if (firstNonWhitespaceIndex !== -1 && chunk[firstNonWhitespaceIndex] === 0x7b) {
    try {
      const text = new TextDecoder("utf-8").decode(chunk);
      // Fast check for JSON structure
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed.content === "string") {
        if (!parsed.content.trim()) {
          return { valid: false, error: "Empty content in upload payload." };
        }
        // Validate internal CSV content
        const contentBytes = new TextEncoder().encode(parsed.content.slice(0, 1024));
        const subCheck = validateTextCsvContent(contentBytes);
        if (!subCheck.valid) {
          return subCheck;
        }
        return { valid: true, detectedType: "json_csv" };
      }
    } catch {
      // Partial JSON chunk or plain text starting with '{', fall through to text validation
    }
  }

  // 4. CSV / Plain Text Sanity Check
  return validateTextCsvContent(chunk);
}

/**
 * Validates that a chunk contains valid, printable CSV or tabular text without binary NULLs or control characters.
 */
function validateTextCsvContent(chunk: Uint8Array): ValidationResult {
  const sampleLength = Math.min(chunk.length, 2048);
  let hasDelimiters = false;
  let hasNewline = false;
  let printableCount = 0;

  for (let i = 0; i < sampleLength; i++) {
    const b = chunk[i];

    // Reject NULL bytes immediately (binary file indicator)
    if (b === 0x00) {
      return { valid: false, error: "Binary data detected with NULL bytes. File is not a valid text/CSV statement." };
    }

    // Check for standard CSV delimiters: comma (0x2C), semicolon (0x3B), tab (0x09)
    if (b === 0x2c || b === 0x3b || b === 0x09) {
      hasDelimiters = true;
    }

    // Check for newline (0x0A, 0x0D)
    if (b === 0x0a || b === 0x0d) {
      hasNewline = true;
    }

    // Check if character is printable ASCII (0x20 to 0x7E) or allowed control (tab, CR, LF) or UTF-8 multibyte (>= 0x80)
    if ((b >= 0x20 && b <= 0x7e) || b === 0x09 || b === 0x0a || b === 0x0d || b >= 0x80) {
      printableCount++;
    } else {
      // Unprintable control character (< 0x09 or between 0x0E and 0x1F)
      return { valid: false, error: `Invalid binary control character (0x${b.toString(16)}) detected.` };
    }
  }

  const printableRatio = printableCount / sampleLength;
  if (printableRatio < 0.95) {
    return { valid: false, error: "Content sanity failed: Low printable character ratio." };
  }

  // Must contain at least some tabular or structured text indicators (delimiter or newline)
  if (!hasDelimiters && !hasNewline) {
    return { valid: false, error: "Content sanity failed: No CSV delimiters or newlines found in text." };
  }

  return { valid: true, detectedType: "csv" };
}
