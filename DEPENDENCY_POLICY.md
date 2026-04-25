# Dependency Update & Security Policy

## 1) Lockfiles are mandatory

- JavaScript workspace uses a committed root lockfile: `pnpm-lock.yaml`.
- Python services use committed per-app lockfiles:
  - `apps/backend/uv.lock`
  - `apps/worker/uv.lock`
- Any change to `package.json` or `pyproject.toml` MUST include regenerated lockfiles in the same PR.

## 2) Update cadence

- **Weekly dependency refresh** via Dependabot (every Monday):
  - npm workspace (`/`)
  - backend pip deps (`/apps/backend`)
  - worker pip deps (`/apps/worker`)
- **Patch/minor updates** are expected continuously.
- **Major updates** are handled explicitly with impact review and rollout notes.

## 3) Security scanning

- A scheduled GitHub Actions workflow (`Dependency maintenance`) runs weekly and on manual dispatch.
- It performs:
  - `pnpm audit --audit-level=high`
  - `pip-audit` for backend and worker dependency graphs exported from `uv.lock`.
- Security findings should be addressed in the next dependency cycle, or immediately for critical issues.

## 4) CI lockfile consistency gate

- PR/push CI (`CI/CD`) includes job **Lockfile integrity**, which fails when lockfiles are out-of-sync:
  - JS: regenerate lockfile in CI and require zero diff for `pnpm-lock.yaml`.
  - Python: `uv lock --check` for backend and worker.
- Merges are blocked until lockfile consistency checks pass.
