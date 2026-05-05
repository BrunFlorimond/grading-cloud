"""Initial schema: teacher, student, assignment + junction tables + RLS.

Revision ID: 001
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = [
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grading_app') THEN
                CREATE ROLE grading_app LOGIN;
            END IF;
        END
        $$;
        """,
        """
        CREATE TABLE teacher (
            id          UUID        PRIMARY KEY,
            email       TEXT        NOT NULL,
            full_name   TEXT        NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,
        """
        CREATE TABLE student (
            id          UUID        PRIMARY KEY,
            email       TEXT        NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,
        """
        CREATE TABLE assignment (
            id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            title                 TEXT        NOT NULL,
            created_by            UUID        NOT NULL REFERENCES teacher(id),
            status                VARCHAR(30) NOT NULL DEFAULT 'created',
            description           TEXT,
            subject               TEXT,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            pipeline_started_at   TIMESTAMPTZ,
            pipeline_completed_at TIMESTAMPTZ
        );
        """,
        """
        CREATE TABLE teacher_assignment (
            teacher_id    UUID        NOT NULL REFERENCES teacher(id)    ON DELETE CASCADE,
            assignment_id UUID        NOT NULL REFERENCES assignment(id) ON DELETE CASCADE,
            role          VARCHAR(20) NOT NULL DEFAULT 'owner',
            joined_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (teacher_id, assignment_id)
        );
        """,
        """
        CREATE TABLE student_assignment (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            assignment_id     UUID        NOT NULL REFERENCES assignment(id) ON DELETE CASCADE,
            student_id        TEXT        NOT NULL,
            cognito_sub       TEXT,
            nom               TEXT        NOT NULL,
            prenom            TEXT        NOT NULL,
            classe            TEXT        NOT NULL,
            email             TEXT,
            submission_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            pdf_available     BOOLEAN     NOT NULL DEFAULT FALSE,
            enrolled_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (assignment_id, student_id)
        );
        """,
        """
        CREATE INDEX idx_student_assignment_cognito ON student_assignment (cognito_sub)
            WHERE cognito_sub IS NOT NULL;
        """,
        "GRANT USAGE ON SCHEMA public TO grading_app;",
        """
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON teacher, student, assignment, teacher_assignment, student_assignment
            TO grading_app;
        """,
        "ALTER TABLE teacher ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE student ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE assignment ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE teacher_assignment ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE student_assignment ENABLE ROW LEVEL SECURITY;",
        """
        CREATE POLICY teacher_self ON teacher FOR ALL TO grading_app
            USING (id = current_setting('app.user_id', true)::uuid);
        """,
        """
        CREATE POLICY student_self ON student FOR ALL TO grading_app
            USING (id = current_setting('app.user_id', true)::uuid);
        """,
        """
        CREATE POLICY assignment_for_teacher ON assignment FOR ALL TO grading_app
            USING (
                current_setting('app.user_type', true) = 'teacher'
                AND EXISTS (
                    SELECT 1 FROM teacher_assignment ta
                    WHERE ta.assignment_id = assignment.id
                      AND ta.teacher_id = current_setting('app.user_id', true)::uuid
                )
            );
        """,
        """
        CREATE POLICY teacher_assignment_self ON teacher_assignment FOR ALL TO grading_app
            USING (
                current_setting('app.user_type', true) = 'teacher'
                AND teacher_id = current_setting('app.user_id', true)::uuid
            );
        """,
        """
        CREATE POLICY student_assignment_for_teacher ON student_assignment FOR ALL TO grading_app
            USING (
                current_setting('app.user_type', true) = 'teacher'
                AND EXISTS (
                    SELECT 1 FROM teacher_assignment ta
                    WHERE ta.assignment_id = student_assignment.assignment_id
                      AND ta.teacher_id = current_setting('app.user_id', true)::uuid
                )
            );
        """,
        """
        CREATE POLICY student_assignment_self ON student_assignment FOR SELECT TO grading_app
            USING (
                current_setting('app.user_type', true) = 'student'
                AND cognito_sub = current_setting('app.user_id', true)
            );
        """,
    ]
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    statements = [
        "DROP TABLE IF EXISTS student_assignment;",
        "DROP TABLE IF EXISTS teacher_assignment;",
        "DROP TABLE IF EXISTS assignment;",
        "DROP TABLE IF EXISTS student;",
        "DROP TABLE IF EXISTS teacher;",
    ]
    for statement in statements:
        op.execute(statement)
