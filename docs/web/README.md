# docs/web

Static site files for Little Wolf Acres web properties.

## Structure

```
docs/web/
  index.html          — littlewolfacres.com landing page
  lwa.jpg             — brand image (not committed — deploy manually)
  mythic/
    index.html        — mythicamps.com landing page
    mythic_coming.png — coming soon image (not committed — deploy manually)
```

## Deployment

**littlewolfacres.com** — upload `index.html` + `lwa.jpg` to Ionos webspace root via SFTP

**mythicamps.com** — upload `mythic/index.html` + `mythic/mythic_coming.png` to Ionos `/mythic` directory via SFTP

Binary assets (jpg, png) are gitignored — manage them manually.
These directories will eventually move to their own repositories.

## Local preview

```bash
cd docs/web
python3 -m http.server 8080
# littlewolfacres: http://localhost:8080
# mythicamps:      http://localhost:8080/mythic/
```
