# Contributing to traefik-certmanager

Thank you for your interest in improving **traefik-certmanager**! This guide will help you get set up, run the project locally, and follow best practices for linting, testing, versioning, and submitting pull requests.

---

## Table of Contents

- [Table of Contents](#table-of-contents)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
  - [Pre-commit hooks](#pre-commit-hooks)
- [Running Locally](#running-locally)
- [Linting \& Formatting](#linting--formatting)
- [Versioning \& Changelog](#versioning--changelog)
- [Docker Image](#docker-image)
- [Submitting a Pull Request](#submitting-a-pull-request)

---

## Getting Started

Clone the repo and set up a Python 3.13 virtual environment:

```bash
git clone https://github.com/gjrtimmer/traefik-certmanager.git
cd traefik-certmanager
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Optionally install development tooling (linters, pre-commit, bump2version, etc.):

```bash
pip install -r requirements-dev.txt
pre-commit install
```

Optionally when you want to generate a `CHANGELOG` `git-conventional-commits` is required
which can be installed with:

```shell
npm install
```

Create a .env file (in the project root) to override any defaults:

```shell
# example .env
ISSUER_NAME_DEFAULT=letsencrypt
ISSUER_KIND_DEFAULT=ClusterIssuer
INGRESS_CLASS_FILTER=traefik-internal,traefik-external
PATCH_SECRETNAME=true
CERT_CLEANUP=false
SUPPORT_LEGACY_CRDS=false
```

## Development Setup

The repository provides default extensions and configuration through the default config in `.vscode`.


### Pre-commit hooks

On each git commit, the configured hooks will run `black`, `isort`, `flake8`, and `mypy`. 

To run them manually:

```shell
pre-commit run --all-files
```

## Running Locally

You can exercise the controller locally (outside of a cluster) using the `--local` flag.

```shell
# ensure your venv is active
python main.py --local
```

This uses your $KUBECONFIG to connect to a real cluster—or, if you set USE_LOCAL_CONFIG=true, it will load your local kubeconfig.
Log output will show which IngressRoute CRDs are watched, and how certificates are reconciled.

## Linting & Formatting

- `Black` (formatter):

    ```shell
    black --check .
    ```

- `isort` (import sorting):

    ```shell
    isort --check-only --diff .
    ```

- `flake8` (style & errors):

    ```shell
    flake8 .
    ```

- `mypy` (static types):

    ```shell
    mypy . --ignore-missing-imports
    ```

You can run them all at once with:

```shell
pre-commit run --all-files
```

## Versioning & Changelog

We use bump2version for Python version bumps and changelog headers, and Conventional Commits + conventional-changelog-cli for changelog entries.

1. Bump version (updates __version__ and the first changelog header; no commit/tag):

    Update Major

    ```shell
    bumpver update --major
    ```

    Update Minor

    ```shell
    bumpver update --minor
    ```

    Update Patch

    ```shell
    bumpver update --minor
    ```

    Create Release Candidate

    ```shell
    bumpver update --tag rc --tag-num
    ```

2. Generate changelog section:

    ```shell
    npx git-conventional-commits changelog -f CHANGELOG.md -r "{VERSION}"
    ```

3. Inspect main.py and CHANGELOG.md.
4. Commit & tag:

    ```shell
    git add main.py CHANGELOG.md
    git commit -m "chore(release): 1.1.1"
    git tag 1.1.1
    git push origin main --tags
    ```

The GitHub Actions will pick up the tag and publish a Release and multi-arch Docker images automatically.

## Docker Image

To build & push a latest image from main branch:

```shell
# in CI via .github/workflows/docker-latest.yml:
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  --tag <dockerhub_user>/traefik-certmanager:latest \
  --push .
```

Or locally:

```shell
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  -t <dockerhub_user>/traefik-certmanager:latest .
```

## Submitting a Pull Request

1. Fork the repo, create a feature branch (git checkout -b feat/my-feature).
2. Make your changes (adhere to linting, formatting, docstrings).
3. Run all linters and tests locally.
4. Commit with a Conventional Commit message:

    ```shell
    feat: add support for new annotation
    ```

5. CI will validate linting and run any workflows.
6. Request review, address feedback, and once approved, your PR will be merged.

Thank you for contributing! 🎉
