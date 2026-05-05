"""Assignment domain entity."""

from __future__ import annotations
from datetime import datetime

from grading_shared.domain.models import StrictModel


class Assignment(StrictModel):
    assignment_id: str
    title: str
    created_by: str  # teacher.id (UUID as str)
    created_at: datetime
