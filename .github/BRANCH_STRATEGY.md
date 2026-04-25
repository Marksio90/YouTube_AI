# Branch strategy and release safety (AI Media OS)

## Branch model

- `dev` branch
  - Integration branch for feature work.
  - CI runs on every PR and push.
  - Auto-deploy target: **dev Kubernetes environment**.
- `main` branch
  - Stable release branch.
  - Merge only from reviewed PRs.
  - Auto-deploy target: **prod Kubernetes environment**.

## Production-safe deployment controls

Configure these repository settings (required for production readiness):

1. **Protected branches**
   - Protect `main` and `dev`.
   - Require pull request before merge.
   - Require status checks from workflow `CI/CD`:
     - Build frontend
     - Build backend
     - Lint
     - Tests (placeholder)
   - Require up-to-date branch before merging.
   - Block force pushes and branch deletions.

2. **GitHub Environments**
   - Create environments: `dev`, `prod`.
   - Add environment secrets:
     - `KUBE_CONFIG_B64` (base64 kubeconfig)
   - Add environment variables:
     - `K8S_NAMESPACE`
     - `ENVIRONMENT_URL`
   - For `prod`: require manual approval (required reviewers).

3. **Registry permissions**
   - Grant workflow `packages:write` permission.
   - Ensure GitHub Packages (GHCR) write access for repository actions.

4. **Rollout safety**
   - Keep Kubernetes rolling update strategy (`maxUnavailable: 0` for frontend/backend).
   - Pipeline blocks until `kubectl rollout status` succeeds for all deploys.
   - If rollout fails, deployment job fails and release is stopped.

## Secret management policy

- Never store credentials in repository.
- Rotate `KUBE_CONFIG_B64` and registry credentials regularly.
- Use GitHub environment-level secrets to separate `dev` and `prod` credentials.
