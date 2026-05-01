# Audit — migration async (issue #59)

État au merge : migration **terminée** pour les endpoints et adapters listés ci‑dessous (aiobotocore + `httpx.AsyncClient`, dépendances FastAPI JWT en `async`).

## Légende

| Statut | Signification |
|--------|--------------|
| `ASYNC_OK` | Async natif (pas d’appel bloquant dans la boucle d’événements) |
| `MIGRATABLE` | (historique) était synchrones |
| `BLOCKED` | Sync pour une raison légitime |

---

## Endpoints

| Endpoint | Fichier | Statut | Motif |
|----------|---------|--------|-------|
| `POST /auth/register` | `api/auth_router.py` | `ASYNC_OK` | Use case + `CognitoAuthAdapter` async |
| `POST /auth/login` | `api/auth_router.py` | `ASYNC_OK` | Idem |
| `POST /exams/{exam_id}/students/{student_id}/invite` | `api/invite_router.py` | `ASYNC_OK` | `CognitoSesStudentInviteAdapter` aiobotocore |
| `GET /exams/{exam_id}/students/{student_id}/scope` | `api/invite_router.py` | `ASYNC_OK` | `DynamoDbInviteRepository` aiobotocore ; JWT `await` |

---

## Adapters / composants transverses

| Composant | Fichier | Statut | Motif |
|-----------|---------|--------|-------|
| `CognitoAuthAdapter` | `infrastructure/cognito_auth_adapter.py` | `ASYNC_OK` | `aiobotocore` |
| `CognitoJwtVerifier` | `infrastructure/cognito_jwt_verifier.py` | `ASYNC_OK` | `httpx.AsyncClient` + `asyncio.Lock` |
| `CognitoSesStudentInviteAdapter` | `infrastructure/student_invite_adapter.py` | `ASYNC_OK` | `aiobotocore` cognito + SES |
| `DynamoDbInviteRepository` | `infrastructure/dynamodb_invite_repository.py` | `ASYNC_OK` | `aiobotocore` DynamoDB low-level |

---

## Ports concernés

| Port | Fichier | Action |
|------|---------|--------|
| `AuthServicePort` | `ports/auth_service_port.py` | `register_teacher` / `login_teacher` → `async def` |
| `JwtVerifierPort` | `ports/jwt_verifier_port.py` | `decode_and_verify_token` → `async def` |
| `ExamRepositoryPort` | `grading_shared/ports/__init__.py` | `get_exam` / `save_exam` / `save_notation_payload` → `async def` |
| `StudentInviteServicePort` | `ports/student_invite_port.py` | Inchangé (déjà async) |
| `StudentScopeRepositoryPort` | `ports/student_scope_repository_port.py` | Inchangé (déjà async) |

---

## Risques (mitigations)

- **aiobotocore vs boto3** : aucun client boto3 sync dans les chemins migrés ; les payloads DynamoDB avec flottants sont convertis en `Decimal` avant sérialisation.
- **JWT** : `get_current_teacher` / `get_current_student` sont `async` et `await` le port JWT.
