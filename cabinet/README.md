# LERIKA Cabinet V1 — isolated development branch

Public site main is unchanged. The cabinet is a separate HTTPS service, not a password gate implemented in static HTML.

## Deployment prerequisites
- Separate hosting service, persistent disk mounted at /data, HTTPS domain. Do not use existing FurnitureAI or Content Factory services. Hosting and persistent volume may cost money; verify before provisioning.
- Root directory: cabinet. Dockerfile is included.
- Set secret environment variables SESSION_SECRET (32+ random characters) and ADMIN_PASSWORD_HASH (Werkzeug scrypt hash). Never commit credentials. Generate them in a trusted local shell: python -c "import secrets; print(secrets.token_urlsafe(48))" and python -c "from werkzeug.security import generate_password_hash; import getpass; print(generate_password_hash(getpass.getpass()))".
- Run only after persistent storage is mounted; regular backups of the database are required. No uploads to the public GitHub repository from the cabinet.
- Health endpoint /health, cabinet at /. A single shared administrator account is supported in V1; individual accounts and recovery are not implemented.
- HTTPS required; cookie is Secure, HttpOnly, SameSite Strict. Eight failed logins in 15 minutes temporarily lock the shared login. CSRF token required for authenticated writes.
- Uploads default private; only decoded and re-encoded raster photos can be explicitly approved. Documents cannot be publicly served. Public project description must be reviewed manually for personal data. File limit 12 MiB, total 500 MiB.

## Public site connection
After successful deployment and security tests, set the lerika-portfolio-api meta tag in index.html to the HTTPS service origin, then publish the tested index.html and portfolio-api.js to main. CORS allows the existing GitHub Pages origin. Existing catalogue is the fallback and remains unchanged until connection. Existing static project cases have not yet been imported into the cabinet database. New published cases appear alongside them. Migrate existing cases before removing the fallback entries.

## Checks
Run python -m unittest -v test_privacy from cabinet; node --check static/admin.js and node --check ../portfolio-api.js. Test on mobile with a temporary password and test photos before production. Verify persistent data across redeploy, backup/restore, logout and denied anonymous document access. No real client documents during testing.

## Not yet deployed
No Railway service, domain, credentials, persistent volume or production API has been provisioned. No login URL is currently active. No live publication from cabinet until deployment and configuration.