# Tabuney — Table Journey Web

The source code behind [tabuney.com](https://tabuney.com), a multilingual board game site. It offers game and edition pages, illustrated turn-flow flowcharts, GM-style teaching scripts, rulebook search, a board game blog feed aggregator, and memberships.

This repository is public so people can read the code. It is **not** open source. See [License](#license).

Some parts are left out of this public copy, including the LLM prompts and RAG pipeline (`game/rag/`), the publisher scrapers and the CI configuration. Because of this, the code here does not run on its own.

## Stack

| Layer | Tech |
|---|---|
| Backend | Django 4.2, Django REST Framework (JWT), django-allauth (Google sign-in) |
| Database | PostgreSQL 17 |
| Background jobs | django-q (`qcluster`) |
| Vector search | Qdrant (rulebook RAG) |
| LLM / translation | Gemini, OpenAI, Claude, DeepL |
| Payments | Stripe (subscriptions and one-off unlocks) |
| Flowchart editor | React 18 + React Flow, built with Vite (`admin_frontend/`) |
| Runtime | Docker Compose; Gunicorn behind Nginx in production |

## Project layout

| Path | Purpose |
|---|---|
| `TJsite/` | Django project: settings, root URLs, sitemaps |
| `game/` | Games, editions, publishers, rulebooks, flowcharts, GM scripts, RAG pipeline (`game/rag/`) |
| `member/` | Member profiles and accounts |
| `commerce/` | Stripe checkout, webhooks, transactions |
| `interaction/` | Ratings and play status |
| `feed/` | RSS aggregation of board game blogs |
| `translation/` | UI translation strings and the `{% t %}` template tag |
| `messaging/`, `msg/` | Member messaging and notifications |
| `stats/` | Site statistics |
| `ad/`, `home/`, `tablejourney/` | Ads, home page, legacy app routes |
| `admin_frontend/` | Source for the flowchart editor; its build output goes to `static/game/admin/flowchart_editor/` |
| `deploy/vps/` | VPS provisioning and monitoring scripts |

## Local development

Requirements: Docker Desktop.

1. Create `.env` in the project root (see [Environment variables](#environment-variables)).
2. Start the stack:

   ```bash
   docker compose up -d
   ```

3. Run Django commands inside the `web` container:

   ```bash
   docker compose exec web python manage.py migrate
   docker compose exec web python manage.py createsuperuser
   ```

The site is served at <http://localhost:8000>.

Settings load `.env` first. They then load `.env.development` or `.env.production` on top of it, depending on `DJANGO_ENV` (default `development`). Heavy jobs such as PDF extraction, OCR, RAG ingestion, scraping and translation generation run only in development. The production image does not install their dependencies.

To work on the flowchart editor:

```bash
cd admin_frontend
npm install
npm run dev      # or: npm run build
```

## Environment variables

None of these are committed. `DJANGO_SECRET_KEY` is required. The site starts without the others, but the related features stop working.

| Variable | Used for |
|---|---|
| `DJANGO_SECRET_KEY` | Django signing key; use a different value in each environment |
| `DJANGO_ENV`, `DEBUG` | Environment selection |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Database |
| `QDRANT_HOST`, `QDRANT_PORT` | Vector store |
| `SOCIAL_AUTH_GOOGLE_CLIENT_ID`, `SOCIAL_AUTH_GOOGLE_SECRET`, `GOOGLE_CLIENT_IDS` | Google sign-in |
| `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_*_PRICE_ID`, `STRIPE_*_PRODUCT_ID` | Payments |
| `GEMINI_API_KEY`, `OPENAI_API_KEY`, `CLAUDE_API_KEY`, `LLAMA_PARSE_API_KEY` | LLM features |
| `DEEPL_AUTH_KEY` | Flowchart translation |
| `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX` | RSS source search in the admin |
| `BGG_API_TOKEN` | BoardGameGeek API |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Outgoing email |
| `GA_MEASUREMENT_ID` | Google Analytics |
| `VPS_API_TOKEN`, `VPS_API_USERNAME`, `VPS_API_PASSWORD` | Syncing data from the local machine to production |

## Deployment

A push to `main` triggers `.github/workflows/deploy.yml`. The workflow connects to the VPS over SSH and runs these steps:

1. Pull the latest code.
2. Build the new images while the old containers keep serving.
3. Run migrations and `collectstatic`.
4. Swap in the new containers with `docker-compose.prod.yml`.

## License

Copyright © Tabuney. All rights reserved.

You may read this code. You may not copy, modify, distribute or use it, in whole or in part, without written permission.
