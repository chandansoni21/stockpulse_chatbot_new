# Fabric Data Agent Chat UI

This folder contains the React + Tailwind UI for the Fabric Data Agent backend.

## Run locally

1. Install dependencies:

```bash
npm install
```

2. Copy `.env.example` to `.env` if you need to customize the backend URL.

```bash
cp .env.example .env
```

3. Start the UI:

```bash
npm run dev
```

4. Start the backend from the `fabric_data_agent_client` folder:

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

5. Open the app at `http://localhost:5173`.
