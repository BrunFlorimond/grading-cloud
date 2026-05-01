# grading-cloud — CLAUDE.md

## Identité du projet
Pipeline de correction automatique de copies d'étudiants.
Stack : Python 3.12 · FastAPI · AWS (Fargate + Lambda + DynamoDB + S3 + SQS)
· Anthropic Batch API · CDK Python · uv workspaces

## Architecture — règles absolues
- Architecture hexagonale stricte. ZERO import AWS dans domain/ ou ports/.
- `grading_shared` est le package partagé (uv workspace). Toute modification
  des modèles domain impacte les 4 services — vérifie la rétrocompat.
- Single-table DynamoDB : PK/SK explicites, pas de scan full-table.
- Pydantic v2 strict partout : `model_config = ConfigDict(extra="forbid", strict=True)`.
- SQS : publier l'événement pipeline APRÈS la mise à jour DynamoDB, jamais avant.
- EventBridge Scheduler : une règle par batch actif, supprimée quand le batch se termine.

## Agents Claude Code disponibles
- `backend-dev`      — implémentation features (domain → application → infrastructure → api)
- `test-writer`      — tests pytest après implémentation
- `reviewer`         — review constructive + adversariale sur les fichiers produits
- `shared-package`   — modifications grading_shared (impact cross-services)
- `infra-dev`        — modifications CDK Python dans infra/

## Stack de tests
- Framework : pytest + pytest-asyncio
- Mocks : `unittest.mock` ou `moto` pour AWS — jamais d'appels réels en test
- Coverage cible : 80 % sur domain/ et application/, 60 % sur infrastructure/
- Commande : `uv run pytest` depuis la racine du service concerné

## Conventions de commit et branches
- Branche : `feature/issue-{N}-{slug}` (ex: `feature/issue-7-create-exam`)
- Commit : `{type}(#{N}): {description}` (ex: `feat(#7): add CreateExam use case`)
- Types : feat | fix | test | refactor | infra | docs
- Ne jamais committer directement sur main

## Services et leur rôle
- `exam-api` (Fargate)              : API FastAPI + orchestration pipeline + consommateur SQS
- `spreadsheet-converter` (Lambda)  : xlsx/ods/numbers → JSON structuré
- `batch-poller` (Lambda)           : polling statut batch Anthropic → résultats S3
- `pdf-generator` (Lambda)          : Jinja2 + WeasyPrint → PDF

## Fichiers à ne jamais modifier sans instruction explicite
- `infra/`                       — utilise l'agent infra-dev
- `shared/grading_shared/domain/` — utilise l'agent shared-package
- `.github/workflows/`           — CI/CD

## Context GitHub Actions
- Crée toujours une branche, jamais de commit sur main
- Formate les commentaires en GitHub-flavoured Markdown
- Les secrets AWS ne sont pas disponibles — ne tente pas d'appels AWS réels
