"""Pydantic models shared across grading-cloud services."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model enforcing strict payload validation."""

    model_config = ConfigDict(extra="forbid", strict=True)


class StudentModel(StrictModel):
    student_id: str
    first_name: str
    last_name: str


class Niveau3Model(StrictModel):
    criterion_id: str
    label: str
    max_points: float = Field(ge=0)
    points_awarded: float = Field(ge=0)
    feedback: str


class Niveau2Model(StrictModel):
    criterion_id: str
    label: str
    max_points: float = Field(ge=0)
    points_awarded: float = Field(ge=0)
    criteres_niveau3: list[Niveau3Model] = Field(default_factory=list)


class Niveau1Model(StrictModel):
    criterion_id: str
    label: str
    max_points: float = Field(ge=0)
    points_awarded: float = Field(ge=0)
    criteres_niveau2: list[Niveau2Model] = Field(default_factory=list)


class TotauxModel(StrictModel):
    total_max_points: float = Field(ge=0)
    total_points_awarded: float = Field(ge=0)
    percentage: float = Field(ge=0, le=100)
    grade: float = Field(ge=0)


class MetaModel(StrictModel):
    corrected_at: str
    correction_model: str
    rubric_version: str
    language: str = "fr"


class NotationPayload(StrictModel):
    exam_id: str
    student: StudentModel
    criteres_niveau1: list[Niveau1Model] = Field(default_factory=list)
    totaux: TotauxModel
    meta: MetaModel

