from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, field_validator
import hashlib


class Offer(BaseModel):
    """Represents a single PhD/research position offer."""

    source: str
    title: str
    institution: Optional[str] = None
    lab: Optional[str] = None
    professor: Optional[str] = None
    url: str
    country: Optional[str] = None
    location: Optional[str] = None
    funding_type: Optional[str] = None
    language: Optional[str] = None
    deadline: Optional[str] = None        # ISO date string or None
    published_at: Optional[str] = None   # ISO date string or None
    keywords_hit: Optional[str] = None   # comma-separated matched keywords
    description: Optional[str] = None    # short excerpt for keyword matching

    @property
    def url_hash(self) -> str:
        """SHA-256 hash of the normalized URL, used as unique dedup key."""
        normalized = self.url.strip().rstrip("/").lower()
        return hashlib.sha256(normalized.encode()).hexdigest()


class Source(BaseModel):
    """Represents a configured scraper source from sources.yaml."""

    name: str
    module: str
    class_name: str = "class"
    enabled: bool = True
