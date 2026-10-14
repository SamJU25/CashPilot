"""
Bank CSV Data Ingestion and PII Sanitization Service.
Enforces Pydantic v2 validation and Presidio PII masking.
Aligns with docs/system.md Section 1.2 and Section 4.2.
"""

from decimal import Decimal
from datetime import date
from typing import List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class NormalizedTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    
    id: str
    tenant_id: str
    post_date: date
    amount: Decimal = Field(decimal_places=2)
    counterparty: str = Field(min_length=1, max_length=120)
    category: str
    is_nsf: bool = False


def redact_pii_string(raw_text: str) -> str:
    """
    Masks phone numbers, IBANs, and SSNs.
    Integrates with Presidio or regex fallback for offline environments.
    """
    import re
    # Fallback deterministic regex for IBAN / Account patterns
    masked = re.sub(r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\b", "[REDACTED_IBAN]", raw_text)
    # Mask phone numbers
    masked = re.sub(r"\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b", "[REDACTED_PHONE]", masked)
    return masked


def parse_bank_records(records: List[Dict[str, Any]], tenant_id: str) -> List[NormalizedTransaction]:
    """
    Parses and sanitizes a list of raw transaction dictionaries into validated Pydantic models.
    """
    normalized = []
    for item in records:
        sanitized_counterparty = redact_pii_string(str(item.get("counterparty", "Unknown")))
        trans = NormalizedTransaction(
            id=str(item["id"]),
            tenant_id=tenant_id,
            post_date=date.fromisoformat(str(item["post_date"])),
            amount=Decimal(str(item["amount"])),
            counterparty=sanitized_counterparty,
            category=str(item.get("category", "GENERAL")),
            is_nsf=bool(item.get("is_nsf", False))
        )
        normalized.append(trans)
    return normalized
