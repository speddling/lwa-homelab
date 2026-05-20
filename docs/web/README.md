# docs/web

Static site files for littlewolfacres.com.

## Files

- `index.html` — landing page
- `lwa.jpg` — brand image (kid's cat drawing) — **not committed to repo, deploy manually**

## Deployment

Upload contents of this directory to the Ionos webspace root via FTP/SFTP.
This directory will eventually move to its own repository.

## Local preview

```bash
cd docs/web
python3 -m http.server 8080
# open http://localhost:8080
```
