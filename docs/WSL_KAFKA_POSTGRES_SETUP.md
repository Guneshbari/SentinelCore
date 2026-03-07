# Setting up Kafka & PostgreSQL in WSL

This guide walks you through setting up an end-to-end data pipeline inside Windows Subsystem for Linux (WSL).

## 1. Prerequisites

Ensure you have WSL 2 installed with Ubuntu. Open your **Ubuntu terminal** to run all the commands below.

```bash
sudo apt update && sudo apt upgrade -y
```

---

## 2. PostgreSQL Setup

### Install PostgreSQL

```bash
sudo apt install postgresql postgresql-contrib -y
sudo service postgresql start
```

### Create Database and User

Log into the PostgreSQL prompt:

```bash
sudo -u postgres psql
```

Run the following SQL commands to create the database, user, and table schema:

```sql
CREATE DATABASE sentinel_logs;
CREATE USER sentinel_admin WITH ENCRYPTED PASSWORD 'changeme123';
GRANT ALL PRIVILEGES ON DATABASE sentinel_logs TO sentinel_admin;
\c sentinel_logs

CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    system_id VARCHAR(50) NOT NULL,
    fault_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    provider_name VARCHAR(255),
    event_id INTEGER,
    cpu_usage_percent FLOAT,
    memory_usage_percent FLOAT,
    disk_free_percent FLOAT,
    event_hash VARCHAR(64) UNIQUE,
    diagnostic_context JSONB,
    raw_xml TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

GRANT ALL PRIVILEGES ON TABLE events TO sentinel_admin;
GRANT USAGE, SELECT ON SEQUENCE events_id_seq TO sentinel_admin;
\q
```

---

## 3. Kafka Setup (KRaft Mode - No Zookeeper)

Kafka now runs in KRaft mode, which simplifies setup as it doesn't require Zookeeper.

### Install Java

Kafka requires Java. Install OpenJDK 11:

```bash
sudo apt install default-jre -y
java -version
```

### Download and Extract Kafka

```bash
cd ~
wget https://downloads.apache.org/kafka/4.2.0/kafka_2.13-4.2.0.tgz
tar -xvzf kafka_2.13-4.2.0.tgz
cd kafka_2.13-4.2.0
```

### Configure and Start Kafka

Since you are testing locally, run these in the background or open new terminal tabs.

**1. Generate KRaft Cluster ID and format storage:**

```bash
KAFKA_CLUSTER_ID="$(bin/kafka-storage.sh random-uuid)"
bin/kafka-storage.sh format -t $KAFKA_CLUSTER_ID -c config/kraft/server.properties
```

**2. Start the Kafka Server:**

```bash
bin/kafka-server-start.sh config/kraft/server.properties
```

**3. Create the SentinelCore Topic:**
Open a _new_ WSL terminal tab, navigate to the Kafka folder (`cd ~/kafka_2.13-4.2.0`), and run:

```bash
bin/kafka-topics.sh --create --topic sentinel-events --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
```

---

## 4. Kafka Network Configuration for Windows Access

By default, Kafka only listens on `localhost` inside WSL. To allow the Windows collector to connect, you must update `server.properties`:

```bash
nano ~/kafka_2.13-4.2.0/config/kraft/server.properties
```

Find and set these properties (replace `<WSL_IP>` with output of `hostname -I`):

```properties
listeners=PLAINTEXT://0.0.0.0:9092
advertised.listeners=PLAINTEXT://<WSL_IP>:9092
```

> **Important:** The WSL IP can change after a reboot. Re-check with `hostname -I` and update both `server.properties` and your `config.json` if it changes.

After making changes, restart Kafka for them to take effect.

---

## Next Steps: Python Integration

Now that the WSL infrastructure is running on `localhost:5432` (Postgres) and `<WSL_IP>:9092` (Kafka), the next phase is connecting the Python pipeline:

1. **Windows-side:** SentinelCore reads `config.json` and publishes to the WSL Kafka broker.
2. **WSL-side:** The consumer script (`kafka_to_postgres.py`) listens on the topic and inserts events into PostgreSQL.
