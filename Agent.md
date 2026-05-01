# Agent.md — grading-cloud (Cursor Cloud Agents)

## Environnement
Python 3.12. Gestionnaire de paquets : uv (workspaces).

## Commandes de build et test
```bash
# Installer les dépendances
uv sync

# Tests d'un service
cd services/exam-api && uv run pytest
cd services/spreadsheet-converter && uv run pytest
cd services/pdf-generator && uv run pytest

# Vérifier le typage
uv run mypy services/exam-api/src

# Linter
uv run ruff check .
uv run ruff format --check .

# CDK synth (vérification infra sans déploiement)
cd infra && uv run cdk synth
```

## Ce que fait un Cloud Agent (mode autonome)
Un Cloud Agent est **monolithique** — il implémente ET teste dans la même session.
Ordre obligatoire : domain → ports → application → infrastructure → api → tests.
Lance `uv run pytest` avant d'ouvrir la draft PR.

(Les agents Claude Code locaux — backend-dev, test-writer, reviewer — sont
spécialisés et s'appellent en séquence. Cloud Agents font tout d'un coup.)

## Conventions obligatoires
- Architecture hexagonale : domain/ = Python pur, zéro import AWS
- Pydantic v2 strict sur tous les modèles
- Branche : feature/issue-{N}-{slug}
- Ouvre une draft PR quand la tâche est terminée

## Structure des services
```
services/{service}/src/{service}/
├── api/            # Handlers FastAPI (thin layer)
├── application/    # Use cases (orchestration)
├── domain/         # Entités, value objects, ports (ABCs)
└── infrastructure/ # Adaptateurs AWS
```

## Ce que tu ne fais pas
- Modifier infra/ sans instruction explicite
- Appeler l'API Anthropic ou AWS réellement dans les tests
- Committer sur main
