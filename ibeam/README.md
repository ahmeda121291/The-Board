# IBeam — unattended IBKR gateway

The IBKR Client Portal Gateway session **expires daily / on inactivity**, so the
manual `bin\run.bat` approach needs a re-login before every checkpoint. IBeam
([voyz/ibeam](https://github.com/voyz/ibeam)) runs the gateway in Docker and keeps
it logged in automatically, so the Directional leg is reliably available.

It serves the same API on `https://localhost:5000`, so **Boardroom needs no
change** — `IBKR_GATEWAY_URL` stays the default.

## One-time setup

1. Install **Docker Desktop** and make sure it's running.
2. From this folder:
   ```powershell
   cd C:\Users\Aawad\The-Board\ibeam
   copy env.list.example env.list
   notepad env.list        # put in IBEAM_ACCOUNT + IBEAM_PASSWORD, save
   ```
3. If the manual gateway window is still open, **close it** (frees port 5000).
4. Start IBeam:
   ```powershell
   docker compose up -d
   docker compose logs -f      # watch until you see it authenticated; Ctrl+C to stop watching
   ```
5. Confirm it's live:
   ```powershell
   cd ..
   .\.venv\Scripts\python -m boardroom.cli preflight
   ```
   The IBKR venue should show **reachable**.

## 2FA reality

IBeam can't magic past two-factor auth:

- **Paper account (`DU…`)** — no 2FA, fully unattended. Recommended for
  validating the system first.
- **Live account with IB Key** — IBeam triggers a push to your phone on each
  (re)login; approve it. Mostly hands-off, not 100%.

## Day to day

- `docker compose up -d` — start (auto-restarts on reboot via `restart: unless-stopped`).
- `docker compose logs -f` — see auth status.
- `docker compose down` — stop.

`env.list` is gitignored — your password never leaves your machine.
