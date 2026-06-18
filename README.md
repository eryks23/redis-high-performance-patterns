# redis-high-performance-patterns

> Atomic Redis patterns in Python — race-condition-safe rate limiting and distributed mutex caching via Lua scripting.

## Description

`redis-high-performance-patterns` demonstrates two production-grade Redis patterns that rely on server-side Lua scripting to guarantee atomicity: a fixed-window rate limiter and a cache-aside strategy protected by a distributed mutex lock. Both patterns eliminate the race conditions that emerge when multiple workers hit the same Redis instance simultaneously. The project targets backend engineers who want a concise, runnable reference before integrating these patterns into a live service.

## Table of Contents

- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage / Quick Start](#usage--quick-start)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Contributing](#contributing)
- [Author](#author)
- [License](#license)

---

## Key Features

- **Atomic rate limiting** — Lua `INCR` + conditional `EXPIRE` in a single script; no request can slip through the race window between the two calls
- **Cache-aside with distributed mutex** — Only one worker fetches from the data source on a cache miss; all concurrent requests back off and retry
- **Dog-pile / cache-stampede prevention** — `SETNX` + `EXPIRE` acquired atomically in Lua ensures a single writer populates the cache
- **Zero infrastructure required** — Powered by `fakeredis`; every pattern runs locally without a running Redis server
- **Self-contained demo** — The `__main__` block reproduces both scenarios end-to-end and produces readable, assertion-friendly output

---

## Tech Stack

| Component | Detail |
|---|---|
| Language | Python 3.8+ |
| Redis simulation | `fakeredis` |
| Scripting layer | Redis Lua scripting API (`EVAL`) |
| Standard library | `time` |

---

## Requirements

- Python **3.8** or later
- `pip` (bundled with Python ≥ 3.4)
- No running Redis instance needed — `fakeredis` handles all in-process state

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/eryks23/redis-high-performance-patterns.git
cd redis-high-performance-patterns

# 2. (Recommended) Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Usage / Quick Start

Run the built-in demo to exercise both patterns:

```bash
python redis_advanced_patterns.py
```

Expected output:

```
=== TEST 3: Pro Rate Limiter (Lua) ===
Attempt 1: OK
Attempt 2: OK
Attempt 3: OK
Attempt 4: LIMIT
Attempt 5: LIMIT

=== Additional TEST: User Data Cache with Lua Mutex ===
1. Fetch: {'id': 'ultra_user_1', 'name': 'Ultra Player', 'level': '99', 'status': 'db'}
2. Fetch (from cache): {'id': 'ultra_user_1', 'name': 'Ultra Player', 'level': '99', 'status': 'cached'}
```

### Switching to a real Redis instance

Replace the `fakeredis` client with a standard `redis-py` client — the rest of the code is unchanged:

```python
import redis

# Replace this line in redis_advanced_patterns.py:
# r = fakeredis.FakeRedis(decode_responses=True)

r = redis.Redis(host="localhost", port=6379, decode_responses=True)
```

Install the additional dependency:

```bash
pip install redis
```

---

## API Documentation

### `check_rate_limit_pro(user_id: str) -> bool`

Determines whether `user_id` is within the configured request quota using an atomic Lua rate limiter.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `user_id` | `str` | Unique identifier of the caller being rate-limited |

**Returns** `bool` — `True` if the request is within the limit; `False` if the quota has been exceeded.

**Behaviour**

- Limit: **3 requests** per **10-second** window
- Counter key pattern: `rate_limit:<user_id>`
- The TTL is set atomically on the first increment to prevent orphaned keys from lingering after a restart

```python
if check_rate_limit_pro("user_42"):
    process_request()
else:
    return_429_response()
```

---

### `get_user_data_pro(user_id: str) -> dict`

Returns a user profile, serving from a Redis hash cache when available. On a cache miss it acquires a distributed Lua mutex, fetches from the data source, and populates the cache — preventing concurrent workers from triggering redundant fetches.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `user_id` | `str` | Unique identifier of the user whose profile is requested |

**Returns** `dict` — User fields plus a diagnostic `"status"` key:

| `status` | Meaning |
|---|---|
| `"cached"` | Data served from the Redis hash; no data-source call made |
| `"db"` | Cache miss; data fetched from the source and written to cache |

**Behaviour**

- Cache key: `user:profile:<user_id>` (Redis hash, TTL **60 s**)
- Lock key: `lock:user:<user_id>` (TTL **5 s** — auto-released even on writer crash)
- On lock contention, the function sleeps **100 ms** and retries recursively

```python
profile = get_user_data_pro("user_42")
print(profile["name"])   # "Ultra Player"
print(profile["status"]) # "db" on first call, "cached" on subsequent calls
```

---

### Lua Scripts

Both scripts are defined as module-level constants and passed to Redis via `r.eval()`.

| Constant | Redis commands used | Purpose |
|---|---|---|
| `LUA_RATE_LIMITER` | `INCR`, `EXPIRE` | Increments a counter; sets TTL only on the first call. Returns the current counter value. |
| `LUA_ACQUIRE_LOCK` | `SETNX`, `EXPIRE` | Attempts to set a lock key with a TTL. Returns `true` on success, `false` if the lock is already held. |

Both scripts execute as a single atomic unit on the Redis server, eliminating TOCTOU (time-of-check / time-of-use) race conditions that would exist if the same logic were implemented with separate client-side calls.

---

## Project Structure

```
redis-high-performance-patterns/
├── redis_advanced_patterns.py   # Core patterns + runnable demo (__main__)
├── requirements.txt             # Python dependencies
├── LICENSE                      # MIT License
└── README.md                    # This file
```

---

## Testing

The module ships with an inline integration demo that covers both patterns end-to-end:

```bash
python redis_advanced_patterns.py
```

Because all Redis calls go through `fakeredis`, the demo is fully hermetic — no external services, no teardown needed.

To add a structured test suite with `pytest`:

```bash
pip install pytest
```

Create a `tests/` directory and import the functions directly:

```python
# tests/test_rate_limiter.py
import fakeredis
import redis_advanced_patterns as rp

def test_rate_limit_allows_within_quota():
    rp.r.flushall()
    for _ in range(3):
        assert rp.check_rate_limit_pro("test_user") is True

def test_rate_limit_blocks_over_quota():
    rp.r.flushall()
    for _ in range(3):
        rp.check_rate_limit_pro("test_user")
    assert rp.check_rate_limit_pro("test_user") is False
```

```bash
pytest tests/ -v
```

---

## Contributing

1. Fork the repository and create a feature branch:
   ```bash
   git checkout -b feature/your-pattern-name
   ```
2. Keep changes focused — one pattern or fix per pull request.
3. Update or extend the `__main__` demo block if your change affects observable behaviour.
4. Ensure new Lua scripts are defined as module-level string constants following the existing naming convention (`LUA_<PURPOSE>`).
5. Open a pull request with a clear description of what the pattern solves and why the Lua approach is preferable to a multi-step client-side implementation.

---

## Author

**eryks23**
GitHub: [@eryks23](https://github.com/eryks23)
Repository: [github.com/eryks23/redis-high-performance-patterns](https://github.com/eryks23/redis-high-performance-patterns)

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
