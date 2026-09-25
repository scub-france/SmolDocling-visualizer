# Monitoring checklist

## Health endpoint

```bash
curl -s http://localhost:3000/api/health
```

Alert when it does not answer with HTTP 200 within 1 second, or when:

- `status` is not `"ok"` (it becomes `"degraded"` when the database fails),
- `database` is not `"ok"`.

The backend itself always answers 200. Through port 3000, nginx answers 502 when the backend is down.

The answer also gives `version`, `engine`, `deploymentMode`, the upload limits, and the flags `ingestionAvailable`, `reasoningAvailable`, `studioModeEnabled` and `ragPipelineEnabled`. Check `version` after each deploy.

No Docker healthcheck is defined for the app containers: use an external uptime check on `/api/health`.

## What to watch

| Signal | How | Alert when |
|--------|-----|------------|
| `/api/health` | Uptime monitor | No 200 within 1 s |
| Server errors (5xx) | nginx access log | Over 1% of requests |
| Failed analyses | **Analyses** page, status `FAILED` | Over 10% |
| Rate-limit hits (429) | nginx access log | Sudden spike |
| CPU and memory | `docker stats` | Over 90% CPU or 85% memory for a while |
| Disk | Size of the data and uploads volumes | Over 80% |
| Restarts | `docker inspect --format '{{.RestartCount}}' docling-studio` | Above 0 |

The restart count only moves when the container runs with a restart policy, as in the [deployment checklist](../release/deployment-checklist.md) (`--restart unless-stopped`).

The local engine is heavy: memory is the first limit to hit. Analyses beyond `MAX_CONCURRENT_ANALYSES` wait in `PENDING`.

## Logs

Single image:

- `docker logs -f docling-studio` shows the backend.
- nginx writes to files inside the container: `docker exec docling-studio tail -f /var/log/nginx/access.log /var/log/nginx/error.log`.

Docker Compose: `docker compose logs -f document-parser` for the backend, `docker compose logs -f frontend` for nginx.

Look for:

- `ERROR` lines, `TimeoutError` from Docling, `sqlite3.OperationalError` in the backend,
- `502` in nginx (backend down),
- `413` in nginx (upload over `NGINX_MAX_BODY_SIZE`).
