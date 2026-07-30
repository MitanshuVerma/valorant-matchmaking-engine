# Matchmaking Engine & Live Telemetry Service

A low-latency, scalable matchmaking engine and player telemetry service inspired by Riot Games' architecture.

## Tech Stack
- **Python / FastAPI**: High performance async web framework.
- **Redis (Redis-Py)**: In-memory datastore for fast matchmaking queue operations using Sorted Sets (ZSET).
- **PostgreSQL (asyncpg)**: Persistent storage for completed matches and historical stats.
- **httpx**: Async HTTP client for Riot Games API integration.
- **Docker & Docker-Compose**: Easy environment setup.

## Features
- **Concurrent Matchmaking**: Players join a Redis ZSET based on MMR. A background worker continuously scans the queue to form balanced lobbies.
- **Dynamic MMR Expansion**: If a player waits too long, the acceptable MMR gap widens dynamically to ensure they find a match.
- **Live Telemetry Parsing**: Resolves Riot IDs, fetches recent matches, and calculates KDA, KP%, GPM, and CSPM. Results are cached in Redis to prevent API rate limiting.

## Setup & Running Locally

1. **Clone & Virtual Environment**
   ```bash
   python -m venv venv
   source venv/Scripts/activate  # On Windows
   pip install -r requirements.txt
   ```

2. **Environment Variables**
   Copy `.env.example` to `.env` and fill in your Riot API Key.
   ```bash
   cp .env.example .env
   ```

3. **Start Infrastructure (Redis & PostgreSQL)**
   ```bash
   docker-compose up -d
   ```

4. **Run the Application**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   *(Note: The `main.py` lifespan event automatically creates the PostgreSQL tables on startup for ease of development).*

## API Testing (cURL & Swagger)

You can view the interactive API documentation (Swagger UI) at:
[http://localhost:8000/docs](http://localhost:8000/docs)

### 1. Join Matchmaking Queue
```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/queue/join' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "player_id": "player123",
  "mmr": 1500,
  "role": "mid",
  "max_ping": 50
}'
```

### 2. Leave Matchmaking Queue
```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/queue/leave' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "player_id": "player123"
}'
```

### 3. Fetch Player Telemetry (Requires Valid Riot API Key)
```bash
curl -X 'GET' \
  'http://localhost:8000/api/v1/player/stats/YourGameName/YourTagLine' \
  -H 'accept: application/json'
```
