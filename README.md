# Macro Tracker — Web App (multi-user)

A Streamlit web app with accounts, backed by Postgres (or SQLite locally).
Each user gets a private log, targets, and custom foods; a shared base food
list is visible to everyone.

## Files
| File | Purpose |
|---|---|
| `streamlit_app.py` | The web UI (login + Log / Food Database / Targets / History tabs) |
| `db.py` | Data layer (SQLAlchemy). Uses Postgres if `DATABASE_URL` is set, else local SQLite |
| `auth.py` | Account creation + login (PBKDF2 password hashing, stdlib only) |
| `requirements.txt` | Python dependencies |
| `.streamlit/secrets.toml.example` | Template for your database secret |
| `.gitignore` | Keeps the local DB and real secrets out of git |

---

## Run it locally first (SQLite, no setup)
```bash
conda activate macrotracker      # or any env with python 3.10+
pip install -r requirements.txt
streamlit run streamlit_app.py
```
It opens at http://localhost:8501. With no `DATABASE_URL`, it creates a local
`macro.db` SQLite file — perfect for trying it out. Create an account and click around.

---

## Deploy so you can reach it from any device

You'll wire up three free things: **GitHub** (code) → **Supabase** (database) →
**Streamlit Community Cloud** (hosting + public URL).

### 1. Put the code on GitHub
```bash
cd webapp
git init
git add .
git commit -m "Macro tracker web app"
# create an empty repo on github.com first, then:
git remote add origin https://github.com/YOURNAME/macro-tracker.git
git branch -M main
git push -u origin main
```
`.gitignore` already prevents your real secrets and local DB from being pushed.

### 2. Create a free Postgres database (Supabase)
1. Sign up at supabase.com → **New project** (free tier is fine).
2. Set a database password when prompted (save it).
3. After it provisions: **Project Settings → Database → Connection string → URI**.
4. Copy the URI. It looks like:
   `postgresql://postgres:[PASSWORD]@db.xxxx.supabase.co:5432/postgres`
   Replace `[PASSWORD]` with the password you set.

> Neon (neon.tech) works identically if you prefer it — just grab its connection string.

### 3. Deploy on Streamlit Community Cloud
1. Go to share.streamlit.io → sign in with GitHub → **New app**.
2. Pick your repo, branch `main`, main file `streamlit_app.py`.
3. Before deploying, open **Advanced settings → Secrets** and paste:
   ```toml
   DATABASE_URL = "postgresql://postgres:YOUR-PASSWORD@db.YOURPROJECT.supabase.co:5432/postgres"
   ```
4. Deploy. You'll get a public URL like `https://your-app.streamlit.app` that
   works on your phone, laptop, anywhere. Tables and base foods are created
   automatically on first load.

Every `git push` after this auto-redeploys the app.

---

## Notes & honest caveats
- **Auth scope**: the built-in login (salted PBKDF2 hashing) is fine for you and
  a few friends. If this ever becomes public or larger, switch to a managed auth
  provider (Supabase Auth, Auth0) rather than hand-rolled accounts — it handles
  email verification, password resets, rate-limiting, etc., which this does not.
- **Free-tier sleeping**: Streamlit Community Cloud may idle your app after
  inactivity; the first visit then takes ~30s to wake. Fine for personal use.
- **HTTPS**: Streamlit Cloud serves over HTTPS by default, so logins aren't sent
  in the clear.
- **GitHub Student perks**: your education pack also includes credits for
  Render/DigitalOcean/Azure if you later want a FastAPI backend + custom domain.
  Not needed for this Streamlit setup, but there if you outgrow it.
- **This is not medical advice** — it's a tracking tool; the numbers are planning
  estimates.
