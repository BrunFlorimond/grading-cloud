# grading-cloud

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
API Gateway (HTTP API)
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
      └── DynamoDB (single table) ─────────────────────────────────────────  │
                                                                              │
spreadsheet-conversion SQS                                                    │
      │                                                                       │
      ▼                                                                       │
spreadsheet-converter Lambda (×N parallel)                                    │
  xlsx / ods / numbers → structured JSON → S3                                 │
  DynamoDB update → pipeline-events SQS ──────────────────────────────────►──┘
                                                                              │
EventBridge Scheduler (every 5 min, one rule per active batch)                │
      │                                                                       │
      ▼                                                                       │
batch-poller Lambda                                                           │
  Anthropic API: retrieve batch status                                        │
  if ended → results to S3 → DynamoDB update → pipeline-events SQS ────────►─┘
                                                                              │
pdf-generation SQS                                                            │
      │                                                                       │
      ▼                                                                       │
pdf-generator Lambda (×N parallel)                                            │
  Jinja2 HTML + cohort stats + matplotlib chart → WeasyPrint → PDF → S3      │
  DynamoDB update → pipeline-events SQS ────────────────────────────────────►┘
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
| AI | Anthropic Claude — Batch API (correction, harmonization), synchronous API (rubric generation) |
| Compute | AWS Fargate (API + orchestration), AWS Lambda (conversion, polling, PDF) |
| Storage | Amazon S3 (all files), Amazon DynamoDB (single-table, denormalized) |
| Messaging | Amazon SQS (3 queues + DLQs) |
| Scheduling | Amazon EventBridge Scheduler (dynamic rules per active batch) |
| Auth | Amazon Cognito (teacher / student groups, JWT) |
| PDF generation | WeasyPrint + Jinja2 + matplotlib (replaces LaTeX — no TeX dependency) |
| Infrastructure | AWS CDK (Python) |
| CI/CD | GitHub Actions (OIDC, no long-lived keys) |
| Dependency management | uv workspaces |

---

## Design Principles

### Domain-Driven Design

The core domain is **exam correction**: exams, students, correction batches, grading rubrics, and notation payloads are first-class domain objects with explicit status machines. Business logic lives in the domain layer; AWS services are infrastructure adapters behind port interfaces.

### Hexagonal Architecture

Every service (Fargate app and each Lambda) follows the same layering:

```
API / Handler          thin — parse input, call use case, serialize output
Application            use cases orchestrate domain objects, call ports
Domain                 pure Python — entities, value objects, domain services
                       Ports: FileStoragePort, ExamRepositoryPort,
                              AIBatchPort, MessagePublisherPort, SchedulerPort
Infrastructure         AWS adapters implementing each port
                       S3FileStorage, DynamoDBExamRepository,
                       AnthropicBatchAdapter, SQSMessagePublisher,
                       EventBridgeSchedulerAdapter
```

The domain layer has zero AWS imports. All four services share it via the `grading_shared` workspace package.

### Event-Driven Pipeline

The pipeline advances through a `pipeline-events` SQS queue consumed by a background worker in the Fargate app. No service polls another service over HTTP. State transitions are persisted to DynamoDB before publishing an event, making every step idempotent and recoverable.

### Why EventBridge Scheduler — not a polling Lambda loop

Anthropic Batch jobs can take up to 24 hours. Lambda's maximum timeout is 15 minutes. Rather than a blocking poller or a timed loop, a dedicated EventBridge Scheduler rule is created per active batch (fires every 5 minutes) and deleted when the batch ends. The `batch-poller` Lambda is a plain handler with no HTTP framework — it checks status, stores results in S3, and publishes a single pipeline event.

### Why WeasyPrint — not LaTeX

The original local script used LaTeX + latexmk for PDF generation. A full TeX Live installation is 3–4 GB — impractical for a Lambda container. The PDF generator Lambda uses WeasyPrint (HTML → PDF) with a Jinja2 template and matplotlib (Agg backend) for the grade distribution histogram, resulting in a ~150 MB container image with no system-level TeX dependency.

---

## Access Control

Two roles, enforced by Cognito groups and FastAPI dependencies:

| Role | Can do |
|---|---|
| **Teacher** | Create exams, upload config + spreadsheets, manage student roster, trigger pipeline, view all results for their exams, download all PDFs |
| **Student** | Upload their own spreadsheet, view their own grade breakdown, download their own PDF |

Students are scoped at the JWT level: the Cognito token carries `custom:role=student` and `custom:exam_id`. Every student-facing endpoint validates that the requested resource matches the token's subject (`sub`).

---

## DynamoDB Single-Table Design

All entities share one table (`grading-table`):

```
PK                         SK                                Attributes
────────────────────────────────────────────────────────────────────────────
TEACHER#{teacher_id}       EXAM#{exam_id}                    title, status, created_at
EXAM#{exam_id}             METADATA                          config S3 keys, status, teacher_id
EXAM#{exam_id}             STUDENT#{student_id}              name, class, submission_status, S3 keys
EXAM#{exam_id}             BATCH#CORRECTION#{batch_id}       status, created_at, ended_at, scheduler_rule
EXAM#{exam_id}             BATCH#HARMONIZATION#{batch_id}    status, created_at, ended_at, scheduler_rule
TEACHER#{teacher_id}       RUBRIC#{rubric_id}                name, structure, status, version count
RUBRIC#{rubric_id}         VERSION#{label}                   immutable structure snapshot
```

**GSI-1** `BatchIndex` — PK: `BATCH#{batch_id}` — lets the batch-poller Lambda look up the parent exam from a bare batch ID.

**GSI-2** `TeacherExams` — PK: `TEACHER#{teacher_id}`, SK: `created_at` — lists a teacher's exams chronologically.

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
│       └── ports/                 # ABCs: FileStoragePort, AIBatchPort, etc.
│
├── services/
│   ├── exam-api/                  # Fargate FastAPI app
│   │   └── src/exam_api/
│   │       ├── api/               # FastAPI routers (exams, students, rubrics, auth)
│   │       ├── application/       # Use cases (CreateExam, StartPipeline, ProcessEvent, …)
│   │       ├── domain/            # HarmonizationService, CohortStatsService, pipeline consumer
│   │       └── infrastructure/    # DynamoDB, S3, SQS, Anthropic, EventBridge adapters
│   │
│   ├── spreadsheet-converter/     # Lambda — xlsx/ods/numbers → JSON
│   ├── batch-poller/              # Lambda — Anthropic batch status check
│   └── pdf-generator/             # Lambda — Jinja2 + WeasyPrint → PDF
│
├── infra/                         # CDK Python
│   └── stacks/
│       ├── auth_stack.py          # Cognito User Pool + API Gateway
│       ├── storage_stack.py       # S3 + DynamoDB
│       ├── messaging_stack.py     # SQS queues + DLQs
│       ├── lambda_stack.py        # Lambda functions + EventBridge Scheduler group
│       └── compute_stack.py       # ECR + Fargate + ALB
│
└── templates/
    └── report_template.html       # Jinja2 HTML report template (stored in S3 at deploy time)
```

---

## Roadmap

Development is tracked in [GitHub Issues](https://github.com/BrunFlorimond/grading-cloud/issues) organized across four milestones:

| Milestone | Scope |
|---|---|
| [Phase 1 – Foundation & Auth](https://github.com/BrunFlorimond/grading-cloud/milestone/1) | CDK stacks, shared package, CI/CD, Cognito, RBAC |
| [Phase 2 – Core Pipeline](https://github.com/BrunFlorimond/grading-cloud/milestone/2) | Exam management, ingestion, AI correction, harmonization, PDF generation |
| [Phase 3 – Student Portal](https://github.com/BrunFlorimond/grading-cloud/milestone/3) | Student dashboard, grade view, PDF download, email notifications |
| [Phase 4 – Rubric Builder](https://github.com/BrunFlorimond/grading-cloud/milestone/4) | AI-assisted rubric generation, versioning, exam attachment |

Full board: [Grading Cloud – Roadmap](https://github.com/users/BrunFlorimond/projects/2)

