#!/usr/bin/env python3
"""Allerion billing sync — turns LiteLLM usage into Stripe invoices.

LiteLLM writes one row per request to LiteLLM_SpendLogs, including the
underlying USD `spend` (already model-aware) and the hashed api_key. We map
each key to a Stripe customer (via the key's metadata.stripe_customer_id),
then emit a Stripe Billing Meter event per request with value = underlying
cost in USD. The Stripe *price* encodes the markup, so the customer's invoice
= underlying_cost x markup, correct across every model automatically.

Idempotency: each meter event uses the LiteLLM request_id as its identifier,
so re-processing a row (after a crash/retry) is de-duplicated by Stripe.

Schema note: LiteLLM's Postgres table/column names can drift between versions.
If a query errors, verify names against your deployed LiteLLM version — they
are all isolated in fetch_rows() below.
"""
import os
import sys
import json
import time
import signal
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import stripe

DATABASE_URL = os.environ["DATABASE_URL"]
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "").strip()
EVENT_NAME = os.environ.get("STRIPE_METER_EVENT_NAME", "allerion_api_usage")
INTERVAL = int(os.environ.get("BILLING_SYNC_INTERVAL", "60"))
BATCH = int(os.environ.get("BILLING_BATCH_SIZE", "500"))

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_running = True


def log(msg):
    print(f"[billing] {datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


def _stop(*_):
    global _running
    _running = False
    log("shutdown signal received; finishing current cycle")


def bootstrap(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS billing_state (
                k text PRIMARY KEY,
                v text NOT NULL
            );
            CREATE TABLE IF NOT EXISTS billing_unmapped (
                request_id text PRIMARY KEY,
                api_key    text,
                model      text,
                spend      numeric,
                ts         timestamptz,
                recorded_at timestamptz DEFAULT now()
            );
            """
        )
    conn.commit()


def get_watermark(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT v FROM billing_state WHERE k = 'watermark'")
        row = cur.fetchone()
    if not row:
        return EPOCH, ""
    data = json.loads(row[0])
    return datetime.fromisoformat(data["ts"]), data.get("request_id", "")


def set_watermark(conn, ts, request_id):
    payload = json.dumps({"ts": ts.isoformat(), "request_id": request_id})
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO billing_state (k, v) VALUES ('watermark', %s)
            ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v
            """,
            (payload,),
        )
    conn.commit()


def fetch_rows(conn, ts, request_id, limit):
    """Pull spend-log rows after the (ts, request_id) cursor, oldest first.

    The composite cursor avoids skipping rows that share a startTime.
    """
    sql = """
        SELECT s.request_id,
               s."startTime"   AS ts,
               s.spend         AS spend,
               s.model         AS model,
               s.api_key       AS api_key,
               v.metadata      AS token_metadata
        FROM   "LiteLLM_SpendLogs" s
        LEFT JOIN "LiteLLM_VerificationToken" v ON s.api_key = v.token
        WHERE  (s."startTime" > %(ts)s)
            OR (s."startTime" = %(ts)s AND s.request_id > %(rid)s)
        ORDER BY s."startTime" ASC, s.request_id ASC
        LIMIT %(limit)s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, {"ts": ts, "rid": request_id, "limit": limit})
        return cur.fetchall()


def resolve_customer(token_metadata):
    if not token_metadata:
        return None
    meta = token_metadata
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            return None
    if isinstance(meta, dict):
        return meta.get("stripe_customer_id")
    return None


def record_unmapped(conn, row):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO billing_unmapped (request_id, api_key, model, spend, ts)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (request_id) DO NOTHING
            """,
            (row["request_id"], row["api_key"], row["model"], row["spend"], row["ts"]),
        )
    conn.commit()


def emit(customer_id, value_usd, request_id):
    # 12 decimals so sub-micro-dollar per-request costs aren't rounded to zero
    # (default "f" formatting keeps only 6 and would silently drop tiny usage).
    stripe.billing.MeterEvent.create(
        event_name=EVENT_NAME,
        identifier=request_id,  # Stripe de-dupes on this
        payload={"stripe_customer_id": customer_id, "value": f"{value_usd:.12f}"},
    )


def process_batch(conn):
    ts, rid = get_watermark(conn)
    rows = fetch_rows(conn, ts, rid, BATCH)
    if not rows:
        return 0, 0

    emitted = unmapped = 0
    for row in rows:
        spend = float(row["spend"] or 0)
        customer = resolve_customer(row["token_metadata"])

        if spend > 0 and customer:
            # Let a Stripe failure raise: we stop before advancing the
            # watermark, so the row is retried (and de-duped) next cycle.
            emit(customer, spend, row["request_id"])
            emitted += 1
        elif spend > 0 and not customer:
            record_unmapped(conn, row)  # no revenue silently lost
            unmapped += 1

        # Advance the cursor only after the row is safely handled.
        set_watermark(conn, row["ts"], row["request_id"])

    return emitted, unmapped


def main():
    if not STRIPE_API_KEY:
        sys.exit("STRIPE_API_KEY is not set — billing sync requires a Stripe secret key.")
    stripe.api_key = STRIPE_API_KEY

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log(f"starting; meter='{EVENT_NAME}', interval={INTERVAL}s, batch={BATCH}")
    conn = psycopg2.connect(DATABASE_URL)
    bootstrap(conn)

    while _running:
        try:
            emitted, unmapped = process_batch(conn)
            if emitted or unmapped:
                log(f"emitted={emitted} unmapped={unmapped}")
            # Drain quickly when a full batch came back; otherwise idle.
            if emitted + unmapped >= BATCH:
                continue
        except psycopg2.Error as e:
            log(f"db error: {e}; reconnecting")
            try:
                conn.close()
            except Exception:
                pass
            time.sleep(min(INTERVAL, 30))
            conn = psycopg2.connect(DATABASE_URL)
            continue
        except stripe.error.StripeError as e:
            log(f"stripe error: {e}; will retry from watermark")
        except Exception as e:  # noqa: BLE001 - keep the worker alive
            log(f"unexpected error: {e}; will retry")

        for _ in range(INTERVAL):
            if not _running:
                break
            time.sleep(1)

    conn.close()
    log("stopped")


if __name__ == "__main__":
    main()
