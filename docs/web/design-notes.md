# Float Web — Design Notes & Style Reference

This document extracts and analyzes the visual architecture, design tokens, motion choreography, and layout rules from the Cairn design reference to implement the Float landing page in `apps/web`.

---

## 1. Art Direction & Visual Metaphor

- **Art Direction Concept**: "The Window" & "Floating Cards".
- **Visual Identity**: Calm, editorial, high-contrast clarity. Framed landscape vista windows with layered mountain ridgelines in muted morning fog / dawn tones, over which dark and light cards float with crisp shadows.
- **Tone**: Transparent, quiet confidence, financial dignity, honest Indian financial intelligence without aggressive fintech hype, badges, or neon clutter.

---

## 2. Colour Palette & Design Tokens

The reference uses two core palette variations (`fog` as primary, `ember` as warm alternate), with full support for light and dark modes.

### Light Mode (`fog` theme)
| Token Name | Value | Purpose |
| :--- | :--- | :--- |
| `--cnl-bg` / `--bg` | `#f7f7f5` | Page background: warm, matte bone-white/fog |
| `--cnl-ink` / `--ink` | `#111211` | Primary text: deep soft obsidian charcoal |
| `--cnl-mute` / `--mute` | `#5c5f5b` | Secondary text & subheadings |
| `--cnl-faint` / `--faint` | `#878a86` | Metadata, kickers, small captions, borders |
| `--cnl-line` / `--line` | `rgba(17, 18, 17, 0.1)` | Structural border dividers and subtle rules |
| `--cnl-soft` / `--soft` | `#ebebe8` | Pill backings, interactive chips, hover states |
| `--cnl-card` / `--card` | `#ffffff` | Floating card background |
| `--cnl-card-ink` | `#151615` | Foreground text on card surfaces |
| `--cnl-card-mute` | `#686b67` | Secondary text on card surfaces |
| `--cnl-card-line` | `rgba(0, 0, 0, 0.08)` | Inner borders and dividers on cards |
| `--cnl-card-soft` | `#f1f1ef` | Segmented control and badge track backgrounds |
| `--cnl-accent` | `#e4572e` | Ember accent: status pings, alert dots, highlight indicators |
| `--cnl-agent` | `#2a6ee0` | Agent blue: interactive focus rings, active links, safe states |
| `--cnl-success` | `#16a34a` | Green indicator: low risk, safe verdict, verified state |

### Dark Mode (`night` theme)
| Token Name | Value | Purpose |
| :--- | :--- | :--- |
| `--cnl-bg` | `#0c0d0d` | Deep obsidian backdrop |
| `--cnl-ink` | `#efeeea` | Bright off-white primary text |
| `--cnl-mute` | `#a5a7a2` | Soft grey secondary copy |
| `--cnl-faint` | `#7d807b` | Subdued metadata text |
| `--cnl-line` | `rgba(255, 255, 255, 0.1)` | Crisp glass dividers |
| `--cnl-soft` | `#1d1f1e` | Button backgrounds, chips |
| `--cnl-card` | `#151716` | Dark surface container |
| `--cnl-card-ink` | `#f0efeb` | High-contrast card text |
| `--cnl-card-mute` | `#a3a5a0` | Muted card labels |
| `--cnl-card-line` | `rgba(255, 255, 255, 0.08)` | Divider lines inside cards |
| `--cnl-card-soft` | `#202221` | Inset backgrounds |

### Ridgeline Atmospheric Palette (Code-drawn SVG fallback & backgrounds)
```css
--cnl-ridge-1: #c9d3dc; /* Sky dawn highlight */
--cnl-ridge-2: #e7d9cc; /* Horizon warmth */
--cnl-ridge-3: #a9b8b4; /* Distant mountain layer */
--cnl-ridge-4: #86998f; /* Mid-distance ridge */
--cnl-ridge-5: #5f776c; /* Near-distance valley */
--cnl-ridge-6: #3c5148; /* Foreground terrain */
```

---

## 3. Typography Hierarchy

- **Display & Section Headings**: Serif stack (`Instrument Serif`, `Newsreader`, `Palatino`, `Georgia`, or system serif).
  - Characteristics: `font-weight: 400`, letter-spacing `-0.022em` to `-0.03em`, tight line-height `1.02` to `1.08`.
  - Sizes:
    - Hero Title: `clamp(46px, 7.4vw, 78px)`
    - Section Headings (`h2`): `clamp(38px, 5.2vw, 56px)`
    - Modal / Card Headings: `28px` to `34px`
- **Body & UI Font**: Clean geometric neo-grotesque sans stack (`Inter`, `system-ui`, `-apple-system`, `sans-serif`).
  - Text: `15px` to `15.5px`, line-height `1.6` to `1.85`.
  - Card Text: `13px` to `14.5px`.
  - Buttons & Navigation: `13.5px`, `font-weight: 500`.
- **Kickers, Timestamps & Numbers**: Monospace stack (`JetBrains Mono`, `SF Mono`, `monospace`).
  - Font: `500 10.5px/1`, uppercase, letter-spacing `0.1em`.
  - Accents: Preceded by a `7px` circular accent dot with soft glowing pulse ring (`box-shadow: 0 0 0 4px color-mix(...)`).

---

## 4. Spacing Scale, Radii & Shadows

### Spacing Scale
- Page gutters: `24px` desktop, `16px` tablet, `12px` mobile.
- Section spacing: `120px` to `150px` on desktop, `70px` to `96px` on mobile.
- Content max-width: `1240px` (standard container) to `1440px` (wide canvas pin).

### Border Radii
- Pill buttons & badges: `999px` (full capsule).
- Cards & Vistas: `14px` standard, `16px` player/modal, `18px` dialogs.
- Inner elements (inputs, tiles, list items): `8px` to `10px`.
- Micro indicators: `50%` (circular dots).

### Shadows & Elevation
- Floating Cards: `0 40px 90px -30px rgba(0, 0, 0, 0.65), 0 0 0 1px rgba(0, 0, 0, 0.05)`.
- Pill Buttons: `0 1px 0 rgba(255, 255, 255, 0.12) inset, 0 6px 18px -8px rgba(0, 0, 0, 0.45)`.
- Nav Glass: `-webkit-backdrop-filter: blur(14px) saturate(1.3); box-shadow: 0 1px 0 var(--cnl-line)`.

---

## 5. Components & Interaction Patterns

### 1. Header & Navigation
- Sticky header (`top: 0`, `z-index: 40`, height `68px`).
- Transitions smoothly on scroll to translucent frosted glass with border.
- Magnetic sliding hover pill on desktop navigation links.
- Mobile burger button reveals full-screen overlay sheet on `< 860px` screens.
- Actions: "Log in" link and primary "Sign up" capsule pill.

### 2. Pill Button Rolling Motion
- Two-tier roll effect: button text is wrapped in a clipping roll container (`.cnl-roll`) with duplicate label in `::after`.
- On hover, transforms `-100%` vertically with smooth cubic-bezier easing (`cubic-bezier(0.22, 1, 0.36, 1)`).

### 3. Vista Canvas & Mountain Horizon
- Framed landscape window (`.cnl-vista`) with rounded clipping path.
- Deep layered ridgeline SVG or scenic backdrop with subtle parallax depth drift on mouse move.
- Inset gradient vignette (`rgba(8, 12, 18, 0.04)` to `0.3`) ensuring readability of floating UI cards.

### 4. Interactive Accordion (FAQ & Three Pillars)
- CSS Grid 0fr-to-1fr smooth animation (`grid-template-rows: 0fr -> 1fr`).
- Accessible keyboard navigation (`Enter` / `Space` toggling, `aria-expanded`).

### 5. Live Scam Checker Demo Box
- Real-time client component calling `POST /api/v1/protect/check`.
- Input textarea for user messages (English, Malayalam, Manglish) with sample chips for instant testing.
- Comprehensive states:
  - Idle state with prompt guidance.
  - Loading / analyzing state with animated pulsing beacon.
  - Success state rendering: Risk tier badge (SAFE, SUSPICIOUS, DANGEROUS), risk score bar, identified trigger indicators, and honest recovery advice.
  - 503 / Offline error state handling with friendly advisory message.
- Zero client-side retention or sensitive logging.

---

## 6. Mobile & Phone Width Behavior (360px – 768px)

1. **360px viewport**:
   - Zero horizontal overflow (`overflow-x: clip` on root container).
   - Side padding compressed to `12px`.
   - Grid cards stack into single columns (`grid-template-columns: 1fr`).
   - Pill forms collapse from inline row into structured vertical stacks.
   - Text clamped gracefully using CSS `clamp()` (`clamp(42px, 7.4vw, 78px)`).
2. **768px viewport (Tablet)**:
   - 2-column stat grids.
   - Pinned multi-step canvas switches from horizontal split to stacked layout.
   - Mobile navigation hamburger menu with accessible modal sheet.

---

## 7. Motion & Accessibility

- **Prefers Reduced Motion**:
  - Automatically verified via `@media (prefers-reduced-motion: reduce)` and `useReduced()` React hook.
  - Disables continuous pulse, marquee, and infinite rotational animations.
  - Transforms instant without scrub lag or jarring transitions.
- **Focus Rings**:
  - `outline: 2px solid var(--cnl-agent); outline-offset: 3px; border-radius: 8px;`.
- **Contrast**:
  - Strict AA compliance against background tints.
