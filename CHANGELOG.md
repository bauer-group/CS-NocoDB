# Changelog

All notable changes to this project are documented here. This file is maintained
automatically by [semantic-release](https://github.com/semantic-release/semantic-release)
on every release to `main`.

## [1.0.7](https://github.com/bauer-group/CS-NocoDB/compare/v1.0.6...v1.0.7) (2026-10-09)

### 🐛 Bug Fixes

* **backup:** counted attachments per table in the export manifest ([00fe435](https://github.com/bauer-group/CS-NocoDB/commit/00fe43574be6271e0f3f0bbf43d3c82dc6fe3a4a))
* **backup:** emptied the Redis cache after a cluster database restore ([006568f](https://github.com/bauer-group/CS-NocoDB/commit/006568f39cf6497375997076d702ea9af851b816))
* **backup:** kept same-title attachments apart in the REST export ([8cc6f51](https://github.com/bauer-group/CS-NocoDB/commit/8cc6f517506a41623721bff7740b94e8e75c26bc))
* **backup:** named the real export switch when a restore finds none ([7f71881](https://github.com/bauer-group/CS-NocoDB/commit/7f71881f4d39b7ed51162c7a8e3bd5b51c63a137))

### 🔧 Maintenance

* update Dockerfile version to 1.0.6 ([884aa2e](https://github.com/bauer-group/CS-NocoDB/commit/884aa2ea995b67e378cf4b9d4ffd212b0ae12b3d))
* update Dockerfile version to 1.0.6 ([9260468](https://github.com/bauer-group/CS-NocoDB/commit/9260468c2ce562e3d9d7dd7ec909a3dfd274c04d))
* update Dockerfile version to 1.0.6 ([87f590a](https://github.com/bauer-group/CS-NocoDB/commit/87f590a2678fe911a06056bbd40e0d9268e9aa8a))

## [1.0.6](https://github.com/bauer-group/CS-NocoDB/compare/v1.0.5...v1.0.6) (2026-10-08)

### 🔧 Maintenance

* **deps:** update base image backuphelper [skip ci] ([7b5d1a1](https://github.com/bauer-group/CS-NocoDB/commit/7b5d1a182f2ec2912e60f5a735d652223cdf2ac9))
* update Dockerfile version to 1.0.5 ([241d076](https://github.com/bauer-group/CS-NocoDB/commit/241d0768b56052e79088f87c0f03bbfa8da07a76))
* update Dockerfile version to 1.0.5 ([20ec0d9](https://github.com/bauer-group/CS-NocoDB/commit/20ec0d90d36e40e690484747e8cec7c90e8dff39))
* update Dockerfile version to 1.0.5 ([ef8f7ac](https://github.com/bauer-group/CS-NocoDB/commit/ef8f7acfe315d7283e2ce62e34632b400b9eb781))

## [1.0.5](https://github.com/bauer-group/CS-NocoDB/compare/v1.0.4...v1.0.5) (2026-10-08)

### 🐛 Bug Fixes

* **backup:** exported attachments stored by the Local adapter ([041f5ec](https://github.com/bauer-group/CS-NocoDB/commit/041f5ec68977f34b3d7047dc912ce6a4215c99d6))
* **backup:** gave the alert mail its own STARTTLS port and switch ([7ab4ec0](https://github.com/bauer-group/CS-NocoDB/commit/7ab4ec0e596e334564fd2fb27d4cf24e8bdb98f8))
* **backup:** ran the sidecar as root to restore the data volume ([65797eb](https://github.com/bauer-group/CS-NocoDB/commit/65797ebe780c931aefe59022a0d0e2a6c6100754))
* **backup:** reported failed REST requests instead of hiding them ([f2416c9](https://github.com/bauer-group/CS-NocoDB/commit/f2416c9dc39f58b18f8e99ce48b72a8d99bcd0f9))
* **backup:** sent the NocoDB API token only to NocoDB itself ([7069e50](https://github.com/bauer-group/CS-NocoDB/commit/7069e50005da606dbe8fa2c199da7d97acb9d80e))
* **backup:** switched the database dump to the custom format ([6e4e0d2](https://github.com/bauer-group/CS-NocoDB/commit/6e4e0d2c651c8a1abc566f5f65009d19029d7adc))

### 🔧 Maintenance

* update Dockerfile version to 1.0.4 ([e8ed27c](https://github.com/bauer-group/CS-NocoDB/commit/e8ed27c46be1c65525a5549722baf88fcc1c7e33))
* update Dockerfile version to 1.0.4 ([bc0091a](https://github.com/bauer-group/CS-NocoDB/commit/bc0091a4cc26257af532d727dda6e9b2e92915d1))
* update Dockerfile version to 1.0.4 ([f6bb8da](https://github.com/bauer-group/CS-NocoDB/commit/f6bb8da1af1d7b55a44173d6d17e5405c7300fe2))

## [1.0.4](https://github.com/bauer-group/CS-NocoDB/compare/v1.0.3...v1.0.4) (2026-10-07)

### 🔧 Maintenance

* **deps:** update base image backuphelper ([633fbf3](https://github.com/bauer-group/CS-NocoDB/commit/633fbf364097c54623d8659a017b73447e5789ec))
* update Dockerfile version to 1.0.3 ([e0a5164](https://github.com/bauer-group/CS-NocoDB/commit/e0a516430d33a54840d860c69384ef74140ed5ed))
* update Dockerfile version to 1.0.3 ([8ad7a38](https://github.com/bauer-group/CS-NocoDB/commit/8ad7a38df43e200a81cfb2dad21f3f924ef789db))
* update Dockerfile version to 1.0.3 ([55b119a](https://github.com/bauer-group/CS-NocoDB/commit/55b119aefe97f4f1a1bc261a2ad76d7e71397c3c))

## [1.0.3](https://github.com/bauer-group/CS-NocoDB/compare/v1.0.2...v1.0.3) (2026-10-03)

### 🔧 Maintenance

* **deps:** update base image backuphelper ([ffba8fb](https://github.com/bauer-group/CS-NocoDB/commit/ffba8fbf277405330425255632e018e63dfaf595))
* update Dockerfile version to 1.0.2 ([c7da56e](https://github.com/bauer-group/CS-NocoDB/commit/c7da56e05a27f9fda9a99e17f045044087b00dfb))
* update Dockerfile version to 1.0.2 ([7438ba1](https://github.com/bauer-group/CS-NocoDB/commit/7438ba1b5d3f2d41034a8a3df43f238f8457d0cd))
* update Dockerfile version to 1.0.2 ([8b007f9](https://github.com/bauer-group/CS-NocoDB/commit/8b007f9344a9ec8394db4b5e3bdf31cea998b66f))

## [1.0.2](https://github.com/bauer-group/CS-NocoDB/compare/v1.0.1...v1.0.2) (2026-10-02)

### 🔧 Maintenance

* **deps:** update base image python-alpine ([934fbee](https://github.com/bauer-group/CS-NocoDB/commit/934fbee346313c88a0ea35380a36ec443cbe4565))
* update Dockerfile version to 1.0.1 ([f568bc1](https://github.com/bauer-group/CS-NocoDB/commit/f568bc11cc4ae2da01c557b093703bda36dd90ab))
* update Dockerfile version to 1.0.1 ([27882cf](https://github.com/bauer-group/CS-NocoDB/commit/27882cf7e35659d922bf69cfaaf0f63842405778))

## [1.0.1](https://github.com/bauer-group/CS-NocoDB/compare/v1.0.0...v1.0.1) (2026-09-29)

### 🔧 Maintenance

* **ci:** removed issue AI summary workflow ([6e14167](https://github.com/bauer-group/CS-NocoDB/commit/6e14167d5b94d3a4b494fc8e3f061919334c08a9)), references [bauer-group/automation-templates#105](https://github.com/bauer-group/automation-templates/issues/105)
* **deps:** update base image nocodb ([fef6490](https://github.com/bauer-group/CS-NocoDB/commit/fef6490123a5d091c899ab25c7945987ecaacbf7))
* update Dockerfile version to 1.0.0 ([e63137b](https://github.com/bauer-group/CS-NocoDB/commit/e63137b9b1eb0d326d08a6ef43c919d51ec73be1))
* update Dockerfile version to 1.0.0 ([ca4c3f0](https://github.com/bauer-group/CS-NocoDB/commit/ca4c3f076e935c50fdf3b6cedacdadfa03270253))
* update Dockerfile version to 1.0.0 ([bea5dcf](https://github.com/bauer-group/CS-NocoDB/commit/bea5dcf96fb85921e5b5d34c01e60ab19e35ea44))

## [1.0.0](https://github.com/bauer-group/CS-NocoDB/compare/v0.8.10...v1.0.0) (2026-09-19)

### ⚠ BREAKING CHANGES

* **compose:** local and traefik-local deployments must set
  NC_SITE_URL in .env before the next "docker compose up -d". The
  value is the URL as the browser calls it, including the scheme -
  https when a TLS-terminating proxy sits in front, even though the
  stack itself speaks plain HTTP.

### 🐛 Bug Fixes

* **compose:** added NC_TRUST_PROXY to all deployment modes ([5dceefa](https://github.com/bauer-group/CS-NocoDB/commit/5dceefac6438b6a813fbcb82dd63a07c0de66d11))
* **compose:** made NC_SITE_URL mandatory in local and traefik-local ([4b5f6d3](https://github.com/bauer-group/CS-NocoDB/commit/4b5f6d33c7446b87b725940dab8ae1d902769f47))

### 🔧 Maintenance

* update Dockerfile version to 0.8.10 ([f4e3c7d](https://github.com/bauer-group/CS-NocoDB/commit/f4e3c7de0076656555b9266be523790456fc5fdf))
* update Dockerfile version to 0.8.10 ([ba13d7d](https://github.com/bauer-group/CS-NocoDB/commit/ba13d7d84535b3cf851ebae96cd03cad6444b32f))
* update Dockerfile version to 0.8.10 ([fbb6279](https://github.com/bauer-group/CS-NocoDB/commit/fbb6279ce66532fc60bc17d05c03e1b66b2bc09e))

## [0.8.10](https://github.com/bauer-group/CS-NocoDB/compare/v0.8.9...v0.8.10) (2026-09-19)

### 🔧 Maintenance

* **deps:** update base image backuphelper ([dbeeb89](https://github.com/bauer-group/CS-NocoDB/commit/dbeeb892b66e657672996d7cf72e7ed45f54fc75))
* update Dockerfile version to 0.8.9 ([3d5a2cf](https://github.com/bauer-group/CS-NocoDB/commit/3d5a2cf30542b52d815e09b38b0cf425415a8b31))
* update Dockerfile version to 0.8.9 ([9c74ff2](https://github.com/bauer-group/CS-NocoDB/commit/9c74ff2a407c28d539b56d8a4852c6497051d4d0))

## [0.8.9](https://github.com/bauer-group/CS-NocoDB/compare/v0.8.8...v0.8.9) (2026-09-18)

### 🔧 Maintenance

* **deps:** update base image python-alpine ([eebd6ae](https://github.com/bauer-group/CS-NocoDB/commit/eebd6ae3d337f314c08a01db15e87a7e63358d3b))
* update Dockerfile version to 0.8.8 ([0365d58](https://github.com/bauer-group/CS-NocoDB/commit/0365d580ea5540fb9dc92a1e274c5d3e84ebab49))
* update Dockerfile version to 0.8.8 ([b358ecd](https://github.com/bauer-group/CS-NocoDB/commit/b358ecded482ef4c5cc842985366dfb448d530fb))
* update Dockerfile version to 0.8.8 ([16dab7e](https://github.com/bauer-group/CS-NocoDB/commit/16dab7ea9b09e8a05e3e9fe31a19e894cd4b5af8))

## [0.8.8](https://github.com/bauer-group/CS-NocoDB/compare/v0.8.7...v0.8.8) (2026-09-10)

### 🔧 Maintenance

* **deps:** update base image nocodb ([656c3ae](https://github.com/bauer-group/CS-NocoDB/commit/656c3ae101f228530b26bc30d7a8e7cf89d3102a))
* update Dockerfile version to 0.8.7 ([b0481f4](https://github.com/bauer-group/CS-NocoDB/commit/b0481f453fa29039715a5271f473b129cc529b10))
* update Dockerfile version to 0.8.7 ([6fd724e](https://github.com/bauer-group/CS-NocoDB/commit/6fd724e31864818dcac31c8707f7837e87392dbf))
* update Dockerfile version to 0.8.7 ([f9ab2a3](https://github.com/bauer-group/CS-NocoDB/commit/f9ab2a3c941b01df498ada2050a78b940fc27aae))

## [0.8.7](https://github.com/bauer-group/CS-NocoDB/compare/v0.8.6...v0.8.7) (2026-09-03)

### 🔧 Maintenance

* **deps:** update base image nocodb ([a4f935a](https://github.com/bauer-group/CS-NocoDB/commit/a4f935a9d14df1b72b488b7d9769fa94a78645f9))
* update Dockerfile version to 0.8.6 ([acf6af4](https://github.com/bauer-group/CS-NocoDB/commit/acf6af4e564c6b5f21901f8ec908af7f646aa115))
* update Dockerfile version to 0.8.6 ([6400595](https://github.com/bauer-group/CS-NocoDB/commit/64005953025cd96ec95c0070a9aaddd07e7fd6b5))
* update Dockerfile version to 0.8.6 ([538bf21](https://github.com/bauer-group/CS-NocoDB/commit/538bf21d66f2589100071a417e0529732fe48d85))

## [0.8.6](https://github.com/bauer-group/CS-NocoDB/compare/v0.8.5...v0.8.6) (2026-09-02)

## [0.8.5](https://github.com/bauer-group/CS-NocoDB/compare/v0.8.4...v0.8.5) (2026-09-01)

## [0.8.4](https://github.com/bauer-group/CS-NocoDB/compare/v0.8.3...v0.8.4) (2026-08-20)

## [0.8.3](https://github.com/bauer-group/CS-NocoDB/compare/v0.8.2...v0.8.3) (2026-08-07)

## [0.8.2](https://github.com/bauer-group/CS-NocoDB/compare/v0.8.1...v0.8.2) (2026-08-06)

## [0.8.1](https://github.com/bauer-group/CS-NocoDB/compare/v0.8.0...v0.8.1) (2026-08-05)

## [0.8.0](https://github.com/bauer-group/CS-NocoDB/compare/v0.7.4...v0.8.0) (2026-07-21)

### 🚀 Features

* **cluster:** added HAProxy multi-instance stack and fixed dead config ([c762b3d](https://github.com/bauer-group/CS-NocoDB/commit/c762b3db1d57ee39def9d941181606145aeefbe7))

### 🐛 Bug Fixes

* **ci:** added the missing permissions block ([a6be0ad](https://github.com/bauer-group/CS-NocoDB/commit/a6be0ad21b18d036985f533695cf41663046ff8e))

## [0.7.4](https://github.com/bauer-group/CS-NocoDB/compare/v0.7.3...v0.7.4) (2026-07-14)

## [0.7.3](https://github.com/bauer-group/CS-NocoDB/compare/v0.7.2...v0.7.3) (2026-07-09)

## [0.7.2](https://github.com/bauer-group/CS-NocoDB/compare/v0.7.1...v0.7.2) (2026-07-08)

### 🐛 Bug Fixes

* **backup:** kept record<->new-id lockstep on a failed insert batch ([cdc84b0](https://github.com/bauer-group/CS-NocoDB/commit/cdc84b0d53243ae7501583952a6834fb158023bd))

## [0.7.1](https://github.com/bauer-group/CS-NocoDB/compare/v0.7.0...v0.7.1) (2026-07-08)

### 🐛 Bug Fixes

* **backup:** clarified the missing-REST-export restore diagnostic ([a7359ea](https://github.com/bauer-group/CS-NocoDB/commit/a7359ea7b1aea9c52d072ce2c79ef9d6e22870b8))

## [0.7.0](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.26...v0.7.0) (2026-07-08)

### 🚀 Features

* **backup:** migrated the backup sidecar onto the central BackupHelper engine ([5cb425d](https://github.com/bauer-group/CS-NocoDB/commit/5cb425de3e728ad457a5db86e29e4f1b6ff69384))

## [0.6.26](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.25...v0.6.26) (2026-06-29)

## [0.6.25](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.24...v0.6.25) (2026-06-19)

### 🐛 Bug Fixes

* **compose:** relaxed nocodb healthcheck for load spikes ([e05fb0e](https://github.com/bauer-group/CS-NocoDB/commit/e05fb0e07848da9ab01f36341f349b2205eae251))

## [0.6.24](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.23...v0.6.24) (2026-06-16)

## [0.6.23](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.22...v0.6.23) (2026-06-15)

## [0.6.22](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.21...v0.6.22) (2026-06-11)

## [0.6.21](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.20...v0.6.21) (2026-06-05)

## [0.6.20](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.19...v0.6.20) (2026-06-02)

## [0.6.19](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.18...v0.6.19) (2026-05-28)

## [0.6.18](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.17...v0.6.18) (2026-05-19)

## [0.6.17](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.16...v0.6.17) (2026-05-09)

## [0.6.16](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.15...v0.6.16) (2026-05-07)

### ♻️ Refactoring

* **stack:** hardcoded API rate limits as compose-level constants ([317926c](https://github.com/bauer-group/CS-NocoDB/commit/317926c026dcf4544011f7f9355c549cf81f8a83))

## [0.6.15](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.14...v0.6.15) (2026-05-07)

### ⚡ Performance

* **stack:** tuned NocoDB and Postgres for high-load burst workloads ([27c30bd](https://github.com/bauer-group/CS-NocoDB/commit/27c30bd7eb1700eabe193aa369304a814c9c83d3))

### ♻️ Refactoring

* **stack:** rebased compose defaults to standard 8GB-RAM profile ([3a6c2a0](https://github.com/bauer-group/CS-NocoDB/commit/3a6c2a0924522907d91eb809dc0e5c82f8ee9f19))

## [0.6.14](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.13...v0.6.14) (2026-05-01)

## [0.6.13](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.12...v0.6.13) (2026-04-24)

## [0.6.12](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.11...v0.6.12) (2026-04-23)

## [0.6.11](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.10...v0.6.11) (2026-04-16)

## [0.6.10](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.9...v0.6.10) (2026-04-14)

## [0.6.9](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.8...v0.6.9) (2026-04-10)

## [0.6.8](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.7...v0.6.8) (2026-03-19)

## [0.6.7](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.6...v0.6.7) (2026-03-17)

## [0.6.6](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.5...v0.6.6) (2026-03-05)

### 🐛 Bug Fixes

* update environment configuration and Docker Compose files for query and bulk operation limits ([94cd743](https://github.com/bauer-group/CS-NocoDB/commit/94cd7436d9e7b30c4eec9703a7961c72f95f97f4))

## [0.6.5](https://github.com/bauer-group/CS-NocoDB/compare/v0.6.4...v0.6.5) (2026-02-28)

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
