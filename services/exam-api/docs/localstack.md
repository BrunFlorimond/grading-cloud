# exam-api with LocalStack (S3/SES/Secrets) + real Cognito

This setup runs:
- PostgreSQL in Docker
- AWS dependencies in LocalStack (`s3`, `ses`, `secretsmanager`)
- `exam-api` in Docker (same Dockerfile for local + AWS deployment image)
- Cognito remains real (AWS)

It is designed for local dev and CI robot jobs.

## 1) Start infra stack (PostgreSQL + LocalStack)

From `services/exam-api`:

```bash
docker compose -f docker-compose.localstack.yml up -d
```

Wait until LocalStack is ready, then copy generated environment values:

```bash
docker cp exam-api-localstack:/var/lib/localstack/localstack-exam-api.env .env.localstack
```

This command overwrites the placeholder `.env.localstack` committed in the repo.

Then fill these real Cognito values in `.env.localstack`:
- `COGNITO_USER_POOL_ID`
- `COGNITO_APP_CLIENT_ID`
- `COGNITO_ISSUER_URL`

The file also contains:
- `EXAM_CONFIG_BUCKET`
- local `DATABASE_URL`
- LocalStack endpoint vars for `s3` / `ses` / `secretsmanager`

## 2) Build/run DB migrations in container

```bash
docker compose -f docker-compose.localstack.yml --profile migrations run --rm exam-api-migrations
```

## 3) Start API container

```bash
docker compose -f docker-compose.localstack.yml up -d exam-api
```

API is then available at `http://localhost:8000`.

## 4) CI usage pattern

- Start infra (`postgres` + `localstack`)
- Copy generated `.env.localstack`
- Inject real Cognito vars in `.env.localstack` (or via CI secrets)
- Run `exam-api-migrations` container
- Start `exam-api` container
- Run API integration tests against `http://localhost:8000`

## 5) Notes and limitations

- Cognito flows depend on your real AWS environment (users/groups/password policies).
- `SES` in LocalStack is emulated (no real email delivery).
- If your test suite does not use config upload routes, `EXAM_CONFIG_BUCKET` is optional.
