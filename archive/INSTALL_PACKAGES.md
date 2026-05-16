# Quick Start: Installing & Using New Packages

## 🔧 Installation

### Option 1: Install Critical Packages (Stage 1 — already done)
```bash
# flask-limiter and sentry-sdk are already installed (Stage 1-A)
pip install flask-limiter sentry-sdk
```

### Option 2: Install All Recommended (including dev tools)
```bash
# Production + Security + Monitoring
pip install flask-limiter sentry-sdk flask-sqlalchemy flask-session python-json-logger bleach

# Dev tools (testing, code quality)
# NOTE: pytest is already installed (119 tests pass).
#       Do NOT install black/isort/flake8 — Ruff covers all of them and is
#       already configured in pyproject.toml.
pip install pytest-cov pytest-mock mypy
```

### Option 3: Full Production Stack (for later)
```bash
# Also install Celery + Redis for background jobs
pip install celery redis flower
```

### Option 4: Update from requirements.txt
```bash
pip install -r requirements.txt
```

---

## 📋 What Each Package Does

### **Immediate (This Week)**

#### 1. **flask-limiter** — Prevent DOS attacks
```python
# Enable rate limiting on audit endpoints
from flask_limiter import Limiter
limiter = Limiter(app, key_func=get_remote_address)

@app.route("/api/index/run", methods=["POST"])
@limiter.limit("5 per hour")  # Max 5 runs per hour per IP
def api_index_run():
    # ...
```

#### 2. **pydantic** — Type-safe input validation
```python
from pydantic import BaseModel, Field

class IndexInput(BaseModel):
    input: str = Field(..., min_length=1, max_length=10000)
    limit: int = Field(20, ge=1, le=500)

# Validate automatically
data = IndexInput(**request.json())
```

#### 3. **sentry-sdk** — Automatic error tracking
```python
import sentry_sdk
sentry_sdk.init(dsn="https://YOUR_SENTRY_DSN", traces_sample_rate=0.1)
# Now all errors are logged to Sentry dashboard
```

#### 4. **flask-session + flask-sqlalchemy** — Persistent logins
```python
# Sessions now survive app restarts
app.config['SESSION_TYPE'] = 'sqlalchemy'
```

---

### **Next (Next Week)**

#### 5. **pytest** — Write tests ✅ Already installed  
> **Note:** pytest is already installed and 119 tests pass. Do not re-install.
```bash
# Run all tests
pytest tests/

# Run with coverage report
pytest --cov=app --cov=core tests/
```

#### 6. **Ruff** — Auto-format + lint ✅ Already configured  
> **Note:** Ruff is already configured in `pyproject.toml`. It replaces `black`, `isort`, and `flake8` in a single fast tool. Do NOT install those separately.
```bash
# Format + lint all Python files
ruff check .
ruff format .
```

#### 7. **python-json-logger** — Structured logging
```python
# Logs now output JSON (machine-parseable)
# {"timestamp": "2026-05-15T20:27:16", "level": "ERROR", ...}
```

---

### **Later (Following Week+)**

#### 8. **celery + redis** — Background jobs at scale
```python
# Move long-running audits to background workers
# Can now run 100 concurrent audits on 10 machines
```

#### 9. **bleach** — Prevent XSS attacks
```python
from bleach import clean
safe_html = clean(user_html, tags=['b', 'i', 'a'])
```

---

## 🚀 Next Steps

### Step 1: Install critical packages ✅ Done (Stage 1-A)
```bash
cd "d:\Coding\SEO Suite"
# flask-limiter and sentry-sdk are already installed
pip install flask-limiter sentry-sdk
```

### Step 2: Update requirements.txt (already done)
```bash
# Verify the new packages are listed
cat requirements.txt | grep -E "pydantic|flask-limiter|sentry"
```

### Step 3: Read the detailed guide
See `RECOMMENDED_PACKAGES.md` for full implementation examples.

### Step 4: Fix code review issues first
Before adding new packages, fix the critical bugs identified in `CODE_REVIEW.md`:
1. Race condition in audit buffers (5 min)
2. Thread safety on _last_index_run (10 min)
3. DNS rebinding audit (30 min)

---

## 📊 Implementation Timeline

| Week | Task | Effort | Packages |
|------|------|--------|----------|
| **This week** | Fix critical bugs + add rate limiting | 1–2 hours | flask-limiter |
| **Next week** | Add input validation + persistent sessions | 2–3 hours | pydantic, flask-session |
| **Following week** | Add testing + error tracking | 3–4 hours | pytest, sentry-sdk |
| **Later** | Scale with Celery + Redis | 4–6 hours | celery, redis |

---

## ✅ Verification

After installing new packages:

```bash
# Check imports work
python -c "import flask_limiter; import pydantic; import sentry_sdk; print('✓ All packages installed')"

# List installed versions
pip list | grep -E "flask-limiter|pydantic|sentry|pytest|black"

# Run a quick test
pytest tests/ -v --co  # Just show test names, don't run
```

---

## 📚 Resources

- **flask-limiter docs:** https://flask-limiter.readthedocs.io/
- **pydantic docs:** https://docs.pydantic.dev/
- **sentry.io setup:** https://docs.sentry.io/platforms/python/
- **pytest docs:** https://docs.pytest.org/
- **GitHub reference projects:**
  - pyspider (16.8k ⭐) — distributed crawler
  - SeleniumBase (12.7k ⭐) — browser automation
  - FastAPI (98.2k ⭐) — modern async framework

---

## 💡 Quick Reference

### Start Flask with new packages
```python
# app/server.py
import sentry_sdk
from flask_limiter import Limiter

sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"))
limiter = Limiter(app, key_func=get_remote_address)
```

### Validate API input
```python
# core/schemas.py
from pydantic import BaseModel

class IndexRunRequest(BaseModel):
    input: str
    limit: int = 20

# In route
try:
    req = IndexRunRequest(**request.json())
except ValidationError as e:
    return {"error": e.errors()}, 400
```

### Rate limit an endpoint
```python
@app.route("/api/index/run", methods=["POST"])
@limiter.limit("5 per hour")
def api_index_run():
    # ...
```

---

**Status:** Ready to install ✅  
**Next:** See RECOMMENDED_PACKAGES.md for full implementation guide
