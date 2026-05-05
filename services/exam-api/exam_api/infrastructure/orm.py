"""SQLAlchemy 2.0 ORM models for the grading PostgreSQL schema."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TeacherORM(Base):
    __tablename__ = "teacher"

    # id = Cognito sub (UUID supplied by the auth adapter)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    assignments: Mapped[list[TeacherAssignmentORM]] = relationship(
        back_populates="teacher"
    )


class StudentORM(Base):
    __tablename__ = "student"

    # id = Cognito sub; created on first authenticated login, not at enrollment time
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AssignmentORM(Base):
    __tablename__ = "assignment"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teacher.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="created")
    description: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    pipeline_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    pipeline_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    teachers: Mapped[list[TeacherAssignmentORM]] = relationship(
        back_populates="assignment"
    )
    students: Mapped[list[StudentAssignmentORM]] = relationship(
        back_populates="assignment"
    )


class TeacherAssignmentORM(Base):
    __tablename__ = "teacher_assignment"

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="owner")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    teacher: Mapped[TeacherORM] = relationship(back_populates="assignments")
    assignment: Mapped[AssignmentORM] = relationship(back_populates="teachers")


class StudentAssignmentORM(Base):
    __tablename__ = "student_assignment"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="CASCADE"),
        nullable=False,
    )
    # school-assigned ID (set at enrollment); may differ from cognito_sub
    student_id: Mapped[str] = mapped_column(Text, nullable=False)
    # set when the student activates their Cognito account via the invite flow
    cognito_sub: Mapped[str | None] = mapped_column(Text)
    nom: Mapped[str] = mapped_column(Text, nullable=False)
    prenom: Mapped[str] = mapped_column(Text, nullable=False)
    classe: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    submission_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )
    pdf_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    assignment: Mapped[AssignmentORM] = relationship(back_populates="students")
