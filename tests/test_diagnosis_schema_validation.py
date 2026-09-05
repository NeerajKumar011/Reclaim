"""Tests for Diagnosis Engine schema validation & LLM client error handling.

Verifies:
1. Valid JSON responses parse into DiagnosisOutput and PromiseToPayOutput.
2. Malformed or invalid JSON/taxonomy outputs trigger DiagnosisValidationError after retry.
"""

from unittest.mock import MagicMock, patch
import pytest

from reclaim.diagnosis.classifier import FailureClassifier
from reclaim.diagnosis.llm_client import LLMClient
from reclaim.diagnosis.promise_extractor import PromiseExtractor
from reclaim.diagnosis.schemas import (
    DiagnosisOutput,
    PromiseToPayOutput,
    DiagnosisValidationError,
)
from reclaim.ingestion.schemas import EventCategory, RevenueEvent
from datetime import datetime, timezone
from decimal import Decimal


@pytest.fixture
def sample_event():
    return RevenueEvent(
        event_id="payment.failed:pay_test123",
        event_category=EventCategory.payment_failure,
        customer_id="cust-uuid-123",
        amount=Decimal("50000"),
        currency="INR",
        failure_reason_raw="BAD_REQUEST_ERROR",
        occurred_at=datetime.now(timezone.utc),
        source_metadata={"payment_id": "pay_test123"},
    )


def test_valid_diagnosis_output_parsing(sample_event):
    """Valid JSON mock parses cleanly into DiagnosisOutput."""
    mock_json = '{"cause": "INSUFFICIENT_FUNDS", "confidence": 0.92}'
    classifier = FailureClassifier()

    output = classifier.classify(sample_event, mock_response=mock_json)

    assert isinstance(output, DiagnosisOutput)
    assert output.cause == "INSUFFICIENT_FUNDS"
    assert output.confidence == 0.92


def test_valid_promise_extractor_parsing():
    """Valid JSON mock parses cleanly into PromiseToPayOutput."""
    mock_json = '{"promise": true, "date": "2026-09-01", "amount": 50000, "confidence": 0.95}'
    extractor = PromiseExtractor()

    output = extractor.extract("I will pay tomorrow ₹500", mock_response=mock_json)

    assert isinstance(output, PromiseToPayOutput)
    assert output.promise is True
    assert output.date == "2026-09-01"
    assert output.amount == 50000
    assert output.confidence == 0.95


def test_malformed_json_triggers_validation_error():
    """Malformed JSON response triggers DiagnosisValidationError after retry."""
    client = LLMClient(api_key="mock_key")

    # Mock the underlying LLM call to return broken JSON twice
    raw_1 = "THIS IS NOT VALID JSON {broken:"
    raw_2 = "STILL BROKEN JSON {{{"

    with patch.object(client, "_call_llm", side_effect=[raw_1, raw_2]):
        with pytest.raises(DiagnosisValidationError) as exc_info:
            client.generate_structured("test prompt", DiagnosisOutput)

        assert "LLM output validation failed after retry" in str(exc_info.value)


def test_invalid_taxonomy_enum_triggers_validation_error():
    """Valid JSON but invalid category enum triggers DiagnosisValidationError after retry."""
    client = LLMClient(api_key="mock_key")

    # Mock response with invented category not in taxonomy
    invalid_category_json = '{"cause": "NOT_A_REAL_CATEGORY", "confidence": 0.9}'

    with patch.object(client, "_call_llm", return_value=invalid_category_json):
        with pytest.raises(DiagnosisValidationError) as exc_info:
            client.generate_structured("test prompt", DiagnosisOutput)

        assert "validation failed after retry" in str(exc_info.value)

