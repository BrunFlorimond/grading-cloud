# Exam configuration upload (teacher)

Specification for **Slice 1 — Exam Setup**: uploading the four JSON/text files that describe an exam configuration (`devoir.json`, `correction.json`, `prompt.txt`, `grille_notation.json`).

## Why presigned POST (not PUT)

The API returns **S3 presigned POST** payloads (`url` + `fields`), not a single presigned PUT URL. Reasons:

1. **Policy constraints** — The POST policy can enforce `content-length-range` (max ~10 MiB per file) so clients cannot upload arbitrarily large objects.
2. **Security / cost** — Same as other browser uploads: short-lived credentials scoped to a key prefix.

Clients must upload with **multipart/form-data** using the returned `fields` plus the file under the field name `file` (see AWS examples). A plain `PUT` to `url` **will not work** for this flow.

## Endpoints

### `POST /exams/{exam_id}/config/upload-urls`

- **Auth**: Bearer JWT (teacher).
- **Response** `200`:

```json
{
  "upload_urls": {
    "devoir.json": {
      "url": "https://bucket.s3.region.amazonaws.com/",
      "fields": {
        "key": "exams/{exam_id}/config/devoir.json",
        "policy": "...",
        "x-amz-algorithm": "...",
        "x-amz-credential": "...",
        "x-amz-date": "...",
        "x-amz-signature": "...",
        "x-amz-security-token": "..."
      }
    },
    "correction.json": { "url": "...", "fields": { ... } },
    "prompt.txt": { "url": "...", "fields": { ... } },
    "grille_notation.json": { "url": "...", "fields": { ... } }
  }
}
```

- **Errors**: `401`, `404` (exam missing), `403` (not owner).

### `POST /exams/{exam_id}/config/confirm`

- **Auth**: Bearer JWT (teacher).
- **Body**: none.
- **Response** `200`:

```json
{ "exam_id": "<uuid>", "status": "CONFIGURED" }
```

- **Errors**: `401`, `404`, `403`, `422` (missing files, invalid JSON for `.json` files, wrong exam status, or concurrent status change).

## Frontend story (grading-cloud-web)

1. After creating an exam (`POST /exams`), call **`upload-urls`** with the teacher token.
2. For each entry in `upload_urls`:
   - Build a `FormData`.
   - Append every key/value from `fields` **exactly** as returned (strings).
   - Append the file bytes as **`file`** (S3 POST convention for browser uploads).
   - `POST` to `url` with `fetch(url, { method: "POST", body: formData })` — **do not** set `Content-Type` manually (browser sets multipart boundary).
3. When all four uploads succeed, call **`confirm`**. On success, exam status becomes **CONFIGURED** (see `GET /exams`: special labels `CREATED` / `CONFIGURED`; other statuses use lowercase enum **values** e.g. `ready`, `ingestion_running`).

## File layout in S3

Object keys:

`exams/{exam_id}/config/devoir.json`  
`exams/{exam_id}/config/correction.json`  
`exams/{exam_id}/config/prompt.txt`  
`exams/{exam_id}/config/grille_notation.json`

## Related environment variables

- **`EXAM_CONFIG_BUCKET`** — Bucket used for presigned POST generation (exam-api task definition).
