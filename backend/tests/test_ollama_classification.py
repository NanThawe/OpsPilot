from types import SimpleNamespace
from uuid import uuid4

import app.services.classification as classification_service
import pytest
from app.core.config import settings
from app.db.models import DocumentPage


def make_test_page():
    return DocumentPage(
        document_id=uuid4(),
        page_number=1,
        text=(
            "PURCHASE ORDER PO-SYN-2026-001. "
            "Supplier: Cedarline Office Systems. "
            "Ordered goods and delivery date."
        ),
    )


def test_ollama_returns_structured_classification(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "ollama")
    monkeypatch.setattr(
        settings,
        "ollama_model",
        "qwen3:4b-instruct",
    )

    class FakeOllamaClient:
        def __init__(self, host, timeout):
            assert host == settings.ollama_base_url

        def chat(self, **kwargs):
            assert kwargs["model"] == "qwen3:4b-instruct"

            assert kwargs["format"] == (
                classification_service.ClassificationProposal.model_json_schema()
            )

            return SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        '{"predicted_type":"purchase_order",'
                        '"confidence":"high",'
                        '"rationale":"The document orders goods.",'
                        '"evidence_page_numbers":[1]}'
                    )
                )
            )

    monkeypatch.setattr(
        classification_service,
        "OllamaClient",
        FakeOllamaClient,
    )

    result = classification_service.classify_pages([make_test_page()])

    assert result.predicted_type == "purchase_order"
    assert result.confidence == "high"
    assert result.evidence_page_numbers == [1]

    assert (
        classification_service.classification_model_name() == "ollama:qwen3:4b-instruct"
    )


def test_invalid_ollama_json_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "ollama")

    class FakeOllamaClient:
        def __init__(self, host, timeout):
            pass

        def chat(self, **kwargs):
            return SimpleNamespace(message=SimpleNamespace(content="not valid JSON"))

    monkeypatch.setattr(
        classification_service,
        "OllamaClient",
        FakeOllamaClient,
    )

    with pytest.raises(classification_service.ClassificationServiceError):
        classification_service.classify_pages([make_test_page()])
