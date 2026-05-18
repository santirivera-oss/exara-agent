---
name: web-frontend
description: Modern HTML/CSS/Tailwind, accessibility, responsive, performance
triggers:
  files_present: ["package.json", "index.html"]
  dependencies: ["react", "vue", "svelte", "next", "nuxt", "tailwindcss", "@types/react"]
  keywords: ["html", "css", "tailwind", "responsive", "accessibility", "frontend", "ui", "ux", "diseño web"]
---

## HTML
- Semantic over divs: `<header>`, `<nav>`, `<main>`, `<article>`, `<aside>`, `<footer>`, `<section>`.
- Headings hierarchical (one `<h1>` per page, no jumping h2→h4).
- Forms: `<label for=>` always paired with the input. `name=` attributes required.
- Images: `alt` attribute always (`alt=""` for purely decorative).
- Links go to URLs (`<a href>`); buttons trigger actions (`<button>`). Don't swap them.

## CSS / Tailwind
- **Mobile-first**: write the base styles for narrow viewports, scale up with `sm:`, `md:`, `lg:`.
- **Spacing system**: stick to multiples of 4 (Tailwind defaults). Custom values are smells.
- **Color tokens**: define a palette (primary/accent/neutral) and reuse. Avoid hex literals scattered everywhere.
- **Avoid `!important`** — fix specificity, don't paper over it.
- **`gap`** for flex/grid spacing over margin tricks.
- Don't fight the cascade: prefer one source of truth per component (CSS module / styled / Tailwind class).

## Tailwind specifics
- Order utilities consistently (layout → spacing → typography → colors → effects).
  Use `prettier-plugin-tailwindcss` to enforce.
- `cn()` helper for conditional classes (combine `clsx` + `tailwind-merge`).
- Component-level abstractions only when reused 3+ times. Don't pre-abstract every button.
- `@apply` sparingly — for component primitives that span many files.

## Accessibility (a11y) — non-negotiable
- Keyboard: every interaction must work without a mouse. Tab order must make sense.
- Focus visible: don't `outline: none` without a clear replacement.
- Contrast: 4.5:1 for body text, 3:1 for large text (WCAG AA minimum).
- ARIA: native HTML > ARIA. Add `aria-*` only when there's no semantic alternative.
- Live regions (`aria-live="polite"`) for dynamic updates that aren't focus-grabbing.
- Don't disable zoom (`user-scalable=no` is hostile).

## Responsive
- Test at: 360px (small phone), 768px (tablet), 1280px (desktop), 1920px (wide).
- Layouts shift, don't just shrink. Sidebar → top nav on mobile.
- Touch targets ≥ 44×44px (iOS guideline) for tap UI.
- Avoid fixed `vh` on mobile — keyboards shrink the viewport and break layouts. Use `dvh` (dynamic).

## Performance
- Lazy-load images below the fold: `<img loading="lazy">`.
- Use `<img>` with explicit `width` and `height` to avoid CLS (layout shift).
- `srcset` / `<picture>` for responsive images, not just CSS scaling.
- Defer non-critical JS: `<script defer>` or `<script type="module">`.
- Avoid layout-thrashing CSS in animation (transition `transform`/`opacity`, not `width`/`height`/`top`).
- For SPAs: split routes, lazy-load heavy components, prefetch on hover.

## Common anti-patterns
- `<div onClick={...}>` instead of `<button>` — breaks keyboard + screen readers.
- Placeholder as the only label — disappears on focus.
- Disabled buttons without explaining why they're disabled.
- Custom dropdowns without arrow-key navigation.
- Animations that ignore `prefers-reduced-motion`.
- Font sizes < 14px on mobile.
- Pop-ups / modals without an escape hatch (Esc key + clickaway).
