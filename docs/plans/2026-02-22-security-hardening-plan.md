# Security Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all 21 security vulnerabilities in the credits system across backend, edge functions, and database.

**Architecture:** Three tiers of fixes applied incrementally: (1) schema & data integrity constraints via Alembic migration + service layer changes, (2) authorization hardening via shared secret middleware + ownership checks + RLS policies, (3) operational hardening via rate limiting + CORS + cleanup tuning.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, Supabase Edge Functions (Deno/TypeScript), PostgreSQL, slowapi

---

### Task 1: Add UNIQUE constraint on stripe_session_id (C2 — Idempotency)

**Files:**
- Create: `alembic/versions/c3d4e5f6g7h8_security_hardening.py`
- Modify: `src/db/models.py:267-290` (UserCredits `__table_args__`)

**Step 1: Create Alembic migration**

Create file `alembic/versions/c3d4e5f6g7h8_security_hardening.py`:

```python
"""security hardening: constraints, indexes, RLS

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f7a8
Create Date: 2026-02-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3d4e5f6g7h8"
down_revision: Union[str, None] = "b2c3d4e5f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # C2: Idempotent Stripe webhook — prevent duplicate credit grants
    op.execute("""
        CREATE UNIQUE INDEX idx_user_credits_stripe_session_id
        ON user_credits (stripe_session_id)
        WHERE stripe_session_id IS NOT NULL;
    """)

    # L3: Prevent duplicate signup bonuses per user
    op.execute("""
        CREATE UNIQUE INDEX idx_user_credits_signup_bonus_per_user
        ON user_credits (user_id)
        WHERE source = 'signup_bonus';
    """)

    # H3: RLS policies on user_credits
    op.execute("ALTER TABLE user_credits ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY "Users can view own credits"
            ON user_credits FOR SELECT TO authenticated
            USING (auth.uid() = user_id);
    """)

    # H3: Restrict writes on credit_usage_logs to service_role only
    op.execute("""
        CREATE POLICY "Service role can manage usage logs"
            ON credit_usage_logs FOR ALL TO service_role
            USING (true) WITH CHECK (true);
    """)

    # I1: updated_at already exists on credit_pricing (added in initial migration)
    # Just verify the trigger exists (it does from a1b2c3d4e5f7)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS \"Service role can manage usage logs\" ON credit_usage_logs;")
    op.execute("DROP POLICY IF EXISTS \"Users can view own credits\" ON user_credits;")
    op.execute("ALTER TABLE user_credits DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP INDEX IF EXISTS idx_user_credits_signup_bonus_per_user;")
    op.execute("DROP INDEX IF EXISTS idx_user_credits_stripe_session_id;")
```

**Step 2: Update SQLAlchemy model to reflect the unique index**

In `src/db/models.py`, add to `UserCredits.__table_args__`:

```python
    __table_args__ = (
        CheckConstraint(
            "remaining_amount >= 0",
            name="ck_user_credits_remaining_non_negative",
        ),
        CheckConstraint(
            "remaining_amount <= original_amount",
            name="ck_user_credits_remaining_lte_original",
        ),
        Index("idx_user_credits_user_id", "user_id"),
        Index("idx_user_credits_stripe_session_id", "stripe_session_id", unique=True, postgresql_where="stripe_session_id IS NOT NULL"),
    )
```

**Step 3: Run tests**

Run: `cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && .venv/bin/python -m pytest tests/ -v`
Expected: All 290 tests pass

**Step 4: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation
git add alembic/versions/c3d4e5f6g7h8_security_hardening.py src/db/models.py
git commit -m "fix(security): add UNIQUE constraint on stripe_session_id, RLS policies, signup bonus guard"
```

---

### Task 2: Fix Stripe webhook — idempotency + amount verification (C2)

**Files:**
- Modify: `page-play-ai/supabase/functions/stripe-webhook/index.ts`

**Step 1: Update the webhook handler**

In `stripe-webhook/index.ts`, replace the section after `const credits = ...` through the INSERT with:

```typescript
      // Verify that the amount paid matches the credits claimed in metadata
      const amountTotal = session.amount_total; // in cents
      const expectedAmount = credits * 100; // $1 per credit, in cents
      if (!amountTotal || amountTotal < expectedAmount) {
        console.error(
          `Amount mismatch: paid ${amountTotal} cents but metadata claims ${credits} credits (expected ${expectedAmount} cents)`
        );
        return new Response("Amount mismatch", { status: 400 });
      }

      const supabase = createClient(
        Deno.env.get("SUPABASE_URL")!,
        Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
      );

      // Insert a new credit batch — UNIQUE index on stripe_session_id
      // makes this idempotent: duplicate webhooks will fail gracefully
      const { error: insertError } = await supabase
        .from("user_credits")
        .insert({
          user_id: userId,
          original_amount: credits,
          remaining_amount: credits,
          source: "purchase",
          stripe_session_id: session.id,
        });

      if (insertError) {
        // Check if this is a duplicate (unique constraint violation)
        if (insertError.code === "23505") {
          console.log(`Duplicate webhook for session ${session.id}, ignoring`);
          return new Response(JSON.stringify({ received: true }), {
            headers: { "Content-Type": "application/json" },
          });
        }
        console.error("Failed to insert credit batch:", insertError);
        return new Response("Failed to add credits", { status: 500 });
      }
```

**Step 2: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/page-play-ai
git add supabase/functions/stripe-webhook/index.ts
git commit -m "fix(security): add idempotency + amount verification to Stripe webhook"
```

---

### Task 3: Add FOR UPDATE to confirm/release + user ownership check (H1, M5)

**Files:**
- Modify: `src/services/credit_service.py:88-120` (confirm and release methods)
- Modify: `tests/unit/test_credit_service.py`

**Step 1: Update confirm() method**

In `credit_service.py`, replace the `confirm` method:

```python
    async def confirm(self, usage_log_id: Optional[uuid.UUID], user_id: Optional[uuid.UUID] = None) -> None:
        if usage_log_id is None:
            return
        query = select(CreditUsageLog).where(CreditUsageLog.id == usage_log_id).with_for_update()
        if user_id is not None:
            query = query.where(CreditUsageLog.user_id == user_id)
        result = await self._session.execute(query)
        log = result.scalar_one_or_none()
        if not log or log.status != "reserved":
            return
        log.status = "confirmed"
        await self._session.commit()
        logger.info(f"Confirmed credit usage {usage_log_id}")
```

**Step 2: Update release() method**

In `credit_service.py`, replace the `release` method:

```python
    async def release(self, usage_log_id: Optional[uuid.UUID], user_id: Optional[uuid.UUID] = None) -> None:
        if usage_log_id is None:
            return
        query = select(CreditUsageLog).where(CreditUsageLog.id == usage_log_id).with_for_update()
        if user_id is not None:
            query = query.where(CreditUsageLog.user_id == user_id)
        result = await self._session.execute(query)
        log = result.scalar_one_or_none()
        if not log or log.status != "reserved":
            return

        batches_consumed = (log.extra_metadata or {}).get("batches_consumed", [])
        for entry in batches_consumed:
            batch_result = await self._session.execute(
                select(UserCredits).where(UserCredits.id == uuid.UUID(entry["batch_id"])).with_for_update()
            )
            batch = batch_result.scalar_one_or_none()
            if batch:
                batch.remaining_amount += Decimal(str(entry["amount"]))

        log.status = "refunded"
        await self._session.commit()
        logger.info(f"Released {log.credits_used} credits for usage {usage_log_id}")
```

**Step 3: Update callers to pass user_id**

In `src/tasks/story_tasks.py`, update all `credit_service.confirm(usage_log_id)` calls to `credit_service.confirm(usage_log_id, user_id)` and all `credit_service.release(usage_log_id)` calls to `credit_service.release(usage_log_id, user_id)`. There are 4 confirm/release call sites in story_tasks.py:

- Line 57: `await credit_service.release(usage_log_id)` → `await credit_service.release(usage_log_id, user_id)`
- Line 97: `await credit_service.release(usage_log_id)` → `await credit_service.release(usage_log_id, user_id)`
- Line 120: `await credit_service.confirm(usage_log_id)` → `await credit_service.confirm(usage_log_id, user_id)`
- Line 136: `await credit_service.release(usage_log_id)` → `await credit_service.release(usage_log_id, user_id)`

In `src/tasks/book_tasks.py`, update the 2 call sites:

- Line 295: `await credit_service.confirm(usage_log_id)` → `await credit_service.confirm(usage_log_id, user_id)`
- Line 315: `await credit_service.release(usage_log_id)` → `await credit_service.release(usage_log_id, user_id)`

**Step 4: Update tests for new signatures**

In `tests/unit/test_credit_service.py`, the existing tests pass `uuid.uuid4()` as the first arg to confirm/release — they will continue to work since `user_id` defaults to `None`. No test changes required for backward compat, but add a new test:

```python
class TestConfirmWithOwnership:
    @pytest.mark.asyncio
    async def test_confirm_with_matching_user(self, service, mock_session):
        user_id = uuid.uuid4()
        mock_log = MagicMock(); mock_log.status = "reserved"; mock_log.user_id = user_id
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_log
        mock_session.execute.return_value = mock_result
        await service.confirm(uuid.uuid4(), user_id=user_id)
        assert mock_log.status == "confirmed"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_confirm_with_wrong_user_is_noop(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        await service.confirm(uuid.uuid4(), user_id=uuid.uuid4())
        mock_session.commit.assert_not_called()
```

**Step 5: Run tests**

Run: `cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && .venv/bin/python -m pytest tests/ -v`
Expected: All tests pass (290 + 2 new = 292)

**Step 6: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation
git add src/services/credit_service.py src/tasks/story_tasks.py src/tasks/book_tasks.py tests/unit/test_credit_service.py
git commit -m "fix(security): add FOR UPDATE + user ownership to confirm/release"
```

---

### Task 4: Page count validation + sanitize error messages (H4, M3)

**Files:**
- Modify: `src/api/routes/books.py:55-85` (page count validation)
- Modify: `src/api/routes/stories.py:67-85` (story cost validation)
- Modify: `src/api/routes/stories.py:85-100` and `src/api/routes/books.py:80-98` (error message sanitization)

**Step 1: Add page count validation in books.py**

After the `page_count` calculation block (around line 68), add:

```python
    if page_count < 1:
        raise HTTPException(status_code=400, detail="Book must have at least one page")
```

**Step 2: Sanitize 402 error messages**

In `src/api/routes/stories.py`, change the InsufficientCreditsError handler from:

```python
        raise HTTPException(
            status_code=402,
            detail={
                "message": f"Insufficient credits: have {float(e.balance)}, need {float(e.required)}",
                "balance": float(e.balance),
                "required": float(e.required),
            },
        )
```

to:

```python
        raise HTTPException(
            status_code=402,
            detail={
                "message": "Insufficient credits",
                "required": float(e.required),
            },
        )
```

Make the same change in `src/api/routes/books.py`.

**Step 3: Run tests**

Run: `cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && .venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation
git add src/api/routes/books.py src/api/routes/stories.py
git commit -m "fix(security): add page count validation, sanitize 402 error messages"
```

---

### Task 5: Cap usage limit + strip metadata from response + decimal rounding (M1, M2, L1/I3)

**Files:**
- Modify: `src/api/routes/credits.py:63-85` (usage endpoint)
- Modify: `src/api/routes/credits.py:48-55` (balance endpoint)
- Modify: `src/api/schemas.py` (CreditUsageItem)

**Step 1: Cap the limit parameter**

In `src/api/routes/credits.py`, in the `get_usage` function, change:

```python
    limit: int = 50,
```

to:

```python
    limit: int = 50,
```

And at the start of the function body, add:

```python
    limit = max(1, min(limit, 100))
```

**Step 2: Strip metadata from usage response**

In `src/api/routes/credits.py`, in the usage item construction, remove the `metadata` field:

```python
            CreditUsageItem(
                id=str(log.id),
                job_id=str(log.job_id),
                job_type=log.job_type,
                credits_used=float(round(log.credits_used, 2)),
                status=log.status,
                description=log.description,
                created_at=log.created_at.isoformat(),
            )
```

**Step 3: Update CreditUsageItem schema**

In `src/api/schemas.py`, remove the `metadata` field from `CreditUsageItem`:

```python
class CreditUsageItem(BaseModel):
    """A single credit usage log entry."""
    id: str
    job_id: str
    job_type: str
    credits_used: float
    status: str
    description: Optional[str] = None
    created_at: str
```

**Step 4: Round balance**

In `src/api/routes/credits.py`, in `get_balance`, change:

```python
    return CreditBalanceResponse(balance=float(balance))
```

to:

```python
    return CreditBalanceResponse(balance=float(round(balance, 2)))
```

**Step 5: Round pricing costs**

In `src/api/routes/credits.py`, in `get_pricing`, change:

```python
                credit_cost=float(r.credit_cost),
```

to:

```python
                credit_cost=float(round(r.credit_cost, 2)),
```

**Step 6: Run tests**

Run: `cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && .venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 7: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation
git add src/api/routes/credits.py src/api/schemas.py
git commit -m "fix(security): cap usage limit, strip metadata, round decimals"
```

---

### Task 6: Shared secret middleware for backend auth (C1)

**Files:**
- Create: `src/api/middleware.py`
- Modify: `src/api/app.py` (add middleware)
- Create: `tests/unit/test_api_key_middleware.py`

**Step 1: Write the failing test**

Create `tests/unit/test_api_key_middleware.py`:

```python
"""Tests for API key validation middleware."""

import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.middleware import ApiKeyMiddleware


def _make_app(secret: str | None) -> FastAPI:
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.add_middleware(ApiKeyMiddleware, api_key=secret, exempt_paths={"/health", "/"})
    return app


class TestApiKeyMiddleware:
    def test_rejects_missing_key(self):
        app = _make_app("my-secret")
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid or missing API key"

    def test_rejects_wrong_key(self):
        app = _make_app("my-secret")
        client = TestClient(app)
        response = client.get("/test", headers={"X-Api-Key": "wrong"})
        assert response.status_code == 403

    def test_accepts_correct_key(self):
        app = _make_app("my-secret")
        client = TestClient(app)
        response = client.get("/test", headers={"X-Api-Key": "my-secret"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_exempt_paths_skip_validation(self):
        app = _make_app("my-secret")
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200

    def test_disabled_when_no_secret(self):
        app = _make_app(None)
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200

    def test_options_requests_pass_through(self):
        app = _make_app("my-secret")
        client = TestClient(app)
        response = client.options("/test")
        assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && .venv/bin/python -m pytest tests/unit/test_api_key_middleware.py -v`
Expected: FAIL (cannot import ApiKeyMiddleware)

**Step 3: Write the middleware**

Create `src/api/middleware.py`:

```python
"""
Custom middleware for API security.
"""

import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """
    Validates X-Api-Key header against a shared secret.

    When api_key is None (not configured), the middleware is disabled
    and all requests pass through — this allows local development
    without the secret.
    """

    def __init__(self, app, api_key: Optional[str] = None, exempt_paths: Optional[set[str]] = None):
        super().__init__(app)
        self._api_key = api_key
        self._exempt_paths = exempt_paths or set()

    async def dispatch(self, request: Request, call_next):
        # Disabled if no secret configured
        if not self._api_key:
            return await call_next(request)

        # Skip validation for CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip validation for exempt paths (health, root)
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        # Validate the key
        provided_key = request.headers.get("X-Api-Key")
        if not provided_key or provided_key != self._api_key:
            logger.warning(f"Rejected request to {request.url.path}: invalid API key")
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && .venv/bin/python -m pytest tests/unit/test_api_key_middleware.py -v`
Expected: All 6 tests PASS

**Step 5: Wire middleware into app.py**

In `src/api/app.py`, add after the existing imports:

```python
from src.api.middleware import ApiKeyMiddleware
```

Then add the middleware BEFORE CORS (so it runs first), right after `app = FastAPI(...)`:

```python
# API key middleware — validates shared secret from edge functions
_api_shared_secret = os.getenv("API_SHARED_SECRET")
app.add_middleware(
    ApiKeyMiddleware,
    api_key=_api_shared_secret,
    exempt_paths={"/", "/api/v1/health"},
)
```

**Step 6: Run all tests**

Run: `cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && .venv/bin/python -m pytest tests/ -v`
Expected: All tests pass (existing tests don't set API key, but middleware is disabled when env var is absent)

**Step 7: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation
git add src/api/middleware.py src/api/app.py tests/unit/test_api_key_middleware.py
git commit -m "feat(security): add X-Api-Key middleware for edge function auth"
```

---

### Task 7: Update edge functions to send X-Api-Key header (C1)

**Files:**
- Modify: `page-play-ai/supabase/functions/story-api/index.ts`
- Modify: `page-play-ai/supabase/functions/book-api/index.ts`
- Modify: `page-play-ai/supabase/functions/credits-backend-api/index.ts`

**Step 1: Update story-api**

In `story-api/index.ts`, after `const userId = claimsData.claims.sub;`, change the fetchOptions headers to include the API key:

```typescript
    const apiSharedSecret = Deno.env.get("API_SHARED_SECRET");
    const fetchOptions: RequestInit = {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": userId,
        ...(apiSharedSecret ? { "X-Api-Key": apiSharedSecret } : {}),
      },
    };
```

**Step 2: Update book-api**

Same change in `book-api/index.ts`. Find the `fetchOptions` block and add the API key:

```typescript
    const apiSharedSecret = Deno.env.get("API_SHARED_SECRET");
    const fetchOptions: RequestInit = {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": userId,
        ...(apiSharedSecret ? { "X-Api-Key": apiSharedSecret } : {}),
      },
    };
```

**Step 3: Update credits-backend-api**

In `credits-backend-api/index.ts`, find the `fetch(targetUrl, ...)` call and add the API key header:

```typescript
    const apiSharedSecret = Deno.env.get("API_SHARED_SECRET");
    const response = await fetch(targetUrl, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": userId,
        ...(apiSharedSecret ? { "X-Api-Key": apiSharedSecret } : {}),
      },
    });
```

**Step 4: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/page-play-ai
git add supabase/functions/story-api/index.ts supabase/functions/book-api/index.ts supabase/functions/credits-backend-api/index.ts
git commit -m "feat(security): send X-Api-Key header from all edge functions"
```

---

### Task 8: Restrict CORS in edge functions (M7)

**Files:**
- Modify: `page-play-ai/supabase/functions/credits-api/index.ts`
- Modify: `page-play-ai/supabase/functions/credits-backend-api/index.ts`
- Modify: `page-play-ai/supabase/functions/story-api/index.ts`
- Modify: `page-play-ai/supabase/functions/book-api/index.ts`

**Step 1: Replace wildcard CORS in all edge functions**

In each edge function, replace:

```typescript
  "Access-Control-Allow-Origin": "*",
```

with a function that checks the origin:

For `credits-api/index.ts` and `credits-backend-api/index.ts`, replace the entire corsHeaders const and serve entry with:

```typescript
const ALLOWED_ORIGINS = [
  "https://talehop.com",
  "https://www.talehop.com",
  "http://localhost:8080",
  "http://localhost:5173",
];

function getCorsHeaders(req: Request) {
  const origin = req.headers.get("Origin") || "";
  const allowedOrigin = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allowedOrigin,
    "Access-Control-Allow-Headers":
      "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  };
}
```

Then replace all usages of `corsHeaders` in that file with `getCorsHeaders(req)`.

Apply the same pattern to `story-api/index.ts` and `book-api/index.ts` (which use `"Access-Control-Allow-Methods": "POST, GET, OPTIONS, PUT, DELETE"`).

**Step 2: Verify backend CORS is already restricted**

The backend `app.py` already has explicit origins — no wildcard. No change needed there.

**Step 3: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/page-play-ai
git add supabase/functions/credits-api/index.ts supabase/functions/credits-backend-api/index.ts supabase/functions/story-api/index.ts supabase/functions/book-api/index.ts
git commit -m "fix(security): replace wildcard CORS with origin allowlist in edge functions"
```

---

### Task 9: Add rate limiting with slowapi (M4)

**Files:**
- Modify: `requirements.txt` (add slowapi)
- Modify: `src/api/app.py` (add rate limiter)
- Modify: `src/api/routes/stories.py` (add rate limit decorator)
- Modify: `src/api/routes/books.py` (add rate limit decorator)
- Modify: `src/api/routes/credits.py` (add rate limit decorator)

**Step 1: Install slowapi**

Add to `requirements.txt`:

```
# Rate limiting
slowapi>=0.1.9
```

Run: `cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && .venv/bin/pip install slowapi`

**Step 2: Set up the limiter in app.py**

Add imports to `src/api/app.py`:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
```

Add after `load_dotenv()`:

```python
# Rate limiter — keyed by X-User-Id header when present, otherwise by IP
def _get_rate_limit_key(request):
    user_id = request.headers.get("X-User-Id")
    if user_id:
        return user_id
    return get_remote_address(request)

limiter = Limiter(key_func=_get_rate_limit_key)
```

After `app = FastAPI(...)`:

```python
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

**Step 3: Add rate limits to routes**

In `src/api/routes/stories.py`, add import at top:

```python
from src.api.app import limiter
```

Add decorator to `create_story`:

```python
@router.post("/create", ...)
@limiter.limit("5/minute")
async def create_story(request_obj: Request, ...):
```

Note: `slowapi` requires a `request: Request` parameter. Rename the existing `request` parameter (which is `StoryCreateRequest`) to avoid conflict. Change it to `request_data: StoryCreateRequest` and add `request_obj: Request` as the first parameter:

```python
from fastapi import Request as FastAPIRequest

@router.post("/create", ...)
@limiter.limit("5/minute")
async def create_story(
    request_obj: FastAPIRequest,
    request: StoryCreateRequest,
    ...
```

Actually, `slowapi` auto-discovers the `Request` object from any parameter named `request`. Since `StoryCreateRequest` is a Pydantic model (not a Starlette Request), this won't conflict. We just need to ensure a `request: Request` is present. The simplest approach is to add it as an additional parameter:

In `stories.py`, add `from starlette.requests import Request` at top, then add `request: Request` as the FIRST parameter of `create_story` (before the existing `request: StoryCreateRequest`). But wait — this creates a naming conflict.

Better approach: rename the body parameter to `body`:

```python
from starlette.requests import Request

@router.post("/create", ...)
@limiter.limit("5/minute")
async def create_story(
    request: Request,
    body: StoryCreateRequest,
    ...
```

Then update all references to `request` inside the function to `body` (e.g., `body.prompt`, `body.age_min`, etc.).

Apply the same pattern to:
- `books.py` `generate_book`: `@limiter.limit("3/minute")`, rename `request` → `body`
- `credits.py` `get_balance`: `@limiter.limit("30/minute")`
- `credits.py` `get_usage`: `@limiter.limit("30/minute")`

For the credits routes, add `request: Request` as first parameter (no conflict since they don't have a body param named `request`).

**Step 4: Run tests**

Run: `cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && .venv/bin/python -m pytest tests/ -v`
Expected: All tests pass (rate limiter is lenient in tests since each test client request is independent)

**Step 5: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation
git add requirements.txt src/api/app.py src/api/routes/stories.py src/api/routes/books.py src/api/routes/credits.py
git commit -m "feat(security): add rate limiting via slowapi"
```

---

### Task 10: Reduce stale reservation TTL + improve release error logging (M6, L5)

**Files:**
- Modify: `src/api/app.py:32-46` (cleanup params)
- Modify: `src/tasks/story_tasks.py` (release error logging)
- Modify: `src/tasks/book_tasks.py` (release error logging)

**Step 1: Reduce TTL and interval**

In `src/api/app.py`, change the cleanup_task line from:

```python
    cleanup_task = asyncio.create_task(_cleanup_stale_reservations())
```

to:

```python
    cleanup_task = asyncio.create_task(_cleanup_stale_reservations(interval_seconds=300, ttl_minutes=15))
```

**Step 2: Improve release error logging in story_tasks.py**

In `src/tasks/story_tasks.py`, at all 3 places where release errors are caught:

```python
                    except Exception as release_err:
                        logger.error(f"[{job_id}] Failed to release credits: {release_err}")
```

Change to:

```python
                    except Exception as release_err:
                        logger.error(
                            f"[{job_id}] Failed to release credits: usage_log={usage_log_id}, user={user_id}, error={release_err}",
                            exc_info=True,
                        )
```

**Step 3: Improve release error logging in book_tasks.py**

The book_tasks.py exception handler at line 304-321 doesn't have a separate try/except around `release()`. The release is inside the `try:` block of the error session. If it fails, it falls through to the outer `except`. Add explicit logging:

Wrap the release call in its own try/except:

```python
                    # Release reserved credits with fresh session
                    if usage_log_id:
                        try:
                            credit_service = CreditService(err_session)
                            await credit_service.release(usage_log_id, user_id)
                            logger.info(f"[{job_id}] Credits released after failure")
                        except Exception as release_err:
                            logger.error(
                                f"[{job_id}] Failed to release credits: usage_log={usage_log_id}, user={user_id}, error={release_err}",
                                exc_info=True,
                            )
```

**Step 4: Run tests**

Run: `cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && .venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation
git add src/api/app.py src/tasks/story_tasks.py src/tasks/book_tasks.py
git commit -m "fix(security): reduce stale TTL to 15min, improve release error logging"
```

---

### Task 11: Validate metadata keys in reserve() (I2)

**Files:**
- Modify: `src/services/credit_service.py:56-85` (reserve method)
- Modify: `tests/unit/test_credit_service.py` (add test)

**Step 1: Add metadata key allowlist**

In `credit_service.py`, add at the top of the class:

```python
    ALLOWED_METADATA_KEYS = frozenset({
        "prompt", "total_cost", "pricing_snapshot", "batches_consumed",
        "title", "pages", "with_images", "cost_per_page",
    })
```

**Step 2: Filter metadata in reserve()**

In the `reserve` method, before `metadata_with_batches = ...`:

```python
        # Sanitize metadata keys
        safe_metadata = {k: v for k, v in metadata.items() if k in self.ALLOWED_METADATA_KEYS}
        metadata_with_batches = {**safe_metadata, "batches_consumed": batches_consumed}
```

**Step 3: Add test**

In `tests/unit/test_credit_service.py`, add:

```python
class TestMetadataSanitization:
    @pytest.mark.asyncio
    async def test_unknown_metadata_keys_are_stripped(self, service, mock_session):
        batch = MagicMock(); batch.id = uuid.uuid4(); batch.remaining_amount = Decimal("10.00")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [batch]
        mock_session.execute.return_value = mock_result
        mock_session.add = MagicMock()
        async def fake_refresh(obj, **kw):
            obj.id = uuid.uuid4()
        mock_session.refresh = fake_refresh

        await service.reserve(
            user_id=uuid.uuid4(), amount=Decimal("1.00"),
            job_id=uuid.uuid4(), job_type="story", description="test",
            metadata={"total_cost": 1.0, "evil_key": "malicious", "prompt": "hello"},
        )

        # Check that the CreditUsageLog was added with sanitized metadata
        added_obj = mock_session.add.call_args[0][0]
        assert "evil_key" not in added_obj.extra_metadata
        assert "total_cost" in added_obj.extra_metadata
        assert "prompt" in added_obj.extra_metadata
```

**Step 4: Run tests**

Run: `cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && .venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation
git add src/services/credit_service.py tests/unit/test_credit_service.py
git commit -m "fix(security): validate metadata keys against allowlist"
```

---

### Task 12: Strip metadata from credits-api edge function (M2 — edge function side)

**Files:**
- Modify: `page-play-ai/supabase/functions/credits-api/index.ts`

**Step 1: Select only needed columns**

In `credits-api/index.ts`, change the usage query from:

```typescript
    const { data: usage, error: usageError } = await supabase
      .from("credit_usage_logs")
      .select("*")
      .eq("user_id", userId)
      .order("created_at", { ascending: false })
      .limit(20);
```

to:

```typescript
    const { data: usage, error: usageError } = await supabase
      .from("credit_usage_logs")
      .select("id, job_id, job_type, credits_used, status, description, created_at")
      .eq("user_id", userId)
      .order("created_at", { ascending: false })
      .limit(20);
```

**Step 2: Commit**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/page-play-ai
git add supabase/functions/credits-api/index.ts
git commit -m "fix(security): strip metadata from credits-api usage response"
```

---

### Task 13: Apply migration + deploy edge functions + run final verification

**Files:** None (operational steps only)

**Step 1: Apply Alembic migration**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation
.venv/bin/python -m alembic upgrade head
```

Expected: Migration `c3d4e5f6g7h8` applied successfully.

**Step 2: Run full backend test suite**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation
.venv/bin/python -m pytest tests/ -v
```

Expected: All tests pass

**Step 3: Build frontend**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/page-play-ai
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use 22 && npm run build
```

Expected: Build succeeds

**Step 4: Deploy edge functions**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/page-play-ai
npx supabase functions deploy stripe-webhook --project-ref qgzsngmtmswaitiwuejo --no-verify-jwt
npx supabase functions deploy credits-api --project-ref qgzsngmtmswaitiwuejo
npx supabase functions deploy credits-backend-api --project-ref qgzsngmtmswaitiwuejo
npx supabase functions deploy story-api --project-ref qgzsngmtmswaitiwuejo
npx supabase functions deploy book-api --project-ref qgzsngmtmswaitiwuejo
```

**Step 5: Set API_SHARED_SECRET in Supabase**

```bash
npx supabase secrets set API_SHARED_SECRET=<generate-a-strong-random-secret> --project-ref qgzsngmtmswaitiwuejo
```

Also set `API_SHARED_SECRET` in the backend environment (wherever the FastAPI server is deployed).

**Step 6: Push both repos**

```bash
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/ai_book_creation && git push
cd /Users/dmshirochenko/Documents/CodingProjects/ai_books_frontend_and_backend/page-play-ai && git push
```

**Step 7: Run Supabase security advisors**

Use Supabase MCP: `mcp__supabase__get_advisors(type="security")`

Expected: No new security issues related to the credit tables
