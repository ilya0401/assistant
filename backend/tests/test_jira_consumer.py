from unittest.mock import patch

from app.jira_consumer import _deliver


def _payload(task: str = "KAN-99999") -> dict:
    return {
        "entry_id": 1,
        "task": task,
        "description": "автотест",
        "time_spent": "15m",
        "date": "2026-01-01",
    }


@patch("app.jira_consumer.jira_configured", return_value=True)
@patch("app.jira_consumer.find_issue", return_value=None)
@patch("app.jira_consumer.token_valid", side_effect=ConnectionError("DNS недоступен"))
def test_network_failure_in_token_valid_does_not_crash_consumer(
    mock_token_valid, mock_find_issue, mock_jira_configured
):
    """KAN-6: find_issue() вернул 404 (issue_summary is None), и в этот момент
    token_valid() падает с сетевой ошибкой (DNS/connection). _deliver() должен
    обработать это как транзиентный сбой (return False, уйдёт в retry с backoff),
    а не дать исключению всплыть и уронить процесс консьюмера целиком."""
    result = _deliver(_payload())
    assert result is False
