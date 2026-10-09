# Next.js App Router (test fixture)

A tiny shop written for Stack to the Future's Next.js adapter tests. Not meant to run.

- `app/page.tsx` → `/`
- `app/(shop)/products/page.tsx` → `/products` (the `(shop)` route group is not part of the URL)
- `app/(shop)/products/[id]/page.tsx` → `/products/[id]`
- `app/api/orders/route.ts` → `GET` and `POST /api/orders`
- `app/actions.ts` → server actions `placeOrder`, `cancelOrder`
- `app/layout.tsx` → wiring
- `app/_drafts/page.tsx` → private folder, not a route
