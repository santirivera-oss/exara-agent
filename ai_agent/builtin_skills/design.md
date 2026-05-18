---
name: design
description: UX + visual design fundamentals — applies to any UI work
triggers:
  always: true
  keywords: ["diseño", "design", "ui", "ux", "layout", "tipografía", "color", "figma", "wireframe"]
---

## Mental model
Design is not decoration. Every choice should serve **understanding** and
**action**. If a user can't tell what's clickable, what's important, or what
will happen next — the design is wrong, no matter how pretty.

## Visual hierarchy
Drive the eye in this order: **size > weight > color > position**.
- One thing per screen has primary focus. Two = no focus.
- Headlines bigger than body. Body bigger than meta. Never the inverse.
- Don't bold everything. If it's all emphasized, nothing is.

## Spacing (the most impactful thing)
- Use a 4 or 8 px grid. Pick one and stay there.
- More breathing room than feels right initially. Cramped UIs feel cheap.
- Group related items by proximity. Separate unrelated by larger gaps.
- White space is content. It directs the eye.

## Typography
- 2 typefaces max per UI. One for display (optional), one for everything else.
- System fonts are perfectly fine and faster: `-apple-system, Segoe UI, Roboto, sans-serif`.
- Line-height: 1.5 for body, 1.1–1.25 for headings.
- Line-length: 60–80 characters for paragraphs (use `max-w-prose` in Tailwind).
- Font sizes step up by 1.2× or 1.25× (modular scale): 12, 14, 16, 20, 24, 32, 40, 56.

## Color
- Start with grayscale. Add ONE accent color for primary actions.
- 60/30/10 rule: 60% neutral, 30% secondary, 10% accent.
- Reserve a "danger" color (red) for destructive only. If everything is red, nothing reads as danger.
- Test in dark mode and grayscale — your UI shouldn't rely on color alone for meaning.
- Contrast: meet WCAG AA at minimum (4.5:1 body, 3:1 large text).

## Layout patterns that work
- **F-pattern** for content pages (eye scans top-left to right, then down-left).
- **Z-pattern** for landing pages with a clear CTA.
- **Card** for repeated similar items (products, articles, profiles).
- **Sidebar + main** for apps; **single column** for marketing.
- Keep the line of action short — don't make users scroll 3 screens to find the button.

## Components
- **Buttons**: 3 variants max (primary, secondary, ghost). Don't invent more.
- **Inputs**: label always visible. Errors inline, in red, descriptive ("Email must include @" > "Invalid").
- **Modals**: only for high-friction confirmations. Don't trap users.
- **Empty states**: never blank. Explain what would be here + offer the next action.
- **Loading**: skeletons > spinners for known shapes. Don't show nothing.

## Microcopy
- Action verbs on buttons: "Save", "Send", "Delete". Not "OK"/"Submit"/"Click here".
- Errors describe what to do, not what's wrong.
- No exclamation marks unless something is genuinely urgent.
- Keep tone consistent across the product.

## Things that signal "amateur"
- Tiny click targets, especially on mobile.
- Walls of text without visual rhythm.
- 8 colors of varying saturation, no system.
- Borders on every element ("box-itis").
- Drop shadows everywhere with no purpose.
- Centered, full-page forms with no visual landmarks.
- Animations that delay every interaction (>200ms is too long).
- Disabled buttons that look identical to enabled.

## When in doubt
- Remove. Most UIs improve from deletion, not addition.
- Look at 3 products you admire that solve the same problem. Steal their structure (not graphics).
- Show a mockup to one person. If they don't know where to click in 3 seconds, redesign.
