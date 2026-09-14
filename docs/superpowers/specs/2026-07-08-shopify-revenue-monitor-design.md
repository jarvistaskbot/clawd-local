# Shopify Revenue Monitor — MVP Design Spec

**Date:** 2026-07-08
**Status:** Design approved, pending implementation planning
**Author:** Arto Mnatsakanyan (design via brainstorm session)

---

## 1. Problem Statement

Shopify stores bleed money silently. A checkout conversion rate can drop 40% due to a theme update, a broken app, or a payment gateway issue — and the store owner has no idea until they check their dashboard hours later. No existing Shopify app detects real customer behavior anomalies and quantifies the revenue impact in merchant-readable terms.

**Core value prop:** "Your store lost ~$3,400 today. Here's what caused it, here's how to fix it."

---

## 2. Target Customer

- **Primary:** Shopify stores doing $500K–$10M GMV/year. DTC brands (apparel, beauty, health).
- **Secondary:** Agencies managing multiple Shopify stores.
- **Buyer persona:** Store owner or founder — they ARE the decision-maker, they own the credit card.
- **Pain point:** Silent revenue bleed from checkout errors, inventory gaps, JS failures.

---

## 3. Competitive Positioning

| Competitor | What they do | Why we win |
|---|---|---|
| Uptime (31 reviews, established) | Synthetic checkout testing (fake purchase every 30 min) | We detect real customer behavior drops, not just hard breaks |
| Revenue Shield / MyStoreGuardian | Automated checkout simulation, binary pass/fail | No revenue attribution; we show estimated $ impact |
| Raygun / CatchJS | JS error tracking | Developer-facing; we're merchant-facing with revenue context |
| Amp / SC Back in Stock | OOS recovery (waitlists after stock-out) | Reactive; we alert the moment a hot product hits zero |
| Shopify Analytics | Conversion funnel reports | No real-time alerting, no error detection |

**Positioning sentence:** "Uptime tells you if your checkout is broken. We tell you if it's quietly costing you money."

**Key insight from competitor review research:** Merchants trust third-party monitoring apps more than Shopify's own status page. Shopify consistently understates outage severity. An app that catches what Shopify misses has built-in credibility.

---

## 4. MVP Scope (v1)

**IN — 4 detection features:**

| Feature | Signal source | What it detects |
|---|---|---|
| Checkout completion rate drop | Webhooks: `checkouts/create`, `orders/create` | Hourly rate drops >40% below 7-day baseline |
| Payment gateway failures | `orders/create` with `financial_status=pending` | Pending order rate doubles above baseline |
| JS errors on cart/product pages | Theme App Extension → `/events` endpoint | New error pattern, ≥10 occurrences in 10 min |
| Out-of-stock hot products | `inventory_levels/update` webhook | Product with ≥5 orders/7 days hits inventory=0 |

**OUT — deferred to v2+:**
- App conflict detection (no reliable signal in v1)
- Multi-store dashboard / agency view
- ML-based predictive alerts (needs 6+ months baseline data)
- Inventory price inconsistencies
- Session recording integration
- A/B test detection, discount abuse, UTM tracking

**"Done" definition:**
A Shopify store installs the app → within 15 minutes sees last 7 days of incidents on a dashboard → gets a Slack message the next time a checkout failure spike happens with an estimated revenue impact.

**Technical corrections baked in:**
1. JS error detection scoped to cart/product pages only (checkout.liquid deprecated for non-Plus stores)
2. OOS detection uses order history as traffic proxy (pageviews not available via API)
3. New installs show "calibrating" state for 7 days before anomaly detection activates

---

## 5. Technical Stack

**Backend:** Python 3.11 + FastAPI
**Admin dashboard:** React + Shopify Polaris components (pre-built UI library)
**Theme App Extension:** Vanilla JS (always required, regardless of backend choice)
**Database:** PostgreSQL (managed, on Railway)
**Hosting:** Railway (~$25/month, FastAPI + PostgreSQL in one platform)
**Email alerts:** SendGrid free tier (100 emails/day)
**Shopify library:** `shopify-python-api` (official, handles OAuth + API calls)

---

## 6. Architecture

```
[Shopify Storefront]
    └─ Theme App Extension (vanilla JS, <5KB)
          ├─ window.onerror / unhandledrejection capture
          └─ POST /events  (batched every 10s, async fire-and-forget)

[Shopify Admin]
    └─ webhooks → POST /webhooks/{topic}  (HMAC-verified)
         topics: checkouts/create, orders/create, orders/cancelled,
                 inventory_levels/update, app/uninstalled,
                 customers/data_request, customers/redact, shop/redact

[FastAPI Backend]
    ├─ /auth              → Shopify OAuth flow
    ├─ /webhooks/{topic}  → store raw to webhooks_raw, return 200 immediately
    ├─ /events            → JS error intake, lightweight write, return 200
    ├─ /api/*             → dashboard REST API (incidents, metrics, config)
    └─ Background workers (asyncio)
          ├─ WebhookProcessor  — polls webhooks_raw every 2s, routes by topic
          ├─ IncidentDetector  — 5-minute heartbeat per shop
          └─ AlertDispatcher   — email (SendGrid) + Slack webhook on incident

[PostgreSQL]
    shops, webhooks_raw, checkouts, orders,
    js_error_events, daily_metrics, incidents, alert_config

[React Admin Dashboard]
    Embedded in Shopify admin via App Bridge (iframe, not external window)
    Polaris components: Card, DataTable, Badge, Banner, SkeletonPage
    Fetches from /api/* using session tokens
```

---

## 7. Data Model

```sql
shops
  id UUID PRIMARY KEY
  shop_domain VARCHAR UNIQUE NOT NULL
  access_token_encrypted TEXT NOT NULL
  plan_tier VARCHAR DEFAULT 'trial'      -- trial/starter/growth/pro/agency
  baseline_ready_at TIMESTAMP            -- NULL = still calibrating
  created_at TIMESTAMP DEFAULT NOW()
  uninstalled_at TIMESTAMP              -- NULL = active

webhooks_raw
  id UUID PRIMARY KEY
  shop_id UUID REFERENCES shops
  topic VARCHAR NOT NULL
  payload_json JSONB NOT NULL
  received_at TIMESTAMP DEFAULT NOW()
  processed_at TIMESTAMP               -- NULL = pending

checkouts
  id UUID PRIMARY KEY
  shop_id UUID REFERENCES shops
  checkout_token VARCHAR NOT NULL
  started_at TIMESTAMP NOT NULL
  completed_at TIMESTAMP               -- NULL = abandoned/in-progress

orders
  id UUID PRIMARY KEY
  shop_id UUID REFERENCES shops
  shopify_order_id BIGINT NOT NULL
  checkout_token VARCHAR               -- links checkout → order
  created_at TIMESTAMP NOT NULL
  financial_status VARCHAR NOT NULL    -- paid/pending/voided/refunded
  total_price NUMERIC(10,2) NOT NULL

js_error_events
  id UUID PRIMARY KEY
  shop_id UUID REFERENCES shops
  error_hash VARCHAR NOT NULL          -- SHA256(message + filename)
  error_message TEXT NOT NULL
  page_url TEXT NOT NULL
  first_seen_at TIMESTAMP NOT NULL
  last_seen_at TIMESTAMP NOT NULL
  count_last_10min INTEGER DEFAULT 0

daily_metrics
  shop_id UUID REFERENCES shops
  date DATE NOT NULL
  checkout_starts INTEGER DEFAULT 0
  checkout_completions INTEGER DEFAULT 0
  completion_rate NUMERIC(5,4)         -- 0.0000 to 1.0000
  payment_pending_count INTEGER DEFAULT 0
  js_error_count INTEGER DEFAULT 0
  avg_order_value NUMERIC(10,2)
  PRIMARY KEY (shop_id, date)

incidents
  id UUID PRIMARY KEY
  shop_id UUID REFERENCES shops
  type VARCHAR NOT NULL                -- checkout_drop/payment_failure/js_error/oos
  severity VARCHAR NOT NULL           -- low/medium/high
  started_at TIMESTAMP NOT NULL
  resolved_at TIMESTAMP               -- NULL = active
  estimated_revenue_loss NUMERIC(10,2)
  details_json JSONB NOT NULL
  alert_sent_at TIMESTAMP             -- NULL = not yet sent

alert_config
  shop_id UUID PRIMARY KEY REFERENCES shops
  email VARCHAR
  slack_webhook_url TEXT
  min_checkouts_for_alert INTEGER DEFAULT 5
  updated_at TIMESTAMP DEFAULT NOW()
```

---

## 8. Detection Logic

### Detection 1: Checkout completion rate drop

```
hourly_rate = completed_checkouts / started_checkouts (last 60 min)
baseline    = avg(same-hour completion rates, last 7 days)

ALERT if ALL:
  - baseline exists (shop.baseline_ready_at IS NOT NULL)
  - started_checkouts in last 60min >= 5   [noise floor]
  - hourly_rate < baseline * 0.60          [>40% drop]

Auto-resolve:
  - rate back above baseline * 0.70 for 30 consecutive minutes
```

### Detection 2: Payment failures

```
Shopify does NOT fire a webhook on payment failure.
Signal: orders/create with financial_status = 'pending'

pending_rate = pending_orders / total_orders (last 60 min)
baseline     = avg(pending_rate, last 7 days)

ALERT if ALL:
  - total_orders in window >= 3
  - pending_rate > baseline * 2.0          [double normal rate]

Auto-resolve:
  - pending_rate returns to <= baseline * 1.2 for 30 minutes
```

### Detection 3: JS errors (cart/product pages only)

```
Per error_hash: count occurrences in last 10 minutes.

ALERT if ALL:
  - error NOT seen in last 24h             [filters known baseline errors]
  - count >= 10 in 10-minute window

Auto-resolve:
  - count drops below 3 for 60 consecutive minutes
```

### Detection 4: Hot product out of stock

```
On inventory_levels/update webhook (fires immediately):
  - check if product had >= 5 orders in last 7 days
  - if inventory = 0 → fire OOS incident immediately (no wait)

Auto-resolve:
  - next inventory_levels/update for same product with qty > 0
```

### Incident lifecycle

```
[detected] → [alert_sent] → [resolved]

State transitions:
  detected   → alert_sent: AlertDispatcher picks up, sends email + Slack
  alert_sent → resolved:   auto-resolve conditions met (per detector above)
  detected   → resolved:   condition clears before alert is sent (no alert fires)
```

---

## 9. Revenue Impact Calculation

**Principle:** Always show the formula. Always label as "estimated". Never show a dollar figure for JS errors (signal too weak).

### Checkout drop

```
AOV = total_revenue_last_30d / completed_orders_last_30d

missed_conversions = (baseline_rate - current_rate) * checkout_starts_in_window

estimated_impact = missed_conversions * AOV
```

**UI display:**
```
Estimated impact: ~$2,400
  ↳ 8 likely missed conversions × $300 avg order value
  ↳ Based on: checkout rate dropped from 62% → 31% (last 60 min)
  ↳ Baseline calculated from last 7 days of same-hour data
```

Confidence: High

### Payment failures

```
excess_failed = (current_pending_rate - baseline_pending_rate) * total_orders_in_window
estimated_impact = excess_failed * AOV
```

Confidence: Medium (some pending orders resolve; impact may be lower)

### JS errors

```
estimated_impact = NULL   ← no dollar figure
UI shows: "X errors detected on cart page — may be causing checkout friction"
```

### Out-of-stock hot product

```
daily_order_rate = orders_last_7d / 7    [for this product/variant only]
hours_oos = (now - inventory_hit_zero_at) / 3600
estimated_impact = daily_order_rate * (hours_oos / 24) * product_price
```

Confidence: Medium-High (assumes demand does not pause during OOS)

### Rules

- Never say "You lost $X" — always "Estimated impact: ~$X"
- Never show a dollar figure for JS errors
- Always show the breakdown formula beneath the number
- Show confidence level (high/medium) next to each estimate

---

## 10. Pricing Model

| Plan | Price/month | GMV tier | Trial |
|---|---|---|---|
| Starter | $29 | < $500K GMV | 14 days free |
| Growth | $79 | $500K–$2M GMV | 14 days free |
| Pro | $199 | $2M–$10M GMV | 14 days free |
| Agency | $399 | Multi-store (up to 10) | 14 days free |

- Shopify takes 20% cut (revenue under $1M/year), 15% above $1M
- No permanent free tier — product requires continuous backend compute
- Trial logic: `trial_days=14` in Shopify RecurringApplicationCharge API
- After trial: merchant selects plan or access is revoked automatically

**Trial design rationale:** Days 1-7 = baseline calibrating (no alerts fire). Days 8-14 = first real alerts with revenue numbers. A 7-day trial would end exactly when the product gets interesting.

---

## 11. Shopify App Store Compliance

### Technical requirements

- HTTPS on all endpoints (no exceptions)
- HMAC-SHA256 verification on every inbound webhook (reject with 401 if invalid)
- All API endpoints respond in < 5 seconds
- Admin UI renders in Shopify App Bridge (iframe inside Shopify admin, not external window)
- OAuth scopes match exactly what the app uses — no unused scopes

### Required OAuth scopes

```
read_orders
read_checkouts
read_inventory
read_products
write_script_tags
```

### Mandatory GDPR webhooks (all 3 required — auto-fail if missing)

```
customers/data_request  → return JSON list of data stored for that customer
customers/redact        → delete customer-linked data within 30 days
shop/redact             → delete all shop data within 90 days
```

### App listing requirements

- Privacy policy URL (public, HTTPS) — must name specific data collected and retention period
- Support email — Shopify tests response time (must reply within 3 business days)
- App icon: 1024×1024 PNG
- Screenshots: minimum 3, showing actual dashboard in use
- App description must match OAuth scopes requested

### Review process timeline

```
Submit → automated checks (48h)
       → human review queue (1-3 weeks)
       → reviewer installs on test store, manually tests:
           install flow, App Bridge render, at least 1 feature,
           uninstall + data deletion, privacy policy accessible
       → approved / rejected with feedback
```

Most common rejection reasons:
1. Missing GDPR webhooks
2. Admin UI opens external window instead of App Bridge iframe
3. Privacy policy doesn't name specific data collected
4. Response time > 5s

### Pre-submission checklist

- [ ] All 3 GDPR webhooks registered and returning 200
- [ ] `app/uninstalled` deletes shop webhooks + anonymizes data within 48h
- [ ] All endpoints < 5s under realistic load
- [ ] Privacy policy published at public HTTPS URL, names all data collected
- [ ] Admin loads inside Shopify admin iframe (App Bridge)
- [ ] OAuth scopes match app functionality exactly
- [ ] Full install + uninstall tested on a real Shopify development store

---

## 12. Infrastructure

| Component | Choice | Cost/month |
|---|---|---|
| Backend + DB hosting | Railway (FastAPI + PostgreSQL managed) | ~$25 |
| Email alerts | SendGrid free tier (100 emails/day) | $0 |
| Slack alerts | Incoming webhooks (free) | $0 |
| Domain | Custom domain for app URL | ~$1 |
| **Total v1** | | **~$26-35/month** |

Scale triggers:
- Add Celery + Redis when > 500 stores (asyncio background tasks become bottleneck)
- Move to dedicated PostgreSQL when > 200GB data
- Add CDN for Theme Extension JS when > 1,000 stores

---

## 13. Implementation Order (for planning reference)

1. Shopify Partner account + development store setup
2. FastAPI project skeleton + Railway deployment + PostgreSQL connection
3. Shopify OAuth flow (install, token storage, uninstall)
4. Webhook registration + HMAC verification + raw storage
5. GDPR webhook handlers (mandatory before review)
6. Theme App Extension (JS error capture + /events endpoint)
7. WebhookProcessor background worker (webhook → DB tables)
8. IncidentDetector (5-min heartbeat, all 4 detection types)
9. AlertDispatcher (email + Slack)
10. React admin dashboard (App Bridge embed, Polaris components)
11. Billing integration (RecurringApplicationCharge, trial logic)
12. Privacy policy page + App Store listing preparation
13. Testing on development store (install, trigger incidents, verify alerts)
14. App Store submission

---

## 14. Open Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Revenue estimates inaccurate → merchant distrust | High | Conservative estimates, transparent formula, "~" prefix always |
| App Store review rejection on first submission | Medium | Follow compliance checklist exactly; test on dev store first |
| False positive alerts → merchant turns off | Medium | Noise floor (min 5 checkouts), 7-day baseline before activating |
| Checkout.liquid deprecation limits JS scope | Low | Already scoped to cart/product pages only in this spec |
| Railway outage causes missed webhooks | Low | Shopify retries failed webhooks for 48h |

---

*Spec self-review: no TBD/TODO placeholders, no internal contradictions, no scope creep beyond v1 features, all technical corrections from design session incorporated.*
