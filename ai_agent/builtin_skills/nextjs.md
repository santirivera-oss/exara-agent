---
name: nextjs
description: Next.js 14+ App Router patterns
triggers:
  dependencies: ["next", "nextjs"]
  keywords: ["next.js", "nextjs", "app router", "server component", "server action"]
---

## App Router defaults
- Use the App Router (`app/`), not the Pages Router (`pages/`).
- Components are **Server Components by default**. Add `"use client"` only when needed
  (hooks, browser APIs, event handlers).
- `layout.tsx` for shared UI, `page.tsx` for routes, `loading.tsx` + `error.tsx` for UX.

## Data fetching
- Server components: just `await fetch(...)` or call your DB directly. No `useEffect`.
- Cache control:
  - `fetch(url, { cache: 'force-cache' })` — default in many setups.
  - `fetch(url, { next: { revalidate: 60 } })` — ISR every 60s.
  - `fetch(url, { cache: 'no-store' })` — always fresh.
- Use Server Actions (form submissions, mutations) over API routes when possible.

## Server vs Client boundary
- Push `"use client"` as far down the tree as possible — keeps bundle small.
- Server Components cannot use hooks or browser APIs.
- Pass data DOWN from server → client, never the other way.
- Async server components are normal; async client components are not allowed.

## Routing
- File-based: `app/blog/[slug]/page.tsx` matches `/blog/foo`.
- Dynamic segments: `[slug]`. Catch-all: `[...slug]`. Optional: `[[...slug]]`.
- `generateStaticParams` for SSG of dynamic routes.
- `searchParams` is a prop on `page.tsx`, async in Next 15+.

## Common pitfalls
- Importing server-only code in a client component → use `import 'server-only'` at top of server modules.
- `Date.now()` / `Math.random()` in server components — they run once at build/request time. Use client components for live data.
- Mutating data without `revalidatePath` / `revalidateTag` → stale UI.
- Heavy 3rd party libs in client components — try server-side first.

## Styling
- Tailwind is the path of least resistance with App Router.
- For component libs, `shadcn/ui` integrates cleanly.
- CSS modules work but global styles must go in `app/globals.css`.

## API routes (when you do need them)
- Live in `app/api/<path>/route.ts`. Export `GET`, `POST`, etc.
- Use `NextResponse.json(...)` for responses.
- Stream long responses with `ReadableStream`.
