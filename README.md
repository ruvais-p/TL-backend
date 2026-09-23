# Tella Django Backend

The Django API is the platform's source of truth. Moodle is an API client and presentation layer; academic authorization and business rules stay in Django services.

The maintained endpoint and payload reference is [docs/API.md](../docs/API.md). For step-by-step creation of every data segment, see [docs/DATA_ENTRY_GUIDE.md](../docs/DATA_ENTRY_GUIDE.md).

## Implemented architecture (Phases 1–4)

- `config/settings/base.py`: shared environment-driven configuration
- `config/settings/development.py`: local development settings
- `config/settings/production.py`: secure production defaults
- `accounts/models.py`: UUID custom user model using Django Groups and Permissions
- `accounts/services.py`: sensitive account operations and privilege-escalation safeguards
- `accounts/permissions.py`: reusable DRF group and permission classes
- `accounts/management/commands/setup_groups.py`: idempotent RBAC synchronization
- `curriculum/`: Programs, Courses, CourseVersions, Chapters, Subtopics, and LearningActivities
- `content/` and `media_library/`: structured learning content and storage-ready media metadata
- `students/`: cohorts, memberships, versioned enrollments, course assignments, and LMS mappings
- `progress/`: transactional activity progress with persisted subtopic, chapter, and course snapshots
- `assessments/`: reusable questions, learning checks, case studies, attempts, and server-side scoring
- `config/urls.py`: versioned, JSON-only REST endpoints under `/api/v1/`, with no HTML routes

The access-control groups are `SUPER_ADMIN`, `ADMIN`, `ACADEMIC_MANAGER`, `CONTENT_MANAGER`, `TEACHER`, and `STUDENT`. These are Django authentication Groups. Classroom cohorts use the separate `students.StudentGroup` model.

## Requirements and environment

Use Python 3.10+, PostgreSQL 15+, and the compatible dependency ranges in `requirements.txt`.

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set a strong `DJANGO_SECRET_KEY`, PostgreSQL credentials, allowed hosts, CORS origins, JWT lifetimes, and optional Redis/object-storage values in `.env`. Set `MATH_TUTOR_API_KEY` only in the backend secret store; never put it in Next.js variables or commit `.env`. Rotate the provider key before production rollout and restart backend instances after rotation.

## Database and initial access control

```bash
python manage.py migrate
python manage.py setup_groups
python manage.py createsuperuser
```

`setup_groups` is safe to run repeatedly. It resolves permissions by `app_label.codename`, never database IDs, and synchronizes each group's permissions.
The user created by `createsuperuser` can sign in directly to the Next.js staff workspace; Django does not expose an `/admin/` frontend.

Schedule `python manage.py purge_course_chat` at least daily. It deletes chat sessions, including their messages, whose last activity is older than `COURSE_CHAT_RETENTION_DAYS` (30 by default). Curriculum, enrollment, and progress records are unaffected.

Human course-support chat has a separate retention policy and cleanup command. Schedule `python manage.py purge_course_support_chat` at least daily after confirming `COURSE_SUPPORT_CHAT_RETENTION_DAYS`; use `--dry-run` during rollout. See [the course support operations guide](../docs/COURSE_SUPPORT_CHAT.md) for ASGI, WebSocket, Redis, privacy, log-redaction, rollout, and rollback requirements.

## Run and test

```bash
python manage.py check
daphne -b 0.0.0.0 -p 8000 config.asgi:application
pytest
```

The native Django test runner is also supported:

```bash
python manage.py test
```

## Run with Docker

Build and start the Django ASGI service, PostgreSQL, and Redis from this
directory:

```bash
docker compose up --build -d
docker compose ps
curl http://localhost:8000/api/v1/health/
```

The Compose stack runs database migrations and synchronizes authorization
groups before starting Daphne. PostgreSQL data, uploaded media, and private
documents are kept in named volumes. Redis is deliberately configured as a
transient transport.

Configuration can be supplied through shell variables or a `.env` file next
to `compose.yaml`. At minimum, replace `DJANGO_SECRET_KEY`,
`POSTGRES_PASSWORD`, and `MOODLE_SSO_SECRET` outside local development. Set
`DJANGO_SECURE_SSL_REDIRECT=true` only when TLS is terminated by a correctly
configured reverse proxy.

Useful operations:

```bash
docker compose logs -f backend
docker compose exec backend python manage.py createsuperuser
docker compose down
```

`docker compose down` preserves the named volumes. Add `--volumes` only when
you intentionally want to delete the local database and uploaded files.

## Authentication API

All public APIs are versioned under `/api/v1/`:

- `POST /api/v1/auth/login/` with `email` and `password`
- `POST /api/v1/auth/refresh/` with `refresh`
- `POST /api/v1/auth/logout/` with a Bearer access token and `refresh`
- `GET /api/v1/auth/me/` with a Bearer access token
- `GET`/`POST /api/v1/auth/users/` and `GET`/`PATCH /api/v1/auth/users/{id}/` for guarded staff account management
- `GET /api/v1/auth/groups/`; permission administrators may `PATCH /api/v1/auth/groups/{id}/permissions/`
- `GET /api/v1/auth/permissions/` for the permission-management catalog

Access tokens default to 15 minutes. Refresh tokens default to seven days, rotate on refresh, and are blacklisted after rotation or logout. `/auth/me/` returns Django Groups and effective permissions.

## Authorization design

API views perform authentication and coarse permission checks. Serializers validate input. Services enforce sensitive business rules and use transactions. Selectors own scoped reads. Teachers only see students connected through an assigned StudentGroup, and student content access requires an active, unexpired enrollment for the exact CourseVersion.

Normal administrators receive `manage_users` but not `manage_permissions`. The account service rejects assignment of `SUPER_ADMIN`, changes to protected accounts, and non-superuser self-escalation without permission-management authority.

## Redis, Celery, storage, and Moodle

`REDIS_URL` backs production caching and the Channels layer used for course-support event delivery across ASGI workers. Redis is transient transport, not message storage; PostgreSQL remains authoritative. Storage environment variables leave room for S3-compatible media. Moodle authenticates through versioned endpoints and must not implement academic business rules locally.

## Deployment

Use `config.settings.production`, TLS, an ASGI server, managed PostgreSQL, rotated secrets, restricted CORS/hosts/socket origins, Redis, and object storage. Run migrations and `setup_groups` during controlled deployment. Keep course support disabled until its `wss://` route and privacy controls pass staging verification. Do not run demo seed commands in production.

### Railway (Dockerfile)

Railway detects the root `Dockerfile` automatically. Create a project, add this
GitHub repository as the backend service, and add managed PostgreSQL and Redis
services to the same project. In the backend service's Variables tab, add:

```text
DJANGO_SECRET_KEY=<at-least-50-random-characters>
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECURE_SSL_REDIRECT=true
PGDATABASE=${{Postgres.PGDATABASE}}
PGUSER=${{Postgres.PGUSER}}
PGPASSWORD=${{Postgres.PGPASSWORD}}
PGHOST=${{Postgres.PGHOST}}
PGPORT=${{Postgres.PGPORT}}
REDIS_URL=${{Redis.REDIS_URL}}
RUN_MIGRATIONS=true
RUN_SETUP_GROUPS=true
MOODLE_SSO_SECRET=<strong-random-secret>
MOODLE_ORIGIN=https://your-moodle-host.example
CORS_ALLOWED_ORIGINS=https://your-frontend.example,https://your-moodle-host.example
COURSE_SUPPORT_CHAT_ALLOWED_ORIGINS=https://your-frontend.example,https://your-moodle-host.example
```

Use the actual Railway service names in the reference variables if they differ
from `Postgres` or `Redis`. Generate a public domain for the backend and set the
deployment healthcheck path to `/api/v1/health/`. The container listens on the
Railway-provided `PORT`; the generated `RAILWAY_PUBLIC_DOMAIN` and Railway's
healthcheck hostname are admitted automatically.

For uploaded media and private documents, attach persistent storage before
production use. One option is a Railway volume mounted at `/data`, with
`MEDIA_ROOT=/data/media`, `PRIVATE_DOCUMENT_ROOT=/data/private_documents`, and
`RAILWAY_RUN_UID=0` (Railway mounts volumes as root). Prefer S3-compatible
object storage for horizontally scaled deployments.

After the first successful deployment, open a Railway shell for the backend and
create the initial administrator:

```bash
python manage.py createsuperuser
```

For safer multi-replica deployments, move `migrate` and `setup_groups` to a
Railway pre-deploy command and set both `RUN_*` variables to `false` so only one
deployment job changes the database.
