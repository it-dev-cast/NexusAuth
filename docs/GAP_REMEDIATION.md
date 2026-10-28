# Architecture gap remediation — status matrix

Baseline: NX-ARC-001 (Nexus One Architecture Plan) and the 2026-10-27 audit
(329 logic items probed against `nexus_auth_test`). This file records where
each of the 62 remediation items stands after the 2026-10-27 work, the
evidence, and what is still needed. Status values: **PASS**, **PARTIAL**,
**FAIL**, **NEEDS DECISION** (see "Decisions" — nothing in that list has been
implemented).

## Matrix

| # | Requirement | Status | Evidence / change | Next step |
|---|---|---|---|---|
| 1 | JWT HS256/RS256, allowlist, expiry, iss/aud | PARTIAL | HS256 (default) and RS256 (`JWT_ALGORITHM=RS256`, `scripts/generate_jwt_keys.py`, public keys at `/.well-known/jwks.json`, `kid`, key rotation, HS256→RS256 overlap); each key is only ever used with its own algorithm; `exp` required; HS256 key rotation (#35) | iss/aud → D1 |
| 2 | Residence-proof storage, protected download | NEEDS DECISION | `residence_proof_reference` is a free-text field; no upload; photos served unauthenticated from `/uploads` | D2 |
| 3 | Company-default role inheritance | PASS / NEEDS DECISION | Job role + department defaults from `config_defaults` work (`employee_service._company_defaults`). Defaults never set RBAC roles | RBAC inheritance not recommended → D3 |
| 4 | User account deletion workflow | NEEDS DECISION | No endpoint; only exiting a linked employee deactivates | D4 |
| 5 | Password reset (single-use, expiring tokens) | NEEDS DECISION | Not implemented; no email/SMS delivery channel exists | D5 |
| 6 | Persistent user preferences | NEEDS DECISION | Theme is per-browser `localStorage` by approved design | D6 |
| 7 | Barcode/QR stable identifier + uniqueness | PARTIAL | `assets.barcode_value` exists, not unique (duplicates found in test DB) | Unique index after real-data check → D7 |
| 8 | Circular-dependency detection | PASS | `graph_utils.creates_cycle` for employee manager + department parent; tests in `test_employee_manager_hierarchy.py`, `test_department_crud.py` | — |
| 9 | Native PostgreSQL enums | NEEDS DECISION | Statuses/roles are VARCHAR validated in Python; no enum semantics required by the plan | Prefer CHECK constraints → D7 |
| 10 | DB CHECK constraints | FAIL | No `CHECK` constraints in any table (raw inserts accept `role='superuser'`, negative cost) | Migration after real-data scan → D7 |
| 11 | Company schema ownership / tenancy | PASS | Approved shared `public` schema with `company_id` scoping (`core/tenancy.py`); no schema-per-company | — |
| 12 | FKs, soft-delete, asset/supplier relations preserved | PASS | Unchanged; FKs RESTRICT/SET NULL verified | — |
| 13 | General cycle checks only where meaningful | PASS | Only the two self-referencing relations need it | — |
| 14 | Configurable audit retention + dry run | NEEDS DECISION | Rows kept indefinitely; the immutability trigger blocks DELETE | Period + trigger exception → D8 |
| 15 | Central PII classification | PASS | `ADMIN_ONLY_PII`, `PII_FIELDS`, `SECRET_FIELDS` in `app/core/audit.py`, used by audit masking, API masking and error redaction | — |
| 16 | Log access to sensitive PII (no values) | PASS | `pii_access` audit row when an admin receives unmasked PAN/Aadhaar/bank numbers (ids + field names only) | — |
| 17 | Consistent masking in audit, logs, errors | PARTIAL | Added: employee home address masked in audit (company addresses stay readable); 422 details drop `input` for PII/secret fields; RBAC log masks email; non-admin API masking | `logger.exception` can still carry raw exception text |
| 18 | PII retention / deletion on request | NEEDS DECISION | Exit keeps PII; no erasure path | Legal retention rules → D9 |
| 19 | Audit logs not modifiable via app endpoints | PASS | No write/delete endpoint; DB trigger blocks UPDATE/DELETE | App connects as table owner → D10 |
| 20 | Masking / access / retention / deletion tests | PARTIAL | `test_api_and_privacy_standards.py`, `test_audit_fixes.py` | Retention/deletion tests follow D8/D9 |
| 21 | Deprecation / Sunset headers | NEEDS DECISION | No endpoint is deprecated today | Add when the first one is |
| 22 | next/previous pagination links | PASS | `pagination.paginated()` adds `next`/`previous` (relative, filters kept); existing keys unchanged | — |
| 23 | Filter operators eq/contains/gt/lt/gte/lte/in/range | PASS | `field[op]=value` on companies, employees, suppliers, assets, departments, job roles, manufacturers, asset models (`app/core/list_query.py`); ops limited by column type; PII/secret/encrypted columns excluded; values bound, `contains` escapes wildcards | Applications list: owner opted out for now |
| 24 | Multi-field sorting with allowlist | PASS | `sort=-created_at,name` (≤3 fields, column allowlist, primary-key tie-breaker); `sort_by`/`sort_dir` unchanged | — |
| 25 | Reject unsupported fields/operators | PASS | Unknown query params, fields, operators and bad values → 422 `VALIDATION_ERROR` with per-parameter details on those 8 lists; frontend and CardDesk only send declared params (checked) | — |
| 26 | API version response header | PASS | `X-API-Version: v1` on `/api/v1/*` (`SecurityHeadersMiddleware`) | — |
| 27 | OpenAPI: error codes, roles, schemas, examples | PASS | `app/core/openapi_docs.py`: `ErrorResponse` schema + example on 401/403/404/409/422/429/500; `x-required-roles` + description on 98/98 secured operations (read from the real role dependencies); typed `{data, meta}` / paginated schemas for 11 resources | Typed bodies for non-CRUD routes (reports, auth) still generic |
| 28 | Request decompression / response compression | PASS / NEEDS DECISION | GZip responses ≥1 KB; no client sends compressed bodies | Request decompression only if a client needs it |
| 29 | Preserve envelope and error format | PASS | Framework 404/405 now enveloped (`http_error_handler`); `DataError` → 422 instead of 500 | — |
| 30 | Configuration namespaces | NEEDS DECISION | Flat `Settings`; env var names must stay | Grouping is cosmetic → D11 |
| 31 | Feature flags | NEEDS DECISION | None exist; nothing consumes one | D11 |
| 32 | Config version metadata | NEEDS DECISION | No defined purpose | D11 |
| 33 | No secrets in source control | PARTIAL | Placeholder JWT secret rejected at startup; bootstrap admin password now `BOOTSTRAP_ADMIN_PASSWORD` (no default); `backups/` git-ignored | **Rotate the local `.env` secret**; dev `docker-compose.yml` has `change-me` |
| 34 | Environment-specific configuration | PASS | `ENVIRONMENT` allowlist; production refuses missing PII key or `*` CORS | — |
| 35 | Signing-key rotation without mass logout | PASS | `JWT_PREVIOUS_SECRET_KEYS` (verify-only), `PII_PREVIOUS_ENCRYPTION_KEYS` via `MultiFernet` | — |
| 36 | Secrets access permissions | NEEDS DECISION | Plain `.env` on the host | Depends on deploy platform → D12 |
| 37 | Secrets never in logs/errors/URLs | PARTIAL | Settings errors hide input values; tokens rejected in URLs; access log scans for secrets | Exception text, see #17 |
| 38 | 100 req/min/IP requirement | NEEDS DECISION | Endpoint limits only (login 10/min, register 5/min) | D13 |
| 39 | Suspicious-activity detection | PARTIAL | Refresh-token reuse revokes all sessions; lockout | Scope → D13 |
| 40 | CSRF where cookie-authenticated | PASS | Bearer-header auth only, no auth cookies | — |
| 41 | HTTPS at the correct boundary | PARTIAL | `HSTS_MAX_AGE_SECONDS` (off by default) | TLS proxy + proxy-header trust → D14 |
| 42 | TLS certificate handling | PASS | No outbound TLS clients | — |
| 43 | CORS/CSP/headers/auth/lockout review | PASS | Added `Cache-Control: no-store` on `/api/v1/auth/*`; CSP, nosniff, frame-deny unchanged | — |
| 44 | Rate limiting in the deploy topology | PASS | Login/register counters in PostgreSQL (`rate_limit_counters`), shared by every worker/container; real client address via `TRUSTED_PROXIES` (X-Forwarded-For believed only from those proxies); IPv6 counted per /64; no longer skipped under pytest (`RATE_LIMIT_ENABLED`, refused off in production); falls back to the in-process counter if the database is unreachable | — |
| 45 | Security regression tests | PASS | `test_key_rotation_and_config.py`, `test_audit_fixes.py`, `test_api_and_privacy_standards.py` | — |
| 46 | Dedicated liveness endpoint | PASS | `/health` has no dependencies (stays 200 with DB down); `/readiness` returns 503 | — |
| 47 | Metrics integration | NEEDS DECISION | Only `duration_ms` in logs | Prometheus dependency → D15 |
| 48 | Bounded DB retries with backoff + jitter | PASS | `schema_check.wait_for_database` at startup (`DB_STARTUP_CONNECT_ATTEMPTS`) | Request-time retries deliberately not added |
| 49 | Deadlock retry for safe transactions | NEEDS DECISION | No transaction is both retry-safe and deadlock-prone today | D16 |
| 50 | Rollback and cleanup on failure | PASS | One transaction per request: `AppSession.commit()` only flushes inside requests and `TransactionMiddleware` commits before the response (rolls back on 4xx/5xx/exception); security writes that precede an error (failed login, lockout, access denied, token reuse) use `commit_now` | — |
| 51 | Graceful degradation, honest health | PASS | Readiness reports 503 honestly; `/db-test` now admin-only | — |
| 52 | Startup verification + graceful shutdown | PASS | `wait_for_database` → `verify_schema_ready`; `lifespan` disposes the pool | — |
| 53 | Preserve logging, request ids, health | PASS | Plus: 500s get an access line, inbound ids validated, `meta.trace_id` = request id | — |
| 54 | Offline SQL / dry run | PARTIAL | `--sql` works for migrations that don't inspect the DB; 10 historical ones do | D17 |
| 55 | Prevent concurrent migrations | PASS | `pg_advisory_xact_lock` + `lock_timeout` (`MIGRATION_LOCK_TIMEOUT`) in `alembic/env.py` | — |
| 56 | Migrations robust to deploy workflow | PARTIAL | Downgrade of `c50668c12e48` fails once PII is encrypted; several downgrades drop data | D17 |
| 57 | Migration tests | PASS | `test_migrations.py`: one head, real downgrades, opt-in full cycle (`RUN_MIGRATION_TESTS=1`, green) | — |
| 58 | API contract tests | PASS | `test_transactions_and_list_queries.py` checks every `$ref` resolves, roles on all secured ops, typed list responses, and that the documented error shape matches real errors | — |
| 59 | Performance/load tests | NEEDS DECISION | None | Tool choice → D18 |
| 60 | CSV export on the 12 list views | PARTIAL | 13 list exports exist; client export now neutralises formulas | Exports cover loaded rows only (≤100) |
| 61 | Live search + suggestions on every list | PASS | Audit and Events now have the same search box + suggestions as the other 11 lists (filters still choose what is loaded) | — |
| 62 | Search/filter/sort state after reload | PASS | State saved as you type/choose (debounced) and on page hide, not only on in-app reloads; Audit/Events filters included; read before the page reloads its data; cleared on logout. Verified with real browser refreshes | — |

## Decisions needed (not implemented)

- **D1** RS256 and `iss`/`aud`: needs a key pair, distribution to verifying services, and agreed issuer/audience names.
- **D2** Identity documents: where files live (local disk, object store), encryption at rest, and whether `/uploads` photos must require login (an `<img>` can't send the bearer token).
- **D3** Should company defaults ever set an RBAC role? Recommended no (privilege-escalation path).
- **D4** User deletion: deactivate, anonymise, or hard delete, and what happens to audit rows that reference the user.
- **D5** Password reset needs a delivery channel (email/SMS) or an admin-issued one-time link.
- **D6** Server-side preferences would replace the approved per-browser theme design.
- **D7** DB constraints (CHECK, barcode uniqueness, enums): needs a read-only scan of the real `nexus_auth` data first.
- **D8** Audit retention period, and a controlled exception to the immutability trigger for purges.
- **D9** PII retention/erasure rules (legal obligations, e.g. payroll records).
- **D10** Separate least-privilege DB role for the app (today the app user owns the audit table and could disable its trigger).
- **D11** Settings namespacing, feature flags, config versioning: no consumer exists yet.
- **D12** Secrets store for the deployment platform.
- **D13** Global 100 req/min/IP vs current per-endpoint limits; worker count (a shared store is needed only with more than one process).
- **D14** TLS termination point and which proxy IPs to trust for `X-Forwarded-*`.
- **D15** Metrics: add `prometheus_client` and a `/metrics` endpoint?
- **D16** Deadlock retry: no qualifying transaction identified.
- **D17** Editing historical migrations for offline mode / safe downgrades vs leaving history untouched.
- **D18** Load-test tool (e.g. Locust) and target numbers.

## Gaps found outside the 62 items

Operators can create companies (including `internal` ones); deactivated companies' users can still log in; supplier names, asset tags and company names are unique only case-sensitively; dashboard "active sessions" counts expired sessions; phone numbers are validated only in the browser; masters (manufacturer, model, department) are not enforced on assets/employees; money is serialised as JSON floats; `users` timestamps are timezone-naive; the test suite never cleans up its database; there is no CI.

## Verification

```
# all tests (uses <DATABASE_URL>_test, never the real database)
.venv/Scripts/python.exe -m pytest -q
# include the full migration upgrade/downgrade cycle on a throwaway database
RUN_MIGRATION_TESTS=1 .venv/Scripts/python.exe -m pytest app/tests/test_migrations.py -q
# models and migrated schema agree
.venv/Scripts/python.exe -m alembic check
```

## Deployment and rollback

No database migration was added in this round, so deploy and roll back are code-only.

1. Before deploying, set a new random `JWT_SECRET_KEY` (and `JWT_SECRET`). The app refuses to start with the `.env.example` placeholder. Rotating away from the placeholder signs everyone out once, by design. Don't list the placeholder in `JWT_PREVIOUS_SECRET_KEYS`, because it's rejected there too.
2. A server that runs with `ENVIRONMENT=production` must have `PII_ENCRYPTION_KEY` set and must not use `*` in `CORS_ALLOWED_ORIGINS`.
3. Fresh installs only: set `BOOTSTRAP_ADMIN_PASSWORD`, or create the first admin with `scripts/seed_admin.py`.
4. Rollback means redeploying the previous commit. All new settings are optional, so the old code ignores them.
