## **2.0.0-rc1** <sub><sup>2025-04-25 (47d581a...7409871)</sup></sub>

### Project Maintenance
*  config flake8 (0c8273c)
*  code format (6215228)
*  rename setup\.cfg \-\> \.flake8 (ceeff13)
*  update project config (3ebc916)
*  update line width (3c038b9)
*  code format (4d61b26)
*  add dev requirements (0f02631)
*  project settings (01d313f)
*  add pre\-commit (b382f0c)
*  update gitignore (e61077c)
*  add markdownlint (632e15b)
*  update package\.json for conventional\-commits (71e4839)
*  add bumpversion (77a3fe1)
*  add bumpversion (6b63537)
*  fix bumpversion (9a26d55)
*  code format (060b9ce)
*  update docs config (ae0e9af)
*  update LICENSE (d26806c)
*  update git\-conventional\-commits (88f6916)
*  fix bumpversion (7409871)


### Features
*  add \.env (5aa771a)
*  add argparse,dotenv,\-\-local argument for testing (1626edd)
*  update dockerfile (c9fc7bc)
*  add issuer annotation (b5adcfa)
*  regen on annotation change (6a902e8)
*  exit (5a7e04a)
*  implement leader\-election multi replica support (c317ec6)
*  implement candidate\_id, logging (41eebd4)
*  add current version (49ac173)
*  update dockerfile (4b971d7)


### Bug Fixes
*  requirements (3779004)
*  reduce CPU load (2a2c779)
*  avoid missing stream events (3b63365)
*  stream retry (05d6f9b)
*  skip if certificate already exists (ce85a30)
*  signal name (d360a76)
*  add signal ID to signal name (5d258b4)
*  leader lock name (621a067)
*  linter (0c2c651)
*  linter (6e215cf)
*  dockerfile (f8b708f)


### Improvements
*  pull request \#5 from gjrtimmer/feat/leader\-election (eb1aff7)


### Operations / Workflow Improvements
*  add CI/CD linter (6ebae81)
*  fix linter (6726730)
*  debug pipeline (a6f94d5)
*  fix lint actions (296840d)
*  add conventional\-commits (8e0ed23)
*  add release action (0d9b2f6)
*  implement automatic changelog (2f12eab)
*  add docker\-latest image (21388c2)
*  fix dockerfile (06dc6d1)
*  refactor docker tags (bf38e24)
*  publish latest README to dockerhub (1cc69cc)
*  implement docker cache (9516f31)
*  update dockerhub readme settings (4e6252a)
*  add docker release workflow (2f734e0)
*  remove obsolete docker workflow (2b16b22)
*  rename workflows (ce9418d)
*  add docker tag latest to docker\-release (bb3da70)
*  deployment manifest (c3009a0)
*  add certmanager helmfile deployment (d9e368d)


### Code Refactoring
*  move file (25e0d35)


## 1.1.0 - 2023-11-21

### Changed

- now monitors `traefik.io` as well as `traefik.containo.us`

### Added

- catch signals to exit quicker
- will add secretName to ingressRoute if missing (PATCH_SECRETNAME=true)

## 1.0.0 - 2022-10-09

This is the initial release. This will work with Traefik IngressRoutes and create Certificates from them.
