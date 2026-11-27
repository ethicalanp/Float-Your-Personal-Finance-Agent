"use client";

import React from "react";

export type MascotState = "idle" | "thinking" | "happy" | "alert";

interface FloatMascotProps {
  state?: MascotState;
  size?: "sm" | "md" | "lg";
  decorative?: boolean;
  label?: string;
  className?: string;
}

/**
 * Original Float.ai mascot inspired by the 3 layered balance stones/waves in Logo.tsx.
 * Friendly floating buoy character with idle, thinking, happy, and alert states.
 */
export function FloatMascot({
  state = "idle",
  size = "md",
  decorative = false,
  label,
  className = "",
}: FloatMascotProps) {
  const px = size === "sm" ? 28 : size === "lg" ? 64 : 38;
  const defaultLabel =
    state === "thinking"
      ? "Float.ai is thinking"
      : state === "alert"
      ? "Float.ai scam alert warning"
      : state === "happy"
      ? "Float.ai mascot smiling"
      : "Float.ai mascot";

  const animClass =
    state === "idle"
      ? "animate-bounce motion-reduce:animate-none"
      : state === "thinking"
      ? "animate-pulse motion-reduce:animate-none"
      : "";

  const accentStroke =
    state === "alert"
      ? "text-amber-500 dark:text-amber-400"
      : state === "happy"
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-accent";

  return (
    <span
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : label || defaultLabel}
      data-testid={`float-mascot-${state}`}
      className={`inline-flex items-center justify-center shrink-0 ${animClass} ${accentStroke} ${className}`}
      style={{ animationDuration: state === "idle" ? "3.2s" : undefined }}
    >
      <svg width={px} height={px} viewBox="0 0 48 48" fill="none">
        {/* Soft buoy halo */}
        <circle cx="24" cy="24" r="21" className="fill-soft stroke-line" strokeWidth="1.5" />
        {/* Alert ring */}
        {state === "alert" && (
          <circle cx="24" cy="24" r="22.5" stroke="currentColor" strokeWidth="2" strokeDasharray="4 3" />
        )}
        {/* Base floating wave/stone from Logo.tsx */}
        <ellipse cx="24" cy="36" rx="12" ry="3.5" fill="currentColor" opacity="0.28" />
        {/* Buoy body (middle layered stone) */}
        <ellipse cx="24" cy="25" rx="12" ry="9" fill="currentColor" opacity="0.92" />
        {/* Top cap (3rd stone) */}
        <ellipse cx="24" cy="14.5" rx="6" ry="2.6" fill="currentColor" />
        {/* Face expression */}
        {state === "thinking" ? (
          <>
            <circle cx="19.5" cy="24.5" r="1.4" className="fill-bg" />
            <circle cx="24" cy="24.5" r="1.4" className="fill-bg" />
            <circle cx="28.5" cy="24.5" r="1.4" className="fill-bg" />
          </>
        ) : state === "alert" ? (
          <>
            <circle cx="19.5" cy="23.5" r="1.5" className="fill-bg" />
            <circle cx="28.5" cy="23.5" r="1.5" className="fill-bg" />
            <path d="M21 28.5 L24 26 L27 28.5" className="stroke-bg" strokeWidth="1.8" strokeLinecap="round" />
          </>
        ) : (
          <>
            <circle cx="19.5" cy="23.5" r="1.5" className="fill-bg" />
            <circle cx="28.5" cy="23.5" r="1.5" className="fill-bg" />
            <path
              d={state === "happy" ? "M19.5 26.8 Q24 30.8 28.5 26.8" : "M20.5 27.2 Q24 29.4 27.5 27.2"}
              className="stroke-bg"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </>
        )}
      </svg>
    </span>
  );
}
