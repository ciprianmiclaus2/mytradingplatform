# API

_To be completed as the implementation progresses. See the README and the V1 implementation plan for the current state._

## Implemented endpoints

All endpoints use the `/api` prefix. Interactive OpenAPI docs: `/api/docs`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Backend status, version, environment, data schema version |

### Error format

Every error response has this shape:

```json
{"error": {"code": "validation_error", "message": "Request validation failed", "details": [...]}}
```

Unexpected errors return `500` with `code: "internal_error"`. Stack traces are logged on the backend only.
