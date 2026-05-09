"""
Data models for the application.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Project:
    """Represents a freelance project scraped from a platform."""
    site: str
    title: str
    link: str
    description: str = ""
    budget: str = ""
    detected_at: Optional[datetime] = None
