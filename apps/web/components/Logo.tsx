import * as React from "react";

/**
 * LOGO PLACEHOLDER:
 * Renders a clearly marked, fixed-size container with the "Float" wordmark.
 * User can drop in a custom SVG or logo design anytime.
 */
export function Logo({
  className = "",
  size = "md",
}: {
  className?: string;
  size?: "sm" | "md" | "lg";
}) {
  const dimensions = {
    sm: "h-7 w-24",
    md: "h-8 w-28",
    lg: "h-10 w-36",
  }[size];

  return (
    <div
      data-testid="logo-placeholder"
      aria-label="Float Home"
      className={`relative inline-flex items-center gap-2 select-none ${dimensions} ${className}`}
    >
      {/* Mark Icon: 3 layered balance stones/waves */}
      <svg
        width="24"
        height="24"
        viewBox="0 0 32 32"
        fill="currentColor"
        aria-hidden="true"
        className="flex-shrink-0 text-current transition-transform duration-300 hover:scale-105"
      >
        <ellipse cx="16" cy="24" rx="11" ry="3.8" opacity="0.9" />
        <ellipse cx="15.5" cy="16" rx="8" ry="3.2" opacity="0.95" />
        <ellipse cx="16.5" cy="9" rx="5" ry="2.4" />
      </svg>
      {/* Wordmark */}
      <span className="font-serif text-xl font-bold tracking-tight text-current">
        Float
      </span>
    </div>
  );
}
