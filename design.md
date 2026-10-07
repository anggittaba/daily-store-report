# Design — Daily Store Report Assistant

A locked design system for this app. Every surface (upload page, report view in
the web app, standalone HTML report) reads this file before changing styles.
Extend or amend it when the system needs to grow; do not restyle per page.

Built with the [Hallmark](https://github.com/nutlope/hallmark) rules
(`hallmark redesign`, multi-page flow). Tokens live in
`store_report/templates/tokens.css`; components in `styles.css`.

## Genre
modern-minimal, utilitarian tone. This is an operations tool read at 7 a.m.
by an area manager deciding which store to call. Numbers first, no decoration.

## Macrostructure family
- App pages: **Workbench**. Top bar, control strip, title block, KPI strip,
  then working sections separated by hairlines and one dark band.
  Variation knobs: control strip present (web app) or absent (static report).
- Marketing / content pages: none. The README is the only "marketing".

## Theme (Cobalt, adapted)
- `--color-paper`   oklch(98.5% 0.004 250)
- `--color-paper-2` oklch(96.5% 0.005 252)
- `--color-ink`     oklch(24% 0.02 258)
- `--color-ink-2`   oklch(34% 0.018 257)
- `--color-rule`    oklch(91% 0.008 255)
- `--color-accent`  oklch(55% 0.20 256), with `--color-accent-ink` oklch(99% 0.004 256)
- `--color-focus`   oklch(55% 0.20 256)
- Severity is data, not decoration: critical oklch(56% 0.19 27), high
  oklch(64% 0.16 52), medium oklch(84% 0.13 95) with a 3:1 edge. Severity is
  always shown as a square plus a text label, never colour alone.
- One dark band (graphite oklch(22% 0.016 260)) holds the written summary.

## Typography
- Display: Space Grotesk, weight 700, roman. Tracking −0.025em.
- Body: IBM Plex Sans, weight 400/500. (Cobalt lists Inter; Hallmark's
  typography rules ban Inter, so Plex is the substitute.)
- Mono: JetBrains Mono 400, one role only: the command-line hint on the upload page.
- Type scale anchor: `--text-display` = clamp(2rem, 2.2vw + 1.1rem, 2.85rem).
- Numbers use tabular figures everywhere.

## Spacing
4-point named scale (`--space-3xs` … `--space-3xl`) in `tokens.css`. Use the
named tokens, never raw values. Controls share one 44 px height.

## Motion
- Easing `--ease-out` cubic-bezier(0.16, 1, 0.3, 1); `--dur-micro` 120 ms.
- Only background colour and a 1 px press transform transition. No reveals.
- Reduced motion: transitions drop to 1 ms; the loading spinner stops.

## Microinteractions stance
- Silent success. No toasts. The page changing is the confirmation.
- Errors appear in place under the field, with a reason and a fix.
- Focus rings appear instantly (2 px accent outline).
- Buttons implement default, hover, focus-visible, active, disabled, loading,
  error and success states.

## CTA voice
- Primary: solid accent fill, 6 px radius, verb-first sentence case
  ("Build report", "Download report"). One primary per screen.
- Secondary: paper fill, 1 px control-edge border, same shape ("Flags as CSV").
- Labels never wrap (`white-space: nowrap`).

## Per-page allowances
- App pages MUST NOT use enrichment. No hero art, no gradients, no icons.
- Charts are inline SVG styled by CSS classes that read tokens.

## What pages MUST share
- The wordmark (accent square + "Store Report").
- Accent placement: primary button, wordmark square, the report-date bar. ≤ 5 % of any viewport.
- Display + body fonts, the KPI strip, the severity marker, the footer line.

## What pages MAY differ on
- The web app adds the control strip (file, date, thresholds) and download buttons.
- The static report drops them and has no JavaScript.

## Exports
### tokens.css
The canonical file is `store_report/templates/tokens.css`; copy it as is.
Tailwind, DTCG and shadcn exports were not generated because this project uses
none of them.
