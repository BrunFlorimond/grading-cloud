# grading-cloud - WIP Only Slice 1 implemented

A cloud-native AI-powered grading pipeline built on AWS, designed to automate the correction, harmonization, and reporting of student work at scale. Demonstrates domain-driven design, hexagonal architecture, event-driven async processing, and infrastructure as code — end to end.

---

## The Problem

Correcting a class set of student spreadsheets with an AI model is straightforward to script locally. Doing it in a way that is reliable, scalable, auditable, and accessible to both teachers and students requires a different architecture entirely.

This system handles the full lifecycle:

1. Students and teachers upload spreadsheets (.xlsx, .ods, .numbers)
2. An AI model (Claude) corrects each copy against a rubric and a reference correction
3. A second AI pass detects and reconciles grading inconsistencies across the class
4. Individual PDF reports are generated per student, with cohort statistics and a grade distribution chart
5. Teachers and students access results through a role-scoped API

---

## Architecture

```
Teacher/Student
      │ HTTPS + JWT (Cognito)
      ▼
Application Load Balancer
      │
      ▼
┌─────────────────────────────────┐
│  exam-api  (Fargate / FastAPI)  │◄─── pipeline-events SQS ◄──────────────┐
│  - Exam & student management    │                                          │
│  - Pipeline orchestration       │──► spreadsheet-conversion SQS           │
│  - Async SQS event consumer     │──► pdf-generation SQS                   │
│  - Pre-signed S3 URLs           │──► EventBridge Scheduler (per batch)    │
└─────────────────────────────────┘                                          │
      │                                                                       │
      ├── S3 (all files) ──────────────────────────────────────────────────  │
      └── PostgreSQL / RDS (exam data, RLS) ───────────────────────────────  │
                                                                              │
spreadsheet-conversion SQS                                                    │
      │                                                                       │
      ▼                                                                       │
spreadsheet-converter Lambda (×N parallel)                                    │
  xlsx / ods / numbers → structured JSON → S3                                 │
  PostgreSQL update → pipeline-events SQS ───────────────────────────────►───┘
                                                                              │
EventBridge Scheduler (every 5 min, one rule per active batch)                │
      │                                                                       │
      ▼                                                                       │
batch-poller Lambda                                                           │
  Anthropic API: retrieve batch status                                        │
  if ended → results to S3 → PostgreSQL update → pipeline-events SQS ──────►─┘
                                                                              │
pdf-generation SQS                                                            │
      │                                                                       │
      ▼                                                                       │
pdf-generator Lambda (×N parallel)                                            │
  Jinja2 HTML + cohort stats + matplotlib chart → WeasyPrint → PDF → S3      │
  PostgreSQL update → pipeline-events SQS ──────────────────────────────────►┘
```

### Pipeline Phases

| Phase | Trigger | Processing | Output |
|---|---|---|---|
| **1. Ingestion** | Teacher starts pipeline | spreadsheet-converter Lambda (parallel) | `student_json` per student in S3 |
| **2. Correction** | All students converted | Fargate → Anthropic Batch (one request per student) → batch-poller Lambda | `notation_json` per student in S3 |
| **3. Harmonization** | Correction batch complete | Fargate → Anthropic Batch (per niveau-2 packet) → batch-poller Lambda → Fargate applies fixes | Corrected `notation_json` + `cohort_stats.json` in S3 |
| **4. PDF generation** | Harmonization complete | pdf-generator Lambda (parallel) | `{student_id}.pdf` per student in S3 |
| **5. Notification** | All PDFs ready | Fargate → SES | Email to teacher + per-student email |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| API framework | FastAPI |
| Data validation | Pydantic v2 (strict typed models, `extra="forbid"`) |
| ORM / async DB | SQLAlchemy 2.0 async + asyncpg |
| AI | Anthropic Claude — Batch API (correction, harmonization), synchronous API (rubric generation) |
| Compute | AWS Fargate (API + orchestration), AWS Lambda (conversion, polling, PDF) |
| Storage | Amazon S3 (all files), Amazon RDS PostgreSQL 16 (exam data, Row-Level Security) |
| Messaging | Amazon SQS (3 queues + DLQs) |
| Scheduling | Amazon EventBridge Scheduler (dynamic rules per active batch) |
| Auth | Amazon Cognito (teacher / student / admin groups, JWT) |
| PDF generation | WeasyPrint + Jinja2 + matplotlib (replaces LaTeX — no TeX dependency) |
| Infrastructure | AWS CDK (Python) |
| CI/CD | GitHub Actions (OIDC, no long-lived keys) |
| Dependency management | uv workspaces |

### Teacher: exam config upload API

Config files are uploaded **directly to S3** using **presigned POST** (multipart form), not presigned PUT — see [`services/exam-api/docs/exam-config-upload.md`](services/exam-api/docs/exam-config-upload.md) for the contract and **frontend integration** (`grading-cloud-web`).

---

## Design Principles

### Domain-Driven Design

The core domain is **exam correction**: exams, students, correction batches, grading rubrics, and notation payloads are first-class domain objects with explicit status machines. Business logic lives in the domain layer; AWS services are infrastructure adapters behind port interfaces.

### Hexagonal Architecture

Every service (Fargate app and each Lambda) follows the same layering:

```
API / Handler          thin — parse input, call use case, serialize output
Application            use cases orchestrate domain objects, call ports
Domain                 pure Python — entities, value objects, domain errors
Ports                  ABCs: ExamCreationRepositoryPort, ExamDetailRepositoryPort,
                              StudentEnrollmentRepositoryPort, StudentScopeRepositoryPort,
                              ExamOwnershipPort, ExamConfigRepositoryPort,
                              StudentInviteServicePort, JwtVerifierPort,
                              FileStoragePort, AIBatchPort, MessagePublisherPort
Infrastructure         AWS adapters implementing each port
                       PostgresAssignmentRepository (exam CRUD + config + ownership)
                       PostgresExamDetailRepository (read-model queries)
                       PostgresStudentEnrollmentRepository (roster + scope)
                       S3ExamConfigStorage, CognitoSesStudentInviteAdapter,
                       CognitoJwtVerifier
```

The domain layer has zero AWS imports. All four services share it via the `grading_shared` workspace package.

### Event-Driven Pipeline

The pipeline advances through a `pipeline-events` SQS queue consumed by a background worker in the Fargate app. No service polls another service over HTTP. State transitions are persisted to PostgreSQL before publishing an event, making every step idempotent and recoverable.

### Why EventBridge Scheduler — not a polling Lambda loop

Anthropic Batch jobs can take up to 24 hours. Lambda's maximum timeout is 15 minutes. Rather than a blocking poller or a timed loop, a dedicated EventBridge Scheduler rule is created per active batch (fires every 5 minutes) and deleted when the batch ends. The `batch-poller` Lambda is a plain handler with no HTTP framework — it checks status, stores results in S3, and publishes a single pipeline event.

### Why WeasyPrint — not LaTeX

A full TeX Live installation weighs 3–4 GB — impractical for a Lambda container image. The PDF generator Lambda uses WeasyPrint (HTML → PDF) with a Jinja2 template and matplotlib (Agg backend) for the grade distribution histogram, resulting in a ~150 MB container image with no system-level TeX dependency.

---

## Access Control

Three roles, enforced by Cognito groups and FastAPI dependencies:

| Role | Can do |
|---|---|
| **Admin** | Register teachers (invite to Cognito) |
| **Teacher** | Create exams, upload config + spreadsheets, manage student roster, trigger pipeline, view all results for their exams, download all PDFs |
| **Student** | Upload their own spreadsheet, view their own grade breakdown, download their own PDF |

Access is enforced at two layers:

1. **FastAPI dependencies** — `require_teacher`, `require_student`, `require_admin` reject JWTs missing the expected `cognito:groups` value; `require_own_data` blocks students from accessing another student's resource.
2. **PostgreSQL Row-Level Security** — every transaction runs with `SET LOCAL app.user_id` and `SET LOCAL app.user_type` GUCs injected by `session_with_rls`. RLS policies on each table enforce row visibility at the database level, so no application-level filter can accidentally leak data.

---

## Data Model (PostgreSQL)

The `exam-api` uses RDS PostgreSQL 16 with Row-Level Security. Core tables:

| Table | Key columns | RLS policy |
|---|---|---|
| `assignments` | `id` (UUID PK), `created_by` (teacher sub), `title`, `status`, `config_*` (S3 keys) | Teacher sees only rows where `created_by = app.user_id` |
| `teacher_assignments` | `teacher_id`, `assignment_id` (FK) | Teacher edge — lists exams belonging to a teacher |
| `student_assignments` | `assignment_id` (FK), `student_id`, `nom`, `prenom`, `classe`, `email`, `submission_status` | Teacher sees all rows for their exams; student sees only their own row |

Every request opens a transaction with `SET LOCAL app.user_id = <sub>` and `SET LOCAL app.user_type = teacher|student` via the `session_with_rls` context manager. All repository queries run inside that transaction — no application-level row filter is needed.

---

## Rubric Builder

Teachers can create grading rubrics independently of any exam:

1. Upload the assignment and reference correction files
2. Call `POST /rubrics/{rubric_id}/generate` — Fargate calls Claude synchronously; Claude infers the 3-level criterion hierarchy (niveau 1 → 2 → 3) and distributes points across leaves
3. Review and amend the generated structure via `PUT /rubrics/{rubric_id}/structure`
4. Save a named version snapshot
5. Attach the rubric to an exam — this generates the `grille_notation.json` config file automatically

No Anthropic Batch is used here: the synchronous API call returns in ~10–30 seconds, which is acceptable for an interactive rubric-generation flow.

---

## Project Structure

```
grading-cloud/
├── shared/                        # grading_shared — domain models, ports, events
│   └── grading_shared/
│       ├── domain/                # NotationPayload, Exam, StudentSubmission, PipelineEvent
│       └── ports/                 # ABCs: FileStoragePort, ExamRepositoryPort, AIBatchPort, etc.
│
├── services/
│   ├── exam-api/                  # Fargate FastAPI app
│   │   └── exam_api/
│   │       ├── api/               # FastAPI routers + RBAC dependencies
│   │       ├── application/       # Use cases (CreateExam, InviteStudent, GetExamDetail, …)
│   │       ├── domain/            # Domain errors, student model
│   │       ├── ports/             # Repository and service port interfaces
│   │       └── infrastructure/    # PostgreSQL (SQLAlchemy + asyncpg), S3, Cognito adapters
│   │                              # session_with_rls — injects RLS GUCs per transaction
│   │
│   ├── spreadsheet-converter/     # Lambda — xlsx/ods/numbers → JSON
│   ├── batch-poller/              # Lambda — Anthropic batch status check
│   └── pdf-generator/             # Lambda — Jinja2 + WeasyPrint → PDF
│
├── infra/                         # CDK Python
│   └── stacks/
│       ├── auth_stack.py          # Cognito User Pool (teacher / student / admin groups)
│       ├── storage_stack.py       # S3 files bucket
│       ├── database_stack.py      # VPC, RDS PostgreSQL 16, security groups, Secrets Manager
│       └── compute_stack.py       # ECR, Fargate service, ALB, SQS, task IAM role
│
└── templates/
    └── report_template.html       # Jinja2 HTML report template (stored in S3 at deploy time)
```

---

## Roadmap

Backend and frontend are developed in parallel vertical slices — each slice delivers a demoable feature end to end. Backend issues are tracked here; frontend issues live in [grading-cloud-web](https://github.com/BrunFlorimond/grading-cloud-web). Both feed into the same project board.

| Slice | Backend scope | Demo at the end |
|---|---|---|
| [Slice 1 – Exam Setup](https://github.com/BrunFlorimond/grading-cloud/milestone/5) | CDK skeleton, shared package, CI/CD, Cognito, RBAC, exam CRUD | Create an exam, configure it, add students — full auth + API flow |
| [Slice 2 – Spreadsheet Ingestion](https://github.com/BrunFlorimond/grading-cloud/milestone/6) | SQS, converter Lambda, upload/confirm endpoints | Upload a spreadsheet, see it converted to JSON |
| [Slice 3 – AI Correction](https://github.com/BrunFlorimond/grading-cloud/milestone/7) | Pipeline trigger, event consumer, Anthropic Batch correction, batch poller | Trigger grading, watch per-student corrections appear |
| [Slice 4 – Full Pipeline](https://github.com/BrunFlorimond/grading-cloud/milestone/8) | Harmonization, cohort stats, PDF Lambda, download endpoints | Spreadsheet in → graded PDF out, downloadable |
| [Slice 5 – Student Portal](https://github.com/BrunFlorimond/grading-cloud/milestone/9) | Student-scoped endpoints, SES notifications | Student logs in, views their grade, downloads their PDF |
| [Slice 6 – Rubric Builder](https://github.com/BrunFlorimond/grading-cloud/milestone/10) | xlsx upload, conversion, Claude rubric generation, versioning, exam attachment | Generate a rubric from an xlsx assignment, attach it to an exam |

Full board: [Grading Cloud – Roadmap](https://github.com/users/BrunFlorimond/projects/2)

