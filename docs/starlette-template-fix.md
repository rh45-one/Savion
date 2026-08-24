# Starlette `TemplateResponse` production fix

## What failed

Starlette 1.0 removed the deprecated `TemplateResponse(name, context)` call
signature. Savion used that old positional signature. On a clean Docker build,
the broad dependency ranges in `requirements.txt` allowed pip to install a new
FastAPI/Starlette combination even though the application source had not
changed.

With the new signature, Starlette interpreted Savion's context dictionary as
the template name. Jinja then attempted to use that dictionary in its template
cache key and raised:

```text
TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')
```

The source fix changes all template responses to explicit arguments:

```python
templates.TemplateResponse(
    request=request,
    name="index.html",
    context={...},
)
```

Direct runtime dependency versions are now pinned so that future clean builds
do not silently select a different framework API. Dependency upgrades should
be made deliberately and tested by rebuilding the container.

No data format changed. `ledger.jsonl` and `settings.json` do not need a
migration.

## Before deploying

Run the following on the server from a shell with Docker access. Replace
`/path/to/savion` with the actual repository directory.

First confirm that `/data` is backed by a Docker volume or bind mount:

```bash
docker inspect savion --format '{{range .Mounts}}{{println .Type .Name .Source "->" .Destination}}{{end}}'
```

The output must contain a mount ending in `-> /data`. Do not replace the
container until that is true; otherwise its ledger may exist only in the
container layer.

Make a backup independent of the container:

```bash
SAVION_BACKUP_DIR="/var/backups/savion/$(date +%Y%m%d-%H%M%S)"
sudo mkdir -p "$SAVION_BACKUP_DIR"
sudo docker cp savion:/data/. "$SAVION_BACKUP_DIR/"
sudo ls -la "$SAVION_BACKUP_DIR"
```

The backup should contain `ledger.jsonl` and `settings.json` for an initialized
installation.

Choose exactly one of the deployment methods below.

## Method A: build from the repository on the server

Use this method when the server has a Git checkout and its Compose file uses
`build: .`, as the Compose file in this repository does.

```bash
cd /path/to/savion
git status --short
git pull --ff-only
docker compose build --pull savion
docker compose up -d --no-deps --force-recreate savion
```

If `git status --short` reports server-side source changes, stop and resolve or
back them up before pulling. Do not discard them blindly.

## Method B: deploy the prebuilt Docker Hub image

Use this only after the GitHub Actions build containing this fix has completed
and pushed `rh45one/savion:latest`.

For a server Compose file that uses `image: rh45one/savion:latest`:

```bash
cd /path/to/the/server-compose-directory
docker compose pull savion
docker compose up -d --no-deps --force-recreate savion
```

For a container originally started with `docker run`, preserve the old
container temporarily for an easy rollback:

```bash
docker pull rh45one/savion:latest
docker stop savion
docker rename savion savion-before-template-fix
docker run -d \
  --name savion \
  --restart unless-stopped \
  -p 8000:8000 \
  -e DATA_DIR=/data \
  -v savion_data:/data \
  rh45one/savion:latest
```

If the old container used different ports, environment variables, bind mounts,
network settings, or a differently named volume, reproduce those settings
instead of copying the example unchanged. `docker inspect
savion-before-template-fix` shows the old configuration.

## Verify the deployment

Check the process and installed framework versions:

```bash
docker ps --filter name=savion
docker exec savion python -c "import fastapi, starlette; print('FastAPI', fastapi.__version__); print('Starlette', starlette.__version__)"
```

Check the health endpoint and a template-rendering route:

```bash
curl -fsS http://127.0.0.1:8000/healthz
curl -sS -o /dev/null -w 'Home page: HTTP %{http_code}\n' http://127.0.0.1:8000/
docker logs --tail 100 savion
```

Expected results:

- `/healthz` returns `{"status":"ok"}`.
- `/` returns HTTP 200 for an initialized installation, or a redirect to
  `/setup` for a new installation.
- The logs contain no `TypeError`, `unhashable type: 'dict'`, or new traceback.

Also load the site through its normal public URL and test the home, setup,
settings, reset, and summary pages as applicable. The reset page should only be
viewed; do not submit the reset form as a test.

The `/favicon.ico` 404 may remain. It is unrelated to the server error.

## Rollback

The data backup and `/data` volume are compatible with both versions.

If Method B preserved the old container, roll back with:

```bash
docker stop savion
docker rm savion
docker rename savion-before-template-fix savion
docker start savion
```

For Method A, check out the previously deployed commit and rebuild it, or deploy
the previous known-good image tag. Remember that rebuilding the old source with
unrestricted dependencies recreates the original failure; a temporary old-code
rollback also needs `starlette<1.0`.

After the fixed container has run successfully long enough to satisfy the
normal rollback window, the preserved old container can be removed:

```bash
docker rm savion-before-template-fix
```
