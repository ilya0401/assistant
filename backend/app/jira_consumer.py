import json
import logging
import time

from confluent_kafka import Consumer

from .config import settings
from .jira_client import find_issue, jira_configured, log_work
from .kafka_producer import TOPIC

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

GROUP_ID = "jira-delivery"
RETRY_BACKOFF_SECONDS = 5


def _deliver(payload: dict) -> bool:
    """Returns True if the message is done (commit offset), False if it should be retried."""
    entry_id = payload["entry_id"]
    task = payload["task"]

    if task == "—" or not jira_configured():
        log.info("Entry #%s: skip (no task / Jira not configured)", entry_id)
        return True

    if not payload["description"].strip():
        log.warning("Entry #%s: no description, skipping Jira delivery", entry_id)
        return True

    try:
        issue_summary = find_issue(task)
    except Exception as e:
        log.error("Entry #%s: find_issue error, will retry: %s", entry_id, e)
        return False

    if issue_summary is None:
        log.warning("Entry #%s: task %s not found in Jira, giving up", entry_id, task)
        return True

    ok = log_work(task, payload["time_spent"], payload["date"], payload["description"])
    if ok:
        log.info("Entry #%s: logged to Jira (%s)", entry_id, task)
        return True

    log.error("Entry #%s: log_work failed, will retry", entry_id)
    return False


def main() -> None:
    consumer = Consumer({
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([TOPIC])
    log.info("Jira consumer started, listening on %s", TOPIC)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                log.error("Kafka error: %s", msg.error())
                continue

            payload = json.loads(msg.value())
            if _deliver(payload):
                consumer.commit(msg)
            else:
                time.sleep(RETRY_BACKOFF_SECONDS)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
