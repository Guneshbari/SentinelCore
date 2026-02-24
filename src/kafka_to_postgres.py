"""
SentinelCore - Kafka to PostgreSQL Consumer
Reads events from Kafka topic 'sentinel-events' and inserts into PostgreSQL.
Run this inside WSL where Kafka and PostgreSQL are running.

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

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "sentinel_logs")
POSTGRES_USER = os.getenv("POSTGRES_USER", "sentinel_admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme123")

KAFKA_SERVERS = os.getenv("KAFKA_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sentinel-events")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "sentinel-consumer-group")

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
# INSERT QUERY
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
# DATABASE CONNECTION
# ============================================================================

def connect_postgres():
    """Connect to PostgreSQL with retry"""
    for attempt in range(3):
        try:
            conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                dbname=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD
            )
            conn.autocommit = False
            logger.info(f"Connected to PostgreSQL at {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
            return conn
        except psycopg2.Error as e:
            logger.error(f"PostgreSQL connection failed (attempt {attempt + 1}/3): {e}")
            if attempt < 2:
                import time
                time.sleep(2 ** attempt)
    logger.critical("Could not connect to PostgreSQL. Exiting.")
    sys.exit(1)

# ============================================================================
# MESSAGE PROCESSING
# ============================================================================

def process_message(msg_value, cursor):
    """
    Process a single Kafka message and insert into PostgreSQL.
    Returns True if the insert was successful or the record was a duplicate.
    """
    try:
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

    except Exception as e:
        logger.error(f"Failed to process message: {e}")
        return False

# ============================================================================
# MAIN CONSUMER LOOP
# ============================================================================

def run_consumer():
    """Main consumer loop: Kafka → PostgreSQL"""
    logger.info("SentinelCore Kafka-to-PostgreSQL Consumer")
    logger.info("=" * 60)
    logger.info(f"Kafka:      {KAFKA_SERVERS} (topic: {KAFKA_TOPIC})")
    logger.info(f"PostgreSQL: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    logger.info(f"Group ID:   {KAFKA_GROUP_ID}")
    logger.info("=" * 60)

    # Connect to PostgreSQL
    conn = connect_postgres()
    cursor = conn.cursor()

    # Connect to Kafka
    try:
        consumer = KafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=KAFKA_SERVERS,
            group_id=KAFKA_GROUP_ID,
            auto_offset_reset='earliest',
            enable_auto_commit=False,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            consumer_timeout_ms=5000,  # Poll timeout
            max_poll_records=100
        )
        logger.info("Connected to Kafka consumer")
    except Exception as e:
        logger.critical(f"Could not connect to Kafka: {e}")
        conn.close()
        sys.exit(1)

    total_inserted = 0
    total_duplicates = 0

    logger.info("\nListening for events... (Press Ctrl+C to stop)\n")

    try:
        while not shutdown_requested:
            # Poll for messages (blocks up to consumer_timeout_ms)
            messages = consumer.poll(timeout_ms=3000)

            if not messages:
                continue

            batch_inserted = 0
            batch_skipped = 0

            for topic_partition, records in messages.items():
                for record in records:
                    if shutdown_requested:
                        break

                    if process_message(record.value, cursor):
                        batch_inserted += 1
                    else:
                        batch_skipped += 1

            # Commit DB transaction, then Kafka offset
            try:
                conn.commit()
                consumer.commit()

                total_inserted += batch_inserted
                total_duplicates += batch_skipped

                if batch_inserted > 0:
                    logger.info(
                        f"Inserted {batch_inserted} events into PostgreSQL "
                        f"(skipped {batch_skipped}) | Total: {total_inserted}"
                    )
            except psycopg2.Error as e:
                logger.error(f"Database commit failed: {e}")
                conn.rollback()
                # Don't commit Kafka offsets on DB failure — will re-process

    except Exception as e:
        logger.error(f"Consumer error: {e}")

    finally:
        logger.info("\nShutting down...")
        consumer.close()
        cursor.close()
        conn.close()
        logger.info(f"Final stats: {total_inserted} events inserted, {total_duplicates} skipped")
        logger.info("Consumer shutdown complete")


if __name__ == "__main__":
    run_consumer()
