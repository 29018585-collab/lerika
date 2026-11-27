# ЛериКа V5.24 — повторный независимый аудит
Целевой код: **V5.23**, commit `33f310765162275842005fd9c530dd4d36bb3290`, tree `d3f2d16386ec9e76413bff3393ebad31f4d0ec59`.
Рабочий сервис: https://lerika-cabinet.onrender.com/showroom/ .
Это задание на повторную проверку, не утверждение независимого результата. Не использовать ключи, пароли или реальные данные. Не отправлять заявки, не менять прайс, не удалять записи на production. Воспроизводить дефекты на disposable SQLite/PostgreSQL 17 и локальном Chromium; результаты оформлять с доказательствами.

## Evidence
- PR #16 / V5.20: https://github.com/29018585-collab/lerika/pull/16 ; run 46077680473, ingress 46077649758.
- PR #17 / V5.21: https://github.com/29018585-collab/lerika/pull/17 ; run 46078671090, smoke 46080944312.
- PR #18 / V5.22: https://github.com/29018585-collab/lerika/pull/18 ; run 46080614113, smoke 46081328733.
- PR #19 / V5.23: https://github.com/29018585-collab/lerika/pull/19 ; run 46082680892.
- V5.23 CI: 5 jobs success; SQLite + PG17 29 PASS + 1 intentional backend skip each; 17 room core, 20 engineering core; 48 DXF independent parser; 112 ray-oracle views, 1806336 pixels, zero owner mismatches; mobile 320–1280, zoom, estimate, admin search, 16 decoded WebPs, deterministic image assets.

## Original 30 defects: re-test independently
| ID | Expected corrected behavior | Critical verification / remaining caveat |
|---|---|---|
| 001 | Sender-local order/design quota | Distinct senders; shared endpoint quota; forged headers; CAPTCHA/file-volume quota/alerts are additional defenses not implemented |
| 002 | Admin login sender-local limit | Wrong password from A cannot block B; 2FA/exponential delay not implemented |
| 003 | Client registration/login sender and sender+email | Test different IP/same email; deliberate decision not to use global email-only lockout |
| 004 | Shared per-pixel z-buffer | Independent ray oracle; bed/table/hall/kitchen/open hinges; picking |
| 005 | Explicit part roles in estimate | Material change leaves priced body area intact |
| 006 | Autosave room and immediate reload | Manual checkpoint separate; test storage blocked and corrupted state |
| 007 | Authorized confirmed deletion incl client records/files | Hard delete tested; audit trail/soft deletion not implemented |
| 008 | Validated configurable HTTPS origins | Synthetic domain tests; real custom DNS/TLS not provisioned |
| 009 | No duplicate base64 WebP; immutable static assets | Only static hashed assets cache; private/revocable DB photos stay no-store |
| 010 | Grain-aware packing | Verify sheet axis and material grain assumption with production |
| 011 | Body/top totals separated | Price exact from shown priced groups |
| 012 | Headboard uses front rate | Bed dimensions unchanged |
| 013 | valid/build consistency | Field-specific reason still generic |
| 014 | DXF physical panels, hidden and visible layers | Sketch documentation, not fabrication drawings |
| 015 | Intake cannot be published | Server enforces; verify media and covers |
| 016 | CSV/XLSX tolerant import | Cached formula result required; reject invalid row without changing price |
| 017 | Instructions match buttons | Test all lab routes and admin guide |
| 018 | Honest studio title | No claim of AI interior generation; real AI generation out of scope |
| 019 | Partial collection recovery | Backup raw original before overwrite; malformed/duplicate rows and quota error |
| 020 | Stable L-number and old prefix search | Retry, concurrency, migration, deletion and no number reuse; old UUID retained |
| 021 | 2D and 3D movement constraints | Wall, overlap, opening; input fields may temporarily show invalid geometry for correction but exports gated |
| 022 | Admin/client session isolation | Login/logout both directions |
| 023 | Legs clear plinth | Verify minimum dimensions and feet options |
| 024 | Shelf label dynamic | 0–8 and singular/plural |
| 025 | Cropped/optimized public photos and covers | Original public sources retained, actual 1080x1400 and 1080x1020 crops, five existing cover viewports; not new originals |
| 026 | RU decimal commas in CSV | Test both estimate and engineering exports |
| 027 | SQLite connection closure | Rollback and PG parity |
| 028 | Current visible version, corrected documentation | Technical compatibility labels intentionally retained |
| 029 | Accurate estimate intake source | Config / 3D / mixed collection / room, admin filter |
| 030 | Integer geometry validation | Fractional dimension rejects save, correct input restores |

## Fresh checks before closing audit
1. Run supplied CI; reproduce original 30 cases independently; report any contradiction or regression, not only count of green existing tests.
2. Check request number migration on a disposable pre-V5.23 schema with historical synthetic requests, simultaneous requests and repeat delivery; preserve ids, private files and prices.
3. Check security after new Origin handling under reverse proxy; no spoofed Host reflection, no cross-origin write, no credentials leaked; verify origin alias semantics.
4. Check rendered image quality and actual network/cache headers, illumination, public HTML/CSP. Review real mobile Safari/Firefox separately; Chromium only confirmed so far.
5. Check full-size performance of software raster on modest mobile devices, especially many products in a room; current independent oracle uses 144x112 samples.
6. Re-evaluate the audit's additional risks: shared admin credential/2FA, password recovery, email verification, session revocation, storage/backup limits, notifications, rate limits, production grain/material/price policy. Do not equate remediation of original repro with resolution of every recommendation.
7. For each issue: PASS / FAIL / PARTIAL / NOT TESTED; exact reproduction, expected/actual, files, logs or screenshots, severity and minimal fix. No production changes during audit.

## Release / backup
Neon project solely LERIKA Cabinet; previous manual snapshot retained, verified restore. Free snapshot limit prevented creating a second manual snapshot. Pre-V5.23 separate branch copy `br-wispy-bar-bhj62slw` verified ready and equal row counts across eight business tables; not a new independent manual snapshot. No paid upgrade, no production data written by QA.
Only this LeriKa repository/service is in scope. FurnitureAI, Smeta Bot and ALEX KEE are excluded. Telegram assistant comes after the independent audit.
