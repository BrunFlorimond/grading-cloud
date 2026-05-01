# Audit — migration async (issue #59)

## Légende

| Statut | Signification |
|--------|--------------|
| `ASYNC_OK` | Déjà correctement async, rien à faire |
| `MIGRATABLE` | Code sync (use case, adapter) remplaçable par `aiobotocore` ou équivalent |
| `BLOCKED` | Sync pour une raison légitime |

---

## Endpoints

| Endpoint | Fichier | Statut | Motif |
|----------|---------|--------|-------|
| `POST /auth/register` | `api/auth_router.py` | `MIGRATABLE` | `run_in_threadpool` sur use case sync ; `CognitoAuthAdapter` utilise `boto3` synchrone |
| `POST /auth/login` | `api/auth_router.py` | `MIGRATABLE` | `run_in_threadpool` sur use case sync ; `CognitoAuthAdapter` utilise `boto3` synchrone |
| `POST /exams/{exam_id}/students/{student_id}/invite` | `api/invite_router.py` | `MIGRATABLE` | Port déjà async, mais l'adapter enveloppe du `boto3` sync dans `asyncio.to_thread` |
| `GET /exams/{exam_id}/students/{student_id}/scope` | `api/invite_router.py` | `MIGRATABLE` | Port déjà async, mais le repository enveloppe du `boto3` sync dans `asyncio.to_thread` |

---

## Adapters / composants transverses

| Composant | Fichier | Statut | Motif |
|-----------|---------|--------|-------|
| `CognitoAuthAdapter` | `infrastructure/cognito_auth_adapter.py` | `MIGRATABLE` | `boto3.client("cognito-idp")` ; toutes les méthodes sont sync → remplacer par `aiobotocore` |
| `CognitoJwtVerifier` | `infrastructure/cognito_jwt_verifier.py` | `MIGRATABLE` | `httpx.get()` synchrone pour récupérer le JWKS → remplacer par `httpx.AsyncClient` |
| `CognitoSesStudentInviteAdapter` | `infrastructure/student_invite_adapter.py` | `MIGRATABLE` | `boto3` sync enveloppé dans `asyncio.to_thread` → remplacer par `aiobotocore` |
| `DynamoDbInviteRepository` | `infrastructure/dynamodb_invite_repository.py` | `MIGRATABLE` | `boto3.resource("dynamodb")` sync enveloppé dans `asyncio.to_thread` → remplacer par `aiobotocore` |

---

## Ports concernés

| Port | Fichier | Action requise |
|------|---------|---------------|
| `AuthServicePort` | `ports/auth_service_port.py` | Passer `register_teacher` et `login_teacher` en `async def` |
| `JwtVerifierPort` | `ports/jwt_verifier_port.py` | Passer `decode_and_verify_token` en `async def` |
| `StudentInviteServicePort` | `ports/student_invite_port.py` | Déjà `async def` — aucun changement |
| `StudentScopeRepositoryPort` | `ports/student_scope_repository_port.py` | Déjà `async def` — aucun changement |

---

## Use cases concernés

| Use case | Fichier | Action requise |
|----------|---------|---------------|
| `RegisterTeacherUseCase` | `application/register_teacher.py` | Passer `execute` en `async def` |
| `LoginTeacherUseCase` | `application/login_teacher.py` | Passer `execute` en `async def` |
| `InviteStudentUseCase` | `application/invite_student.py` | Déjà `async def` — retirer `asyncio.to_thread` quand l'adapter sera natif async |

---

## Risques identifiés

- `aiobotocore` et `boto3` ne peuvent pas partager le même client dans le même event loop.
  La migration des adapters doit être faite de façon coordonnée (pas endpoint par endpoint).
- `CognitoJwtVerifier` est appelé dans des dépendances FastAPI synchrones (`get_current_teacher`,
  `get_current_student`). Passer à `async def` nécessite de mettre à jour ces dépendances.
- `DynamoDbInviteRepository.get_exam()` est appelé via `asyncio.to_thread` dans le use case
  `InviteStudentUseCase` (ligne 69 de `invite_student.py`). Ce contournement disparaît quand le
  repository sera natif async.

---

## Ordre de migration recommandé

1. `ports/auth_service_port.py` + `ports/jwt_verifier_port.py` → async signatures
2. `application/login_teacher.py` + `application/register_teacher.py` → async execute
3. `infrastructure/cognito_auth_adapter.py` → aiobotocore
4. `infrastructure/cognito_jwt_verifier.py` → httpx.AsyncClient
5. `infrastructure/student_invite_adapter.py` → aiobotocore (retirer asyncio.to_thread)
6. `infrastructure/dynamodb_invite_repository.py` → aiobotocore (retirer asyncio.to_thread)
7. `api/auth_router.py` → retirer run_in_threadpool
