---
name: typescript-react
description: TypeScript + React conventions (hooks, components, state)
triggers:
  dependencies: ["react", "typescript", "@types/react"]
  keywords: ["react", "tsx", "jsx", "hook", "component"]
---

## TypeScript
- Strict mode always: `"strict": true, "noUncheckedIndexedAccess": true`.
- Prefer `type` for unions/aliases, `interface` for object shapes that may extend.
- `unknown` over `any`. If you reach for `any`, you're probably skipping work.
- `as const` for literal types: `const ROLES = ['admin', 'user'] as const`.
- Discriminated unions for state machines:
  ```ts
  type Result = { kind: 'ok'; data: T } | { kind: 'err'; error: string }
  ```

## Components
- Functional only — no class components.
- Type props with `interface Props { ... }`, not React.FC (deprecated pattern).
- Default exports for pages, named exports for components.
- Keep components under ~150 lines; split before that.

## Hooks
- Custom hooks start with `use`. Always.
- Dependencies array is exhaustive — let ESLint enforce it (`react-hooks/exhaustive-deps`).
- `useEffect` only for side effects. Derived state goes in render or `useMemo`.
- `useState(() => expensive())` for lazy init.
- `useCallback`/`useMemo` only when there's a measurable benefit (child re-render, expensive calc).
- Avoid `useEffect` for fetching when a framework (Next.js, TanStack Query) provides better tools.

## State
- Local first. Lift up only when needed.
- `useReducer` for state with >2 interrelated fields.
- Context for cross-cutting concerns (auth, theme), not generic state — it forces re-renders.
- For server state, use TanStack Query / SWR, not raw useEffect.

## Anti-patterns
- `useEffect` calling `setState` based on props → derive instead.
- `useState` with an object instead of multiple primitive states (more re-renders).
- Indices as `key` in lists — use a stable id.
- Inline functions/objects in `useMemo`/`useCallback` deps.
- Reading state inside `setState(value)` — use `setState(prev => ...)`.
