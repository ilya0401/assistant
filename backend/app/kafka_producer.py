import json
import logging

from confluent_kafka import Producer

from .config import settings

log = logging.getLogger(__name__)

TOPIC = "jira-worklog-requests"

_producer: Producer | None = None


def _get_producer() -> Producer:
    global _producer
    if _producer is None:
        _producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    return _producer


def publish_worklog_entry(entry_id: int, task: str, time_spent: str, date: str, description: str) -> None:
    """Publishes the entry for async Jira delivery. Raises if the broker doesn't confirm delivery."""
    payload = {
        "entry_id": entry_id,
        "task": task,
        "time_spent": time_spent,
        "date": date,
        "description": description,
    }
    delivery_errors: list[str] = []

    def _on_delivery(err, msg):
        if err is not None:
            delivery_errors.append(str(err))

    producer = _get_producer()
    producer.produce(
        TOPIC,
        key=str(entry_id),
        value=json.dumps(payload, ensure_ascii=False),
        callback=_on_delivery,
    )
    producer.flush(timeout=10)
    if delivery_errors:
        raise RuntimeError(delivery_errors[0])
    log.info("Published entry #%d to Kafka topic %s", entry_id, TOPIC)
