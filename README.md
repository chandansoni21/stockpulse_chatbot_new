# Stock Pulse Agent

React + FastAPI chat UI for Microsoft Fabric Data Agents.

## Architecture for production

| Part | Host | Why |
|------|------|-----|
| **Frontend** | [Vercel](https://vercel.com) | Static Vite build, GitHub auto-deploy |
| **Backend** | [Railway](https://railway.app) or [Render](https://render.com) | FastAPI + long chat requests (up to 5 min) |

Vercel cannot run this Python backend reliably (serverless timeout ~60s; chat needs up to 300s).

---

## 1. Push to GitHub

```bash
git add .
git commit -m "Add Vercel and backend deployment config"
git push origin main
```

Do **not** commit `.env` files, `node_modules/`, `venv/`, or `backend/.auth_sessions.json`.

---

## 2. Deploy backend (Railway)

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Select this repo → set **Root Directory** to `backend`
3. Railway detects the `Dockerfile` automatically
4. Add environment variables (Settings → Variables):

| Variable | Example |
|----------|---------|
| `AZURE_AUTHORITY` | `common` |
| `AZURE_CLIENT_ID` | your Azure app client ID |
| `TENANT_ID` | your tenant ID |
| `FABRIC_TOKEN_MODE` | `delegated` |
| `AUTH_SESSION_DAYS` | `7` |

5. Deploy → copy the public URL (e.g. `https://stockpulse-api.up.railway.app`)
6. Verify: open `https://YOUR-BACKEND-URL/health` → should return `{"status":"ok"}`

**Render alternative:** connect repo on Render; it reads `render.yaml` at repo root.

---

## 3. Deploy frontend (Vercel)

1. Go to [vercel.com](https://vercel.com) → **Add New Project** → import GitHub repo
2. Vercel reads `vercel.json` at repo root (builds `frontend/`)
3. Add environment variables (Settings → Environment Variables):

| Variable | Value |
|----------|-------|
| `VITE_API_URL` | `https://YOUR-BACKEND-URL` (no trailing slash) |
| `VITE_AZURE_CLIENT_ID` | same as backend `AZURE_CLIENT_ID` |
| `VITE_AZURE_AUTHORITY` | `common` (or your tenant) |
| `BACKEND_URL` | same as `VITE_API_URL` (optional fallback for `/api` proxy) |

4. Deploy

**Important:** set `VITE_API_URL` to the backend URL so chat requests go directly to Railway (not through Vercel’s 60s proxy limit).

---

## 4. Azure app registration

In [Azure Portal](https://portal.azure.com) → App registrations → your app → **Authentication**:

Add **Redirect URIs** (type: Single-page application):

- `https://YOUR-APP.vercel.app`
- `https://fabric_agent.com` (if using custom domain from `CNAME`)

Enable: **Access tokens**, **ID tokens**, **Allow public client flows**.

---

## 5. Custom domain (optional)

- **Vercel:** Project → Settings → Domains → add `fabric_agent.com`
- **DNS:** point CNAME to `cname.vercel-dns.com` (Vercel will show exact value)

---

## Local development

```bash
# Terminal 1 – backend
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env         # fill in values
uvicorn app:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 – frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Sign-in loop | Add Vercel URL to Azure redirect URIs; redeploy after setting env vars |
| Chat timeout on Vercel | Set `VITE_API_URL` to backend URL (direct call, not `/api` proxy) |
| 401 after sign-in | Sign out → hard refresh → sign in again (fresh session + refresh token) |
| Wrong user on another device | Fixed: each browser has its own `X-Auth-Session-Id` session |
