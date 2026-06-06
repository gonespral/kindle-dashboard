# kdash — AI Agent Guide

A self-hosted Kindle e-ink dashboard with two card modes: **server cards** (Flask/Docker PNG generation on PC) and **on-device cards** (shell/Python payload on Kindle). See [HOWTO.md](HOWTO.md) for setup steps.

## Architecture

**Server** (`/server`): Flask app rendering cards as PNG images
- Card registry in `render.py` — maps card names to `Card` classes
- Cards inherit from `cards/base.py::Card` base class
- Config in `server/config.yml` — stores active card + per-card settings
- Runs in Docker via `compose.yml`

**Kindle payload** (`/payload`): KUAL menu extension for jailbroken Kindle
- Shell payload (`*.sh`) for lightweight text display via `eips`
- Python payload for graphical cards via PIL (requires Python + PIL on Kindle)
- Menu defined in `payload/menu.json`
- Fetches PNGs from server at `$SERVER_URL` or runs locally

## Key Files

| File | Purpose |
|------|---------|
| `server/render.py` | Card registry & PNG render entrypoint |
| `server/app.py` | Flask routes: `/card/active.png`, `/card/<name>.png`, `/` (GUI), `/config` (POST) |
| `server/cards/base.py` | `Card` base class: `name`, `fetch()`, `render(data, w, h)`, `font()` helper |
| `server/config.yml` | Active card + per-card settings (city, API key, etc.) |
| `server/Dockerfile` | (implicit) Builds from `./server` dir |
| `compose.yml` | Mounts Claude stats at `/data/stats-cache.json` (read-only) |
| `HOWTO.md` | Detailed user-facing setup & troubleshooting guide |

## Commands

```bash
docker compose up -d              # Start server (runs on port 4567)
docker compose logs -f            # Stream logs
docker compose up -d --build      # Rebuild after code changes
docker compose down               # Stop
```

## Adding a Server Card

1. Create `server/cards/mycard.py` implementing the `Card` base class:
   ```python
   from cards.base import Card as BaseCard
   
   class Card(BaseCard):
       name = 'mycard'
       
       def fetch(self) -> dict:
           # Fetch data (API, files, etc.)
           return {'key': value}
       
       def render(self, data: dict, w: int, h: int) -> Image.Image:
           img = self.new_image(w, h)  # 1448×1072, grayscale
           # Draw via PIL
           return img
   ```

2. Register in `server/render.py`:
   ```python
   from cards.mycard import Card as MyCard
   REGISTRY = {..., 'mycard': MyCard}
   ```

3. Add config defaults to `server/config.yml`:
   ```yaml
   mycard:
     setting_name: default_value
   ```

4. Rebuild: `docker compose up -d --build`
5. Access at `http://localhost:4567/card/mycard.png`

## Adding an On-Device Card

Create `payload/cards/mycard.sh` (or `.py` for graphical) and add a menu entry in `payload/menu.json`:
```json
{"name": "My Card", "priority": 75, "action": "/bin/sh ./stop.sh; /bin/sh ./cards/mycard.sh"}
```

## Conventions

- **Card image size**: 1448×1072 pixels, grayscale (8-bit)
- **Base class pattern**: All server cards inherit from `Card` base class; must implement `fetch()` and `render()`
- **Settings**: Per-card config in `config.yml`; accessible via `self.settings` in card instance
- **Fonts**: DejaVu fonts at `/usr/share/fonts/truetype/dejavu/` (in container); use `self.font()` helper with fallback
- **Error handling**: `render_card()` catches exceptions and returns error image; check logs for details

## Kindle Context

Requires **jailbroken Kindle** with **KUAL** + **MRPI** installed. Key environment variables in `payload/local/env.sh`:
- `SERVER_URL`: PC running the Docker server (e.g., `http://192.168.x.x:4567`)
- `REFRESH_INTERVAL`: 0 (suspend after display) or seconds to stay awake
- `WEATHER_CITY`: For on-device weather card

See [HOWTO.md](HOWTO.md) Part 0 & 2 for jailbreak and installation steps.

## Data Sources

- **claude_usage**: Claude API stats from `~/.claude/stats-cache.json` (mounted read-only into container)
- **weather**: OpenWeatherMap API (optional) or wttr.in free service
- **clock**: System time (no network needed)

## Testing

1. **Local PNG render**: `docker compose up -d` then visit `http://localhost:4567/`
2. **Preview changes**: Changes to cards auto-render on browser refresh (if compose is running)
3. **Logs**: `docker compose logs -f` — use for debugging card render errors
4. **On Kindle**: Check `extensions/kdash/logs/kdash.log` via USB if display is blank
