# tgbot – Price & Bank Offer Tracker

A Dockerized microservice architecture that tracks product prices and bank offers on **Flipkart** and **Vivo IN**, delivering Telegram notifications when anything changes.

---

## Architecture Overview

```
Telegram User
     │
     ▼
bot-service  ←──────────────────────── scheduler-service
     │                                        │
     ▼                                        ▼
api-gateway ──── postgres          scraper-service
                                             │
                                      offer-engine
```

| Service            | Port  | Description                                     |
|--------------------|-------|-------------------------------------------------|
| `api-gateway`      | 7500  | REST API, PostgreSQL persistence                |
| `bot-service`      | —     | Telegram bot (polling) + internal notify server (8080) |
| `scraper-service`  | 7501  | Flipkart & Vivo page scraper                    |
| `offer-engine`     | 7502  | Offer normalisation & change detection          |
| `scheduler-service`| —     | Periodic check job (APScheduler)                |
| `postgres`         | 5432  | PostgreSQL 15                                   |

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) >= 24
- [Docker Compose](https://docs.docker.com/compose/install/) v2

---

## Setup

```bash
# 1. Clone the repo and enter the directory
git clone <repo-url> && cd tgbot

# 2. Copy the example env file
cp .env.example .env

# 3. Set your Telegram bot token (get one from @BotFather)
#    Edit .env and replace the placeholder value:
#    TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
```

---

## Run

```bash
docker-compose up --build
```

The API gateway will be available at **http://localhost:7500**.

To run in detached mode:

```bash
docker-compose up --build -d
```

---

## API Endpoints

### `GET /health`
Returns `{"status": "ok"}`.

### `POST /users`
Create or retrieve a user by Telegram user ID.
```json
{ "telegram_user_id": "123456789" }
```

### `GET /users/{id}`
Get a user by internal database ID.

### `POST /track`
Start tracking a product URL.
```json
{ "url": "https://www.flipkart.com/...", "telegram_user_id": "123456789" }
```
Supported domains: `flipkart.com`, `fkrt.it`, `shop.vivo.com`.

### `GET /products?user_id=<telegram_user_id>`
List tracked products. Omit `user_id` to list all.

### `PATCH /products/{id}`
Update product data (used internally by the scheduler).

### `DELETE /products/{id}`
Remove a product from tracking.

---

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/track <url>` | Start tracking a product |
| `/list` | List your tracked products |
| `/remove <id>` | Stop tracking a product |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | — | **Required.** Token from @BotFather |
| `DATABASE_URL` | `postgresql://user:password@postgres:5432/tracker` | PostgreSQL connection string |
| `SCRAPER_TIMEOUT` | `30` | HTTP timeout for scraper requests (seconds) |
| `CHECK_INTERVAL_MINUTES` | `30` | How often the scheduler checks all products |

---

## Development Notes

- Alembic migrations are in `api-gateway/alembic/`. Run `alembic upgrade head` inside the container to apply them (tables are also auto-created on startup via `Base.metadata.create_all`).
- The scraper uses realistic browser headers and exponential-backoff retries to handle transient failures.
- The offer engine computes a SHA-256 hash of normalised offers to detect changes without storing full offer text.
