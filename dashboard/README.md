# Boardroom Dashboard

A read-only Next.js dashboard over the Boardroom Supabase `boardroom` schema.
Shows the CEO's latest decision + rationale, per-division calibration & leashes,
ROI vs the floor and vs buy-and-hold, per-division attribution, the decision log,
recent pitches, resolved outcomes, the weekly readout, and the audit log.

It reads Supabase **server-side** with the service key — the key never reaches
the browser. Pages are dynamic (always fresh).

## Local dev

```bash
cd dashboard
npm install
cp .env.example .env.local   # add SUPABASE_SERVICE_KEY
npm run dev                  # http://localhost:3000
```

## Deploy on Vercel

Import the repo at vercel.com, set **Root Directory = `dashboard`**, and add two
Environment Variables:

- `SUPABASE_URL` = `https://qyaekaifodgiaxyztpdt.supabase.co`
- `SUPABASE_SERVICE_KEY` = your Supabase `service_role` key

Vercel auto-detects Next.js and redeploys on every push. The dashboard shows
empty states until Boardroom logs its first decisions.
