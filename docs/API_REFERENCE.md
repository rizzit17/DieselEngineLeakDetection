# API Reference — Diesel Engine Air Leak Detection

Base URL (development): `http://localhost:8000`  
WebSocket URL (development): `ws://localhost:8000/ws/engine/`  
Authentication: Token-based (`Authorization: Token <token>`)

---

## Authentication Endpoints

### POST /user_auth/signup/

Register a new user account. Returns a token for immediate use.

**Request**
```
Content-Type: application/json
```
```json
{
  "username": "test_engineer",
  "email": "engineer@caterpillar.com",
  "password": "<your_password>",
  "role": "tester"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| username | string | yes | Unique; 150 chars max |
| email | string | yes | Valid email format |
| password | string | yes | Django validators apply |
| role | string | no | viewer / tester / admin; defaults to viewer |

**Response 201 Created**
```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "user": {
    "id": 1,
    "username": "test_engineer",
    "email": "engineer@caterpillar.com",
    "role": "tester"
  }
}
```

**Response 400 Bad Request** (validation failure)
```json
{
  "username": ["A user with that username already exists."]
}
```

```bash
curl -X POST http://localhost:8000/user_auth/signup/ \
  -H "Content-Type: application/json" \
  -d '{"username":"test_engineer","email":"engineer@caterpillar.com","password":"<your_password>","role":"tester"}'
```

---

### POST /user_auth/login/

Authenticate with username and password. Returns token.

**Request**
```json
{
  "username": "test_engineer",
  "password": "<your_password>"
}
```

**Response 200 OK**
```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
}
```

**Response 400 Bad Request**
```json
{
  "error": "Invalid credentials"
}
```

```bash
curl -X POST http://localhost:8000/user_auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"test_engineer","password":"<your_password>"}'
```

---

### POST /user_auth/logout/

Invalidate the current auth token.

**Request**
```
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```
No body required.

**Response 200 OK**
```json
{
  "message": "Logged out successfully"
}
```

**Response 401 Unauthorized** — missing or invalid token.

```bash
curl -X POST http://localhost:8000/user_auth/logout/ \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
```

---

### DELETE /user_auth/delete_account/

Permanently delete the authenticated user's account and invalidate the token.

**Request**
```
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```

**Response 200 OK**
```json
{
  "message": "Account deleted"
}
```

```bash
curl -X DELETE http://localhost:8000/user_auth/delete_account/ \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
```

---

## Inference Endpoint

### POST /api/predict

Single-shot inference. Send one sensor reading; receive a full anomaly score breakdown.

**Request**
```
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
Content-Type: application/json
```

All 12 sensor channels are required. Missing any channel returns 400.

```json
{
  "rpm": 1600.0,
  "fuel_rate": 75.0,
  "turbo_speed": 90000.0,
  "boost_pressure": 1.2,
  "MAP": 2.2,
  "IAT": 305.0,
  "MAF": 500.0,
  "EGT": 650.0,
  "exhaust_pressure": 2.5,
  "VGT": 50.0,
  "DPF_delta": 20000.0,
  "ambient_pressure": 1.0
}
```

| Channel | Unit | Typical healthy range |
|---------|------|-----------------------|
| rpm | rev/min | 600–2200 |
| fuel_rate | L/hr | 10–200 |
| turbo_speed | rev/min | 30000–150000 |
| boost_pressure | bar (gauge) | 0.8–2.5 |
| MAP | bar (absolute) | 1.5–3.5 |
| IAT | K | 280–340 |
| MAF | g/s | 100–800 |
| EGT | K | 500–900 |
| exhaust_pressure | bar | 1.5–3.5 |
| VGT | % open | 10–90 |
| DPF_delta | Pa | 0–50000 |
| ambient_pressure | bar | 0.95–1.05 |

**Response 200 OK**

```json
{
  "is_leak": false,
  "confidence": 0.12,
  "z_cumulative": 2.31,
  "final_score": 2.31,
  "physics_score": 2.31,
  "boost_z": 0.82,
  "dpf_z": 0.44,
  "maf_z": 1.01,
  "exhaust_z": 0.55,
  "svm_z": 0.33,
  "ae_z": 0.71,
  "z_mahalanobis": 1.12,
  "z_scores": [0.82, 0.44, 1.01, 0.55, 1.12, 0.33],
  "leak_type": null
}
```

| Response field | Type | Description |
|---------------|------|-------------|
| is_leak | bool | True if z_cumulative ≥ MODEL_STACK_ANOMALY_THRESHOLD (3.5) |
| confidence | float [0,1] | Normalized score: min(z_cumulative / threshold, 1.0) |
| z_cumulative | float ≥ 0 | Fused z-score: √(z_boost²+z_dpf²+z_maf²+z_exhaust²+0.3·z_mahal²+z_svm²) |
| final_score | float | Alias for z_cumulative (same value) |
| physics_score | float | Alias for z_cumulative (legacy field) |
| boost_z | float ≥ 0 | Boost-circuit autoencoder z-score |
| dpf_z | float ≥ 0 | DPF autoencoder z-score |
| maf_z | float ≥ 0 | MAF autoencoder z-score |
| exhaust_z | float ≥ 0 | Exhaust autoencoder z-score |
| svm_z | float ≥ 0 | One-Class SVM anomaly z-score |
| ae_z | float ≥ 0 | Mean of the four AE z-scores |
| z_mahalanobis | float ≥ 0 | Mahalanobis distance z-score |
| z_scores | float[6] | [boost_z, dpf_z, maf_z, exhaust_z, z_mahal, svm_z] |
| leak_type | str or null | "precompressor" / "charge_air" / "exhaust" / null |

**Response 400 Bad Request** — missing or non-numeric channel

```json
{
  "error": "Missing required sensor channels",
  "missing": ["DPF_delta", "ambient_pressure"]
}
```

or

```json
{
  "error": "Non-numeric value for channel 'rpm': 'idle'"
}
```

**Response 401 Unauthorized** — missing or invalid token

**Response 500 Internal Server Error** — unexpected inference failure

```json
{
  "error": "Inference failed: <exception message>"
}
```

```bash
# Healthy sample
curl -X POST http://localhost:8000/api/predict \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b" \
  -H "Content-Type: application/json" \
  -d '{
    "rpm": 1600.0,
    "fuel_rate": 75.0,
    "turbo_speed": 90000.0,
    "boost_pressure": 1.2,
    "MAP": 2.2,
    "IAT": 305.0,
    "MAF": 500.0,
    "EGT": 650.0,
    "exhaust_pressure": 2.5,
    "VGT": 50.0,
    "DPF_delta": 20000.0,
    "ambient_pressure": 1.0
  }'
```

---

## WebSocket Endpoint

### WS /ws/engine/

Streaming inference for live test-cell runs. The client sends one sensor sample per timestep; the server returns scored results and issues a final verdict when a leak is confirmed or the session times out.

**Connection**
```
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```

All WebSocket messages are JSON strings.

---

### Client → Server: Engine Registration (first message)

Must be the first message after connection. Any other message format closes the connection.

```json
{
  "model_no": "CAT-3412-001",
  "engine_type": "diesel"
}
```

---

### Client → Server: Sensor Sample

All 12 channels required. Identical field names and units as `/api/predict`.

```json
{
  "rpm": 1600.0,
  "fuel_rate": 75.0,
  "turbo_speed": 90000.0,
  "boost_pressure": 1.2,
  "MAP": 2.2,
  "IAT": 305.0,
  "MAF": 500.0,
  "EGT": 650.0,
  "exhaust_pressure": 2.5,
  "VGT": 50.0,
  "DPF_delta": 20000.0,
  "ambient_pressure": 1.0
}
```

---

### Server → Client: Message Types

#### `engine_registered`
Sent immediately after valid engine registration.
```json
{
  "type": "engine_registered",
  "model_no": "CAT-3412-001",
  "engine_type": "diesel"
}
```

#### `error`
Sent when the first message is missing `model_no` or `engine_type`. Connection closes after.
```json
{
  "type": "error",
  "message": "First message must contain model_no and engine_type"
}
```

#### `buffering`
Sent for each sample while the stability buffer is filling (first 7 samples).
```json
{
  "type": "buffering",
  "buffered": 3,
  "required": 7
}
```

#### `unstable`
Sent when the engine is not at steady state (CV checks fail).
```json
{
  "type": "unstable",
  "message": "Engine not at steady state — RPM CV=0.023 exceeds limit 0.010"
}
```

#### `sample_result`
Sent after each stable sample is scored.
```json
{
  "type": "sample_result",
  "status": "normal",
  "confidence": 0.12,
  "z_scores": {
    "boost": 0.82,
    "dpf": 0.44,
    "maf": 1.01,
    "exhaust": 0.55,
    "mahalanobis": 1.12,
    "svm": 0.33,
    "cumulative": 2.31
  },
  "window_index": 0
}
```

`status` is `"leak"` when z_cumulative ≥ CONSUMER_ANOMALY_THRESHOLD (6.3156).

#### `window_result`
Sent after every `INFERENCE_WINDOW_SIZE` (7) samples.
```json
{
  "type": "window_result",
  "window_index": 2,
  "window_leak": true,
  "anomaly_count": 5,
  "confirmed_windows": 1,
  "leaky_samples_last_window": [4, 5, 6, 8, 9]
}
```

#### `test_complete`
Sent when `CONFIRMATION_WINDOWS_REQUIRED` (2) consecutive anomalous windows are detected, or when the session timeout is reached.
```json
{
  "type": "test_complete",
  "leak_detected": true,
  "windows_evaluated": 4,
  "confirmed_anomaly_windows": 2
}
```

---

### WebSocket Session Lifecycle

```
Client                                    Server
  |                                          |
  |-- (connect with token) ----------------> |
  |<-- (accept) ----------------------------|
  |-- {"model_no":"X","engine_type":"Y"} --> |
  |<-- {"type":"engine_registered"} --------|
  |-- {12 sensor channels} --------------->  |
  |<-- {"type":"buffering"} ---------------- |  (×7 while buffer fills)
  |-- {12 sensor channels} --------------->  |
  |<-- {"type":"sample_result"} ----------- |  (inference starts)
  |   ...                                    |
  |<-- {"type":"window_result"} ----------- |  (after every 7 samples)
  |   ...                                    |
  |<-- {"type":"test_complete"} ----------- |  (leak confirmed or timeout)
  |-- (disconnect) -----------------------> |
```

---

## Error Codes Summary

| Code | Endpoint | Cause |
|------|----------|-------|
| 201 | POST /signup | User created |
| 200 | POST /login | Login successful |
| 200 | POST /predict | Inference successful |
| 400 | POST /signup | Validation failure (duplicate username, etc.) |
| 400 | POST /predict | Missing channel, non-numeric value |
| 401 | Any authenticated | Missing or invalid token |
| 500 | POST /predict | Unexpected inference error |
