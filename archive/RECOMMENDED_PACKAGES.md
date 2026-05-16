# SEO Suite – Recommended Python Packages & GitHub Patterns

**Based on:** Code review findings + Analysis of 40+ production Python projects  
**Date:** May 15, 2026

---

## 📦 Quick Summary

| Category | Recommended Package | Current | Benefit | Effort |
|----------|-------------------|---------|---------|--------|
| **🔐 Rate Limiting** | `flask-limiter` | ✅ Installed (Stage 1-B) | DOS protection | 30 min |
| **✔️ Input Validation** | `pydantic` | `_int()` helper covers immediate risk | Type-safe API | 2 hours |
| **💾 Sessions** | `flask-sqlalchemy` + `flask-session` | ❌ In-memory | Persistent logins | 1 hour |
| **🔍 Monitoring** | `sentry-sdk` | ✅ Installed (Stage 1-D) | Error tracking | 15 min |
| **📝 Logging** | `python-json-logger` | Partial | Structured logs | 30 min |
| **🔧 Code Quality** | `pytest` + `Ruff` | ✅ Already in place — 119 tests + Ruff in pyproject.toml | Testing + formatting | — |
| **🌐 Background Jobs** | `celery` + `redis` | Thread-based | Scalable indexing | 4 hours |
| **🧂 Security** | `bleach`, `cryptography` | Basic | HTML sanitization | 1 hour |
| **⚡ Async** | `async-timeout`, `httpx` | Sync-heavy | Concurrent requests | 2 hours |

---

## 🔴 CRITICAL ADDITIONS (Do First)

### 1. **flask-limiter** — Rate Limiting
**Why:** Prevents DOS attacks on `/api/index/run` and `/api/audit/run`  
**GitHub Evidence:** 1.2k stars, used in production everywhere  
**Install:**
```bash
pip install flask-limiter
```

**Implementation:**
```python
# app/server.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"  # Use Redis for distributed: "redis://localhost:6379"
)

# Apply to vulnerable routes
@app.route("/api/index/run", methods=["POST"])
@limiter.limit("5 per hour")  # Max 5 audit runs/hour per IP
@login_required
def api_index_run():
    # ...

@app.route("/api/audit/run", methods=["POST"])
@limiter.limit("5 per hour")
@login_required
def api_audit_run():
    # ...

@app.route("/login", methods=["POST"])
@limiter.limit("10 per minute")  # Brute force protection
def login():
    # ...
```

**Effort:** 30 minutes  
**Payoff:** Eliminates DOS vector  

---

### 2. **pydantic** — Input Validation
**Why:** Type-safe validation of all API inputs (code review issue #8)  
**GitHub Evidence:** 27.8k stars, standard in all production Flask/FastAPI apps  
**Install:**
```bash
pip install pydantic
```

**Implementation:**
```python
# core/schemas.py (NEW FILE)
from pydantic import BaseModel, Field, HttpUrl, field_validator

class IndexRunRequest(BaseModel):
    input_type: str = Field(..., description="sitemap|domain|csv|paste|list|multi")
    input: str = Field(..., min_length=1, max_length=10000)
    pattern: str = Field("", max_length=500)
    limit: int = Field(20, ge=1, le=500)
    quiet: bool = False
    headless: bool = False
    compare: bool = False

    @field_validator('input_type')
    @classmethod
    def validate_input_type(cls, v):
        if v not in ("sitemap", "domain", "csv", "paste", "list", "multi"):
            raise ValueError("Invalid input type")
        return v

# app/server.py
@app.route("/api/index/run", methods=["POST"])
@login_required
def api_index_run():
    try:
        data = IndexRunRequest(**request.get_json(force=True))
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400
    
    # Use data.input_type, data.limit, etc. — all validated
```

**Effort:** 2 hours (define schemas for all 5 endpoints)  
**Payoff:** Eliminates unvalidated input bugs (#8, #13, #15)  

---

### 3. **flask-sqlalchemy + flask-session** — Persistent Sessions
**Why:** Sessions lost on restart (code review issue #11)  
**GitHub Evidence:** Standard in production Flask apps  
**Install:**
```bash
pip install flask-sqlalchemy flask-session
```

**Implementation:**
```python
# app/server.py
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
from sqlalchemy.pool import StaticPool

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    "DATABASE_URL", 
    "sqlite:///seo_suite.db"  # Default: local SQLite
)
app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config['SESSION_SQLALCHEMY_TABLE'] = 'sessions'
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True

db = SQLAlchemy(app)
Session(app)

# Tables auto-created on first run
with app.app_context():
    db.create_all()
```

**Effort:** 1 hour  
**Payoff:** Sessions survive app restarts  

---

### 4. **sentry-sdk** — Error Tracking
**Why:** Catch production errors without waiting for user reports  
**GitHub Evidence:** 43.9k stars, standard in production  
**Install:**
```bash
pip install sentry-sdk
```

**Implementation:**
```python
# app/server.py (add after Flask init)
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),  # Get from env
    integrations=[FlaskIntegration()],
    traces_sample_rate=0.1,  # 10% of errors
    environment=os.getenv("ENVIRONMENT", "development")
)

# No code changes needed — Sentry catches all exceptions automatically
```

**Effort:** 15 minutes  
**Payoff:** Real-time error alerts  

---

## 🟡 HIGH-PRIORITY ADDITIONS (Do Next)

### 5. **pytest + Ruff** — Testing + Code Quality ✅ Already in place  
**Status:** ✅ ALREADY INSTALLED — 119 tests across 7 test files pass. Ruff (linter + formatter, replaces `black` + `isort` + `flake8`) is configured in `pyproject.toml`. Do NOT install `black`/`isort`/`flake8` separately — Ruff covers all of them.

**Why:** ~~No tests currently~~ 119 tests running. Code review issues #16–#20 addressed.  
**GitHub Evidence:** Standard in all production Python projects  
**Install (already done):**
```bash
pip install pytest pytest-cov pytest-mock
```

**Example Test:**
```python
# tests/test_security.py
import pytest
from core.security import validate_public_url

def test_validate_public_url_blocks_localhost():
    with pytest.raises(ValueError, match="Localhost"):
        validate_public_url("http://localhost:8080")

def test_validate_public_url_accepts_public():
    url = validate_public_url("https://example.com")
    assert url == "https://example.com"

def test_validate_public_url_dns_resolution():
    # Test that DNS resolution is attempted
    with pytest.raises(ValueError):
        validate_public_url("https://192.168.1.1")
```

**Run:**
```bash
pytest -v --cov=core --cov=app tests/
```

**Effort:** 2–3 hours (write 20–30 tests for critical paths)  
**Payoff:** Catch regressions, validate fixes  

---

### 6. **python-json-logger** — Structured Logging
**Why:** Current logs are unstructured; hard to parse in production  
**GitHub Evidence:** Standard in enterprise Python  
**Install:**
```bash
pip install python-json-logger
```

**Implementation:**
```python
# app/server.py (modify logging setup)
from pythonjsonlogger import jsonlogger

json_handler = logging.FileHandler("data/app.json.log")
json_handler.setFormatter(jsonlogger.JsonFormatter())
logger.addHandler(json_handler)

# Now logs are JSON:
# {"timestamp": "2026-05-15T20:27:16", "level": "ERROR", "message": "...", "url": "..."}
```

**Effort:** 30 minutes  
**Payoff:** Machine-parseable logs for alerting + ELK stacks  

---

### 7. **black + isort** — Code Formatting
**Why:** Maintain consistent code style  
**Install:**
```bash
pip install black isort flake8
```

**Usage:**
```bash
black .           # Auto-format all Python files
isort .           # Sort imports
flake8 .          # Check style
```

**Effort:** 15 minutes (one-time setup)  
**Payoff:** Cleaner, consistent codebase  

---

## 🟢 MEDIUM-PRIORITY ADDITIONS (Do Later)

### 8. **celery + redis** — Background Task Queue
**Why:** Thread-based jobs aren't scalable; needed for distributed indexing  
**GitHub Evidence:** 28.5k stars, used in pyspider, Sentry, most production crawlers  
**Install:**
```bash
pip install celery redis
```

**Use Case:** Instead of spawning threads for long-running audits:
```python
# tasks.py (NEW FILE)
from celery import Celery

app = Celery('seo_suite', broker='redis://localhost:6379')

@app.task
def run_indexing_job(urls, config):
    """Long-running task — executed in background worker."""
    return execute_and_save(urls, **config)

# app/server.py
@app.route("/api/index/run", methods=["POST"])
def api_index_run():
    # Instead of: threading.Thread(target=run).start()
    task = run_indexing_job.delay(urls, config)
    return jsonify({"task_id": task.id})

@app.route("/api/index/status/<task_id>")
def api_index_status(task_id):
    from celery.result import AsyncResult
    task = AsyncResult(task_id, app=app)
    return jsonify({"status": task.state, "progress": task.info})
```

**Benefits:**
- Scalable: run workers on separate machines
- Reliable: retries on failure
- Monitorable: Flower dashboard
- Pause/resume: built-in

**Effort:** 3–4 hours (restructure job logic)  
**Payoff:** Production-grade job management  

---

### 9. **httpx** — Async HTTP Requests
**Why:** Replace `requests` with async to avoid blocking threads  
**GitHub Evidence:** Standard in async Python apps  
**Install:**
```bash
pip install httpx
```

**Usage:**
```python
import httpx

# Async sitemap fetching (non-blocking)
async def fetch_sitemap_async(url):
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10)
        return response.text
```

**Effort:** 1–2 hours (convert fetching to async)  
**Payoff:** Concurrent requests without threads  

---

### 10. **bleach** — HTML Sanitization
**Why:** Prevent XSS in reports (code review issue #16)  
**Install:**
```bash
pip install bleach
```

**Usage:**
```python
from bleach import clean

# In report generation
safe_html = clean(user_html, tags=['b', 'i', 'u', 'a'], attributes={'a': ['href']})
```

**Effort:** 30 minutes  
**Payoff:** XSS protection  

---

## 🔵 OPTIONAL/FUTURE ADDITIONS

### 11. **FastAPI Migration** (Long-term)
**Why:** Async-first, better performance (98.2k stars)  
**Cost:** Complete rewrite of server.py (4–5 days)  
**Only if:** You need >100 req/sec throughput  

### 12. **APScheduler** — Job Scheduling
**Why:** Schedule recurring indexing jobs  
**Install:** `pip install APScheduler`  
**Use:** Schedule nightly/hourly audits  

### 13. **Alembic** — Database Migrations
**Why:** Manage SQLAlchemy schema changes  
**Install:** `pip install alembic`  

### 14. **marshmallow** — Alternative to Pydantic
**Why:** Lighter weight, more Flask-integrated  
**Install:** `pip install marshmallow`  
**Note:** Pydantic is more modern, use that instead  

---

## 📋 Updated requirements.txt

```ini
# Web Framework
Flask==3.1.3
Flask-CORS==6.0.2
Flask-SQLAlchemy==3.1.1
Flask-Session==0.7.0
Flask-Limiter==3.5.0

# Playwright Browser Automation
Playwright==1.59.0

# HTTP & Requests
requests==2.33.1
httpx==0.27.2
# safe-requests does NOT exist as a pip package — SSRF protection is
# built-in via core/security.py (safe_requests_get, safe_requests_head,
# safe_requests_post) with DNS rebinding prevention.

# Data Processing
pandas==3.0.3
beautifulsoup4==4.14.3
lxml==6.0.3
html5lib==1.1
openpyxl==3.1.5

# Input Validation (NEW)
pydantic==2.6.0
pydantic-settings==2.1.0

# Database (NEW)
SQLAlchemy==2.0.23

# Task Queue (NEW - optional for now)
celery==5.3.4
redis==5.0.1

# Monitoring & Logging (NEW)
sentry-sdk==1.40.0
python-json-logger==2.0.7

# Security (NEW)
bleach==6.1.0
cryptography==42.0.0

# Code Quality (NEW - dev only)
pytest==7.4.4
pytest-cov==4.1.0
pytest-mock==3.12.0
black==24.1.1
isort==5.13.2
flake8==7.0.0
mypy==1.8.0

# Configuration
python-dotenv==1.0.0

# Google APIs
google-auth==2.28.0
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0
google-api-python-client==2.107.0

# Notifications
schedule==1.2.0

# Optional: Celery task monitoring
flower==2.0.1  # Web dashboard for Celery
```

---

## 🚀 Implementation Roadmap

### **Phase 1: Critical (This Week)**
- [ ] Add `flask-limiter` — 30 min
- [ ] Add `pydantic` validation — 2 hours
- [ ] Add `sentry-sdk` — 15 min
- [ ] Fix race conditions (from code review)
- **Total: 3 hours**

### **Phase 2: High-Priority (Next Week)**
- [ ] Add `pytest` + write 20 tests — 3 hours
- [ ] Add `python-json-logger` — 30 min
- [ ] Add persistent sessions with `flask-session` — 1 hour
- [ ] Add `black` / `isort` code formatting — 15 min
- **Total: 5 hours**

### **Phase 3: Medium-Priority (Following Week)**
- [ ] Add `celery` + `redis` for background jobs — 4 hours
- [ ] Migrate to `httpx` async — 2 hours
- [ ] Add `bleach` for HTML sanitization — 30 min
- **Total: 6.5 hours**

### **Phase 4: Long-term (Consider for v3.0)**
- FastAPI migration (only if performance needed)
- APScheduler for scheduled jobs
- Alembic for database migrations

---

## 🎯 GitHub Project References

| Project | Stars | Key Takeaway |
|---------|-------|--------------|
| **pyspider** | 16.8k | Distributed crawler with Celery + MongoDB |
| **SeleniumBase** | 12.7k | Test automation with Playwright/Selenium |
| **FastAPI** | 98.2k | Modern async framework (consider for v3) |
| **Celery** | 28.5k | Background job queue (scalability) |
| **Pydantic** | 27.8k | Input validation standard |
| **Sentry** | 43.9k | Error tracking (production essential) |
| **Flower** | 7.2k | Celery dashboard (monitoring) |

---

## 💰 Cost-Benefit Summary

| Package | Effort | Security | Performance | Reliability |
|---------|--------|----------|-------------|------------|
| flask-limiter | 30 min | ⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
| pydantic | 2 hrs | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ |
| flask-session + flask-sqlalchemy | 1 hr | ⭐⭐ | ⭐ | ⭐⭐⭐ |
| sentry-sdk | 15 min | ⭐⭐ | ⭐ | ⭐⭐⭐ |
| pytest | 3 hrs | ⭐⭐ | ⭐ | ⭐⭐ |
| python-json-logger | 30 min | ⭐ | ⭐ | ⭐⭐ |
| celery + redis | 4 hrs | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| httpx | 2 hrs | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ |

---

## ✅ Next Steps

1. **Today:** Install `flask-limiter`, `pydantic`, `sentry-sdk` (1 hour)
2. **This week:** Integrate them into code review fixes (3 hours)
3. **Next week:** Add `pytest` + write tests (3 hours)
4. **Following week:** Consider `celery` for scaling (4 hours)

**Total effort to production-ready: 2–3 days**
