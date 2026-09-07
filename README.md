# Hail Mary NFL Projections

Real, from-scratch NFL fantasy projections for FanTeam's "NFL Regular Season
2026/27" tournament. Standalone project - see [CLAUDE.md](CLAUDE.md) for
scope, scoring rules, data sources, and the model design.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in the real DB password and service role key
python scripts/run_migration.py
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```
