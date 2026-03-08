from prometheus_client import start_http_server, Counter
import time

events_total = Counter('sentinelcore_events_total', 'Total processed events')

if __name__ == '__main__':
    start_http_server(8000)
    while True:
        events_total.inc()
        time.sleep(5)
