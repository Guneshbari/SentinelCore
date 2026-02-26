"""
SentinelCore - Kafka to PostgreSQL Consumer (v2.0.0 - Reliability Hardened)
Reads events from Kafka topic 'sentinel-events' and inserts into PostgreSQL.
Run this inside WSL where Kafka and PostgreSQL are running.

RELIABILITY FEATURES:
- Manual offset commit only after successful DB insert
- Persistent DB connection with exponential backoff reconnection
- Transaction rollback on insert failure (batch-level)
- Never exits on transient errors — logs and retries
- Idempotent inserts via ON CONFLICT (event_hash) DO NOTHING
- Structured logging for reliability debugging

Usage:
    python3 kafka_to_postgres.py

Environment Variables:
    POSTGRES_HOST     (default: localhost)
    POSTGRES_PORT     (default: 5432)
    POSTGRES_DB       (default: sentinel_logs)
    POSTGRES_USER     (default: sentinel_admin)
    POSTGRES_PASSWORD (default: changeme123)
    KAFKA_SERVERS     (default: localhost:9092)
    KAFKA_TOPIC       (default: sentinel-events)
    KAFKA_GROUP_ID    (default: sentinel-consumer-group)
"""

import json
import os
import sys
import signal
import logging
import time
from datetime import datetime

try:
    from kafka import KafkaConsumer
    from kafka.errors import KafkaError
except ImportError:
    print("ERROR: kafka-python-ng is required. Install with: pip install kafka-python-ng", file=sys.stderr)
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:
    print("ERROR: psycopg2 is required. Install with: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

# ============================================================================
# CONFIGURATION
# ============================================================================

CONSUMER_VERSION = "2.0.0"

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "sentinel_logs")
POSTGRES_USER = os.getenv("POSTGRES_USER", "sentinel_admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme123")

KAFKA_SERVERS = os.getenv("KAFKA_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sentinel-events")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "sentinel-consumer-group")

# Retry configuration
DB_MAX_RETRIES = 5
DB_RETRY_BACKOFF_BASE = 2.0  # seconds (exponential: 2, 4, 8, 16, 32)
DB_MAX_BACKOFF = 60  # seconds cap

KAFKA_POLL_TIMEOUT_MS = 3000
KAFKA_CONSUMER_TIMEOUT_MS = 5000
KAFKA_MAX_POLL_RECORDS = 100

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
# INSERT QUERY (idempotent via ON CONFLICT)
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
# SHUTDOWN HANDLER
# ============================================================================

shutdown_requested = False


def signal_handler(sig, frame):
    global shutdown_requested
    logger.info("Shutdown signal received, finishing current batch...")
    shutdown_requested = True


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ============================================================================
# DATABASE CONNECTION WITH RETRY
# ============================================================================


def connect_postgres(max_retries=DB_MAX_RETRIES):
    """Connect to PostgreSQL with exponential backoff retry.
    Returns connection on success, None on failure (never exits)."""
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                dbname=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD
            )
            conn.autocommit = False
            logger.info(f"Connected to PostgreSQL at "
                        f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
            return conn
        except psycopg2.Error as e:
            backoff = min(DB_RETRY_BACKOFF_BASE * (2 ** attempt), DB_MAX_BACKOFF)
            logger.error(f"PostgreSQL connection failed "
                         f"(attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"  Retrying in {backoff:.0f}s...")
                time.sleep(backoff)
    logger.critical("Could not connect to PostgreSQL after all retries.")
    return None


def ensure_db_connection(conn):
    """Check if DB connection is alive. Reconnect if needed.
    Returns a valid connection or None."""
    if conn is not None:
        try:
            # Lightweight health check
            conn.cursor().execute("SELECT 1")
            return conn
        except Exception:
            logger.warning("PostgreSQL connection lost. Attempting reconnection...")
            try:
                conn.close()
            except Exception:
                pass

    return connect_postgres()


# ============================================================================
# MESSAGE PROCESSING
# ============================================================================


def process_message(msg_value, cursor):
    """
    Process a single Kafka message and insert into PostgreSQL.
    Returns True if the insert was successful or the record was a duplicate.
    Raises on unexpected errors so the caller can rollback.
    """
    system_id = msg_value.get('system_id', 'unknown')
    event = msg_value.get('event', {})

    row = {
        'system_id': system_id,
        'fault_type': event.get('fault_type', 'UNKNOWN'),
        'severity': event.get('severity', 'INFO'),
        'provider_name': event.get('provider_name'),
        'event_id': event.get('event_id'),
        'cpu_usage_percent': event.get('cpu_usage_percent'),
        'memory_usage_percent': event.get('memory_usage_percent'),
        'disk_free_percent': event.get('disk_free_percent'),
        'event_hash': event.get('event_hash'),
        'diagnostic_context': Json(event.get('diagnostic_context', {})),
        'raw_xml': event.get('raw_xml')
    }

    cursor.execute(INSERT_SQL, row)
    return True


# ============================================================================
# MAIN CONSUMER LOOP
# ============================================================================


def run_consumer():
    """Main consumer loop: Kafka → PostgreSQL (resilient, never exits on transient errors)"""
    logger.info(f"SentinelCore Kafka-to-PostgreSQL Consumer v{CONSUMER_VERSION}")
    logger.info("=" * 60)
    logger.info(f"Kafka:      {KAFKA_SERVERS} (topic: {KAFKA_TOPIC})")
    logger.info(f"PostgreSQL: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    logger.info(f"Group ID:   {KAFKA_GROUP_ID}")
    logger.info("=" * 60)

    # Connect to PostgreSQL (retry until success or shutdown)
    conn = None
    while conn is None and not shutdown_requested:
        conn = connect_postgres()
        if conn is None:
            logger.warning("Will retry PostgreSQL connection in 10s...")
            time.sleep(10)

    if shutdown_requested:
        logger.info("Shutdown requested before startup completed.")
        return

    cursor = conn.cursor()

    # Connect to Kafka (retry until success or shutdown)
    consumer = None
    kafka_connect_attempt = 0
    while consumer is None and not shutdown_requested:
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
            kafka_connect_attempt += 1
            backoff = min(DB_RETRY_BACKOFF_BASE * (2 ** kafka_connect_attempt), DB_MAX_BACKOFF)
            logger.error(f"Could not connect to Kafka "
                         f"(attempt {kafka_connect_attempt}): {e}")
            logger.info(f"  Retrying in {backoff:.0f}s...")
            time.sleep(backoff)

    if shutdown_requested:
        if conn:
            conn.close()
        logger.info("Shutdown requested before startup completed.")
        return

    total_inserted = 0
    total_duplicates = 0
    total_errors = 0

    logger.info("\nListening for events... (Press Ctrl+C to stop)\n")

    try:
        while not shutdown_requested:
            # Poll for messages
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

            batch_inserted = 0
            batch_skipped = 0
            batch_failed = False

            # Ensure DB connection is alive before processing
            conn = ensure_db_connection(conn)
            if conn is None:
                logger.error("PostgreSQL unavailable. Skipping batch "
                             "(offsets NOT committed — will re-process).")
                total_errors += 1
                time.sleep(5)
                continue

            cursor = conn.cursor()

            # Process all messages in this poll batch
            for topic_partition, records in messages.items():
                for record in records:
                    if shutdown_requested:
                        break

                    try:
                        if process_message(record.value, cursor):
                            batch_inserted += 1
                    except psycopg2.Error as e:
                        logger.error(f"DB insert error: {e}")
                        batch_failed = True
                        break
                    except Exception as e:
                        logger.error(f"Unexpected message processing error: {e}")
                        batch_skipped += 1

                if batch_failed:
                    break

            # Commit or rollback based on batch result
            if batch_failed:
                # Rollback entire batch — don't commit Kafka offset
                try:
                    conn.rollback()
                    logger.warning(f"Batch ROLLED BACK due to DB error. "
                                   f"Offsets NOT committed — will re-process.")
                except psycopg2.Error:
                    logger.error("Rollback failed. Reconnecting to DB...")
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
                total_errors += 1
                time.sleep(2)
                continue

            # Attempt DB commit, then Kafka offset commit
            try:
                conn.commit()
            except psycopg2.Error as e:
                logger.error(f"Database commit failed: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.warning("Offsets NOT committed due to DB commit failure.")
                # Reconnect DB
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
                total_errors += 1
                time.sleep(2)
                continue

            # DB commit succeeded — now commit Kafka offsets
            try:
                consumer.commit()
            except KafkaError as e:
                logger.error(f"Kafka offset commit failed: {e}. "
                             f"Some messages may be re-processed.")

            total_inserted += batch_inserted
            total_duplicates += batch_skipped

            if batch_inserted > 0:
                logger.info(
                    f"Inserted {batch_inserted} events into PostgreSQL "
                    f"(skipped {batch_skipped}) | "
                    f"Total: {total_inserted} inserted, "
                    f"{total_errors} errors"
                )

    except Exception as e:
        logger.error(f"Consumer fatal error: {e}")

    finally:
        logger.info("\nShutting down...")
        if consumer:
            try:
                consumer.close()
            except Exception:
                pass
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        logger.info(f"Final stats: {total_inserted} events inserted, "
                    f"{total_duplicates} skipped, {total_errors} errors")
        logger.info("Consumer shutdown complete")


if __name__ == "__main__":
    run_consumer()
