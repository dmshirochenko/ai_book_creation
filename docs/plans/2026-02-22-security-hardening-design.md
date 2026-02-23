# Security Hardening Design — Credits System

**Goal:** Fix all 21 security vulnerabilities identified in the credits deduction and usage logging system.

**Scope:** Backend (FastAPI), Frontend (Edge Functions), Database (Supabase/Postgres)

---

## Tier 1: Schema & Data Integrity

### C2 — Stripe Webhook Idempotency
- Add UNIQUE constraint on `user_credits.stripe_session_id`
- Webhook INSERT fails on duplicate; return 200 to Stripe (graceful dedup)
- Verify `amount_total` matches `metadata.credits * 100` before granting

### H1 — FOR UPDATE on Usage Log in confirm/release
- Add `with_for_update()` when selecting usage log in `confirm()` and `release()`

### H4 — Amount and Page Count Validation
- `books.py`: validate `page_count >= 1` before cost calculation (return 400 if zero)
- `stories.py`: validate `story_cost > 0` before proceeding
- DB CHECK constraints already cover remaining_amount >= 0

### H2 — release() Re-reads from DB
- Verify `release()` reads `credits_used` from the CreditUsageLog row, not metadata
- Fix if it uses metadata-sourced values

### L1 / I3 — Decimal Consistency
- Use `float(round(value, 2))` in API responses to prevent floating-point drift
- Keep `Decimal` internally through service layer

### M1 — Cap Usage Limit
- Clamp `limit` to `max(1, min(limit, 100))` in `/usage` endpoint

---

## Tier 2: Authorization & Access Control

### M5 — User Ownership Check in confirm/release
- Add `user_id` parameter to `confirm()` and `release()`
- Filter query by both `id` AND `user_id`
- Raise error if no matching row found

### H3 — RLS Policies
- `user_credits`: Enable RLS, add SELECT policy for `user_id = auth.uid()`, no INSERT/UPDATE/DELETE for regular users
- `credit_usage_logs`: Add explicit deny for INSERT/UPDATE/DELETE from non-service roles

### C1 — Shared Secret (Edge Function ↔ Backend)
- Add `API_SHARED_SECRET` env var
- Edge functions send it as `X-Api-Key` header
- Backend middleware validates on every request; 403 if missing/invalid

### M2 — Strip Metadata from Usage Response
- Exclude `extra_metadata` from usage endpoint response
- Return only: id, job_id, job_type, credits_used, status, description, created_at

### M3 — Sanitize Error Messages
- Change 402 to generic "Insufficient credits" (no amounts)
- Frontend shows specific numbers from its own balance data

---

## Tier 3: Operational Hardening

### M4 — Rate Limiting
- Add `slowapi` rate limiter middleware
- Story creation: 5/min per user
- Book generation: 3/min per user
- Checkout: 5/min per user
- Balance/usage: 30/min per user

### M7 — CORS Verification
- Verify CORS restricts to talehop.com origins; remove wildcards if present

### M6 — Stale Reservation TTL
- Reduce TTL from 30 to 15 minutes
- Reduce cleanup interval from 10 to 5 minutes

### L3 — Signup Bonus Farming
- Add partial UNIQUE index on `(user_id, source)` WHERE `source = 'signup_bonus'`

### L5 — Log Credit Release Failures
- Add `logger.error()` with full context on release failure

### I1 — Pricing Audit Trail
- Add `updated_at` column to `credit_pricing` table

### I2 — Sanitize Metadata
- Validate metadata keys against allowlist before storing

### Deferred (No Change Needed)
- L2: Pricing endpoint stays public (intentional)
- L4: job_type already validated by DB CHECK constraint
