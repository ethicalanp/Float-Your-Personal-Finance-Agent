"use client";

import { useEffect, useState, type ReactNode } from "react";

interface WarpedFloatBackgroundProps {
  children: ReactNode;
}

/**
 * Layered Depth Visual for Auth Pages:
 * - Back layer: giant decorative warped "FLOAT" serif text via inline SVG per-letter transforms (concave/pincushion).
 * - Mid layer: soft gradient shapes with subtle pointer parallax on desktop (disabled on touch & prefers-reduced-motion).
 * - Front layer: high-contrast WCAG AA card container on solid/high-opacity surface.
 * - Decorative elements have aria-hidden="true" and pointer-events-none.
 */
export function WarpedFloatBackground({ children }: WarpedFloatBackgroundProps) {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [canParallax, setCanParallax] = useState(false);

  useEffect(() => {
    // Only enable parallax on desktop fine-pointer devices and when reduced-motion is not requested
    const finePointer = window.matchMedia("(pointer: fine)").matches;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setCanParallax(finePointer && !reducedMotion);

    if (!finePointer || reducedMotion) return;

    function handleMouseMove(e: MouseEvent) {
      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;
      // Gentle parallax clamp: -10px to +10px
      const deltaX = ((e.clientX - centerX) / centerX) * 10;
      const deltaY = ((e.clientY - centerY) / centerY) * 10;
      setOffset({ x: deltaX, y: deltaY });
    }

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-bg text-ink flex flex-col justify-center items-center py-12 px-4 sm:px-6 lg:px-8">
      {/* ==================================================================== */}
      {/* BACK LAYER: Giant Warped FLOAT SVG (Concave/Pincushion Transformation) */}
      {/* ==================================================================== */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 flex items-center justify-center select-none overflow-hidden opacity-[0.05] dark:opacity-[0.08]"
        style={{
          transform: canParallax
            ? `translate3d(${offset.x * 0.4}px, ${offset.y * 0.4}px, 0)`
            : undefined,
          transition: "transform 150ms ease-out",
        }}
      >
        <svg
          viewBox="0 0 1400 450"
          className="w-full max-w-[150vw] sm:max-w-[125vw] h-auto text-ink fill-current"
          preserveAspectRatio="xMidYMid meet"
          role="presentation"
        >
          <defs>
            <style>{`
              .warped-letter {
                font-family: var(--cnl-serif), "Instrument Serif", Georgia, serif;
                font-size: 340px;
                font-weight: 400;
                text-anchor: middle;
                dominant-baseline: central;
              }
            `}</style>
          </defs>

          {/* Letter F: Outer tall & flared outward (skew & scale up) */}
          <g transform="translate(140, 225) scale(1.18, 1.45) skewY(-5) translate(-140, -225)">
            <text x="140" y="225" className="warped-letter">
              F
            </text>
          </g>

          {/* Letter L: Middle pinched inward */}
          <g transform="translate(420, 225) scale(1.02, 0.98) translate(0, 10) translate(-420, -225)">
            <text x="420" y="225" className="warped-letter">
              L
            </text>
          </g>

          {/* Letter O: Center most pinched toward the focal axis */}
          <g transform="translate(700, 225) scale(0.92, 0.85) translate(0, 25) translate(-700, -225)">
            <text x="700" y="225" className="warped-letter">
              O
            </text>
          </g>

          {/* Letter A: Middle pinched inward */}
          <g transform="translate(980, 225) scale(1.02, 0.98) translate(0, 10) translate(-980, -225)">
            <text x="980" y="225" className="warped-letter">
              A
            </text>
          </g>

          {/* Letter T: Outer tall & flared outward (skew & scale up) */}
          <g transform="translate(1260, 225) scale(1.18, 1.45) skewY(5) translate(-1260, -225)">
            <text x="1260" y="225" className="warped-letter">
              T
            </text>
          </g>
        </svg>
      </div>

      {/* ==================================================================== */}
      {/* MID LAYER: Soft Gradient Shapes (Parallax & Depth)                   */}
      {/* ==================================================================== */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 overflow-hidden"
        style={{
          transform: canParallax
            ? `translate3d(${offset.x * 0.8}px, ${offset.y * 0.8}px, 0)`
            : undefined,
          transition: "transform 150ms ease-out",
        }}
      >
        {/* Warm accent gradient aura (subtle, non-distracting) */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[350px] rounded-full bg-gradient-to-tr from-accent/15 via-agent/10 to-transparent blur-2xl md:blur-3xl opacity-40 dark:opacity-20" />
        <div className="absolute bottom-1/4 left-1/3 w-[400px] h-[300px] rounded-full bg-gradient-to-br from-agent/10 to-transparent blur-2xl md:blur-3xl opacity-30 dark:opacity-15" />
      </div>

      {/* ==================================================================== */}
      {/* FRONT LAYER: Foreground Content (Solid / High-Opacity Surface)        */}
      {/* ==================================================================== */}
      <div className="relative z-10 w-full max-w-md">
        {children}
      </div>
    </div>
  );
}

export default WarpedFloatBackground;
