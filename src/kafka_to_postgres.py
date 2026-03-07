"""
SentinelCore - Kafka to PostgreSQL Consumer
Version: 2.1.0

CHANGES FROM v2.0.0:
- Cursor created inside transaction scope (was leaking on every batch loop)
- Counters renamed to accurately reflect what they track
- shutdown_requested replaced with threading.Event (signal-safe)
- connect_postgres / ensure_db_connection merged into one clean DB manager class
- Removed redundant outer cursor declaration before the loop
"""

import json
import os
import sys
import signal
import logging
import time
import threading
from datetime import datetime

try:
    from kafka import KafkaConsumer
    from kafka.errors import KafkaError
except ImportError:
    print("ERROR: kafka-python-ng required. pip install kafka-python-ng", file=sys.stderr)
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:
    print("ERROR: psycopg2 required. pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

# ============================================================================
# CONFIGURATION
# ============================================================================

CONSUMER_VERSION = "2.1.0"

POSTGRES_HOST     = os.getenv("POSTGRES_HOST",     "localhost")
POSTGRES_PORT     = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB       = os.getenv("POSTGRES_DB",       "sentinel_logs")
POSTGRES_USER     = os.getenv("POSTGRES_USER",     "sentinel_admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme123")

KAFKA_SERVERS   = os.getenv("KAFKA_SERVERS",   "localhost:9092")
KAFKA_TOPIC     = os.getenv("KAFKA_TOPIC",     "sentinel-events")
KAFKA_GROUP_ID  = os.getenv("KAFKA_GROUP_ID",  "sentinel-consumer-group")

DB_MAX_RETRIES       = 5
DB_RETRY_BACKOFF_BASE = 2.0   # seconds — doubles each attempt: 2, 4, 8, 16, 32
DB_MAX_BACKOFF       = 60     # seconds cap

KAFKA_POLL_TIMEOUT_MS    = 3000
KAFKA_CONSUMER_TIMEOUT_MS = 5000
KAFKA_MAX_POLL_RECORDS   = 100

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('SentinelConsumer')

# ============================================================================
# INSERT QUERY — idempotent via ON CONFLICT
# ============================================================================

INSERT_SQL = """
INSERT INTO events (
    system_id, fault_type, severity, provider_name, event_id,
    cpu_usage_percent, memory_usage_percent, disk_free_percent,
    event_hash, diagnostic_context, raw_xml
) VALUES (
    %(system_id)s, %(fault_type)s, %(severity)s, %(provider_name)s, %(event_id)s,
    %(cpu_usage_percent)s, %(memory_usage_percent)s, %(disk_free_percent)s,
    %(event_hash)s, %(diagnostic_context)s, %(raw_xml)s
)
ON CONFLICT (event_hash) DO NOTHING;
"""

# ============================================================================
# SHUTDOWN — threading.Event is signal-handler safe (vs plain global bool)
# ============================================================================

_shutdown = threading.Event()


def _handle_signal(sig, frame):
    logger.info("Shutdown signal received — finishing current batch...")
    _shutdown.set()


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

# ============================================================================
# DATABASE MANAGER
# ============================================================================

class DBManager:
    """
    Owns the PostgreSQL connection lifecycle.
    - connect()        : establish connection with exponential backoff retry
    - ensure()         : health-check; reconnects transparently if connection dropped
    - cursor()         : context manager — always opens a fresh cursor per transaction
    - commit/rollback  : explicit transaction control
    """

    def __init__(self):
        self._conn = None

    def connect(self, max_retries: int = DB_MAX_RETRIES) -> bool:
        """Attempt to connect. Returns True on success, False after all retries."""
        for attempt in range(max_retries):
            try:
                self._conn = psycopg2.connect(
                    host=POSTGRES_HOST, port=POSTGRES_PORT,
                    dbname=POSTGRES_DB, user=POSTGRES_USER,
                    password=POSTGRES_PASSWORD
                )
                self._conn.autocommit = False
                logger.info(f"Connected to PostgreSQL at {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
                return True
            except psycopg2.Error as e:
                backoff = min(DB_RETRY_BACKOFF_BASE * (2 ** attempt), DB_MAX_BACKOFF)
                logger.error(f"PostgreSQL connection failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    logger.info(f"  Retrying in {backoff:.0f}s...")
                    time.sleep(backoff)
        logger.critical("Could not connect to PostgreSQL after all retries.")
        self._conn = None
        return False

    def ensure(self) -> bool:
        """Verify connection is alive; reconnect if not. Returns True if ready."""
        if self._conn is not None:
            try:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1")
                return True
            except Exception:
                logger.warning("PostgreSQL connection lost. Reconnecting...")
                self._close_quietly()
        return self.connect()

    def new_cursor(self):
        """Return a fresh cursor. Caller is responsible for closing it."""
        return self._conn.cursor()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            self._close_quietly()

    def _close_quietly(self):
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass
        self._conn = None

    def close(self):
        self._close_quietly()
        logger.info("PostgreSQL connection closed")

# ============================================================================
# MESSAGE PROCESSING
# ============================================================================

def process_message(msg_value: dict, cursor) -> bool:
    """
    Insert one Kafka message into PostgreSQL.
    Returns True on success (including silent duplicate skip via ON CONFLICT).
    Raises psycopg2.Error on DB failure so the caller can rollback.
    """
    system_id = msg_value.get('system_id', 'unknown')
    event     = msg_value.get('event', {})

    row = {
        'system_id':            system_id,
        'fault_type':           event.get('fault_type', 'UNKNOWN'),
        'severity':             event.get('severity', 'INFO'),
        'provider_name':        event.get('provider_name'),
        'event_id':             event.get('event_id'),
        'cpu_usage_percent':    event.get('cpu_usage_percent'),
        'memory_usage_percent': event.get('memory_usage_percent'),
        'disk_free_percent':    event.get('disk_free_percent'),
        'event_hash':           event.get('event_hash'),
        'diagnostic_context':   Json(event.get('diagnostic_context', {})),
        'raw_xml':              event.get('raw_xml'),
    }
    cursor.execute(INSERT_SQL, row)
    return True

# ============================================================================
# MAIN CONSUMER LOOP
# ============================================================================

def run_consumer():
    logger.info(f"SentinelCore Kafka→PostgreSQL Consumer v{CONSUMER_VERSION}")
    logger.info("=" * 60)
    logger.info(f"Kafka      : {KAFKA_SERVERS}  (topic: {KAFKA_TOPIC})")
    logger.info(f"PostgreSQL : {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    logger.info(f"Group ID   : {KAFKA_GROUP_ID}")
    logger.info("=" * 60)

    # ── Connect to PostgreSQL ────────────────────────────────────────────────
    db = DBManager()
    while not _shutdown.is_set():
        if db.connect():
            break
        logger.warning("Retrying PostgreSQL in 10s...")
        time.sleep(10)

    if _shutdown.is_set():
        logger.info("Shutdown before startup completed.")
        return

    # ── Connect to Kafka ─────────────────────────────────────────────────────
    consumer = None
    kafka_attempt = 0
    while consumer is None and not _shutdown.is_set():
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_SERVERS,
                group_id=KAFKA_GROUP_ID,
                auto_offset_reset='earliest',
                enable_auto_commit=False,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                consumer_timeout_ms=KAFKA_CONSUMER_TIMEOUT_MS,
                max_poll_records=KAFKA_MAX_POLL_RECORDS
            )
            logger.info("Connected to Kafka consumer")
        except Exception as e:
            kafka_attempt += 1
            backoff = min(DB_RETRY_BACKOFF_BASE * (2 ** kafka_attempt), DB_MAX_BACKOFF)
            logger.error(f"Kafka connection failed (attempt {kafka_attempt}): {e}")
            logger.info(f"  Retrying in {backoff:.0f}s...")
            time.sleep(backoff)

    if _shutdown.is_set():
        db.close()
        logger.info("Shutdown before startup completed.")
        return

    # ── Counters (named for what they actually track) ─────────────────────
    total_inserted    = 0   # rows written to DB
    total_skipped     = 0   # processing errors for individual messages
    total_batch_fails = 0   # batches rolled back due to DB error

    logger.info("\nListening for events... (Ctrl+C to stop)\n")

    try:
        while not _shutdown.is_set():

            # Poll Kafka
            try:
                messages = consumer.poll(timeout_ms=KAFKA_POLL_TIMEOUT_MS)
            except KafkaError as e:
                logger.error(f"Kafka poll error: {e}. Continuing...")
                time.sleep(2)
                continue
            except Exception as e:
                logger.error(f"Unexpected Kafka poll error: {e}. Continuing...")
                time.sleep(2)
                continue

            if not messages:
                continue

            # Ensure DB is alive before touching data
            if not db.ensure():
                logger.error("PostgreSQL unavailable — skipping batch (offsets NOT committed, will re-process).")
                total_batch_fails += 1
                time.sleep(5)
                continue

            batch_inserted = 0
            batch_failed   = False

            # ── Open cursor INSIDE the transaction scope ───────────────────
            cursor = db.new_cursor()
            try:
                for tp, records in messages.items():
                    for record in records:
                        if _shutdown.is_set():
                            break
                        try:
                            process_message(record.value, cursor)
                            batch_inserted += 1
                        except psycopg2.Error as e:
                            logger.error(f"DB insert error: {e}")
                            batch_failed = True
                            break
                        except Exception as e:
                            logger.error(f"Message processing error (skipping): {e}")
                            total_skipped += 1
                    if batch_failed or _shutdown.is_set():
                        break

                if batch_failed:
                    raise psycopg2.Error("Batch insert failed — triggering rollback")

                # Commit DB, then commit Kafka offsets
                db.commit()
                try:
                    consumer.commit()
                except KafkaError as e:
                    logger.error(f"Kafka offset commit failed: {e} — some messages may re-process")

                total_inserted += batch_inserted
                if batch_inserted:
                    logger.info(
                        f"Inserted {batch_inserted} event(s) | "
                        f"Total: {total_inserted} inserted, "
                        f"{total_skipped} skipped, "
                        f"{total_batch_fails} batch rollbacks"
                    )

            except psycopg2.Error:
                db.rollback()
                logger.warning(f"Batch ROLLED BACK — offsets NOT committed, will re-process.")
                total_batch_fails += 1
                time.sleep(2)

            finally:
                # Cursor always closed here — no leaks regardless of code path
                try:
                    cursor.close()
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Consumer fatal error: {e}")

    finally:
        logger.info("\nShutting down...")
        if consumer:
            try:
                consumer.close()
            except Exception:
                pass
        db.close()
        logger.info(
            f"Final stats: {total_inserted} inserted, "
            f"{total_skipped} skipped, "
            f"{total_batch_fails} batch rollbacks"
        )
        logger.info("Consumer shutdown complete")


if __name__ == "__main__":
    run_consumer()