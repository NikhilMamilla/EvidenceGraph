# Infrastructure — Docker

The primary Docker Compose configuration lives at the repository root:
`../../docker-compose.yml`

This directory is reserved for environment-specific overrides and future
infrastructure-as-code additions (e.g. production compose overrides,
Kubernetes manifests, Terraform configurations).

## Phase 1 services

| Service    | Image                  | Port  |
|------------|------------------------|-------|
| postgres   | postgres:16.3-alpine   | 5432  |
| redis      | redis:7.2-alpine       | 6379  |
| backend    | (local build)          | 8000  |
| frontend   | (local build)          | 5173  |

## Volumes

| Volume          | Purpose                              |
|-----------------|--------------------------------------|
| postgres_data   | PostgreSQL data directory persistence |
| redis_data      | Redis RDB snapshot persistence        |
