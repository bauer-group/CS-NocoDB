## [0.6.4](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.3...v0.6.4) (2026-02-09)

### 🐛 Bug Fixes

* entferne die Funktion zur automatischen Behebung von Kollationsmismatches und verbessere die Fehlerberichterstattung ([ae2b0d5](https://github.com/bauer-group/CS-NocoDB/commit/ae2b0d5f6838a6a1741b80cd9951aa76d5d91aae))

## [0.6.3](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.2...v0.6.3) (2026-02-09)

## [0.6.2](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.1...v0.6.2) (2026-02-08)

### 🐛 Bug Fixes

* aktualisiere SMTP-Konfiguration für E-Mail-Benachrichtigungen und verbessere Fehlerbehandlung ([d36980e](https://github.com/bauer-group/CS-NocoDB/commit/d36980ed4b8ada3db3c33d681cd45c6b46f4f2b3))

## [0.6.1](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.0...v0.6.1) (2026-02-08)

### 🐛 Bug Fixes

* Korrigiere Schreibfehler in den deutschen Kommentaren und Dokumentationen ([0e44ac4](https://github.com/bauer-group/CS-NocoDB/commit/0e44ac4edf4600c8fed1b0de5960c45828e3ca36))

## [0.6.0](https://github.com/bauer-group/CS-NocoDB/compare/v0.5.0...v0.6.0) (2026-02-08)

### 🚀 Features

* Add audit cleanup task and update environment configurations ([6d43d0b](https://github.com/bauer-group/CS-NocoDB/commit/6d43d0bb31d97f6b2e3d8a1d5901f23dd20bac32))
* Add file_backup_size to alerting classes and update summary outputs ([4600c54](https://github.com/bauer-group/CS-NocoDB/commit/4600c54d885ec4ec29c9b24f57c1ed3e43554150))
* add PG_USER and PG_DATABASE variables for pg_upgrade script ([220c3cb](https://github.com/bauer-group/CS-NocoDB/commit/220c3cbcc1733a29f19a14960225c20ffec76c99))
* Add restore-schema command for recreating table schemas from backup ([bce5815](https://github.com/bauer-group/CS-NocoDB/commit/bce5815bc5045f226ca704da6e1ecbc308566dac))
* Implement S3 storage module for backup management ([4f6463d](https://github.com/bauer-group/CS-NocoDB/commit/4f6463d387d52672ddbff78b61036903def3d7aa))
* Increase DB_MAX_POOL_SIZE from 45 to 48 for improved connection handling ([b80bfbc](https://github.com/bauer-group/CS-NocoDB/commit/b80bfbce4caf9031ebc499ed3d6faeb56acb1f93))
* Update Docker configurations for NocoDB, including base images and workflows ([e42a28b](https://github.com/bauer-group/CS-NocoDB/commit/e42a28b4e7b802dc22e433370f1e4a90ea282fef))
* update pg_upgrade_inplace.sh to support hardlink mode and improve error handling ([c71b308](https://github.com/bauer-group/CS-NocoDB/commit/c71b308ab843ab82f4abc3901a94cd13671c9971))

## [0.5.0](https://github.com/bauer-group/CS-NocoDB/compare/v0.4.0...v0.5.0) (2026-02-05)

### 🚀 Features

* enhance pg_upgrade_inplace.sh with error handling and user-configurable variables ([e5ed413](https://github.com/bauer-group/CS-NocoDB/commit/e5ed413fd32960739b62372b4d0b12a9936355ce))

## [0.4.0](https://github.com/bauer-group/CS-NocoDB/compare/v0.3.0...v0.4.0) (2026-02-03)

### 🚀 Features

* remove private subnet configuration from environment and Docker Compose files ([c36a684](https://github.com/bauer-group/CS-NocoDB/commit/c36a6844addf972e70140a560ad93f7ab067ed8d))

## [0.3.0](https://github.com/bauer-group/CS-NocoDB/compare/v0.2.0...v0.3.0) (2026-01-29)

### 🚀 Features

* update Traefik middleware to use 'ipAllowList' for v3 compatibility ([e137d93](https://github.com/bauer-group/CS-NocoDB/commit/e137d934b0ffdb32703b17e1706c5cd8db782835))

## [0.2.0](https://github.com/bauer-group/CS-NocoDB/compare/v0.1.0...v0.2.0) (2026-01-25)

### 🚀 Features

* increase database connection pool size and max connections in Docker configurations ([f66583e](https://github.com/bauer-group/CS-NocoDB/commit/f66583e8bbbad321e668e86c1b23ff708cf454e0))

## [0.1.0](https://github.com/bauer-group/CS-NocoDB/compare/v0.0.0...v0.1.0) (2026-01-25)

### 🚀 Features

* Initial Commit ([8e93507](https://github.com/bauer-group/CS-NocoDB/commit/8e93507ca2a860c0fd57de71cdd108adaa800958))
