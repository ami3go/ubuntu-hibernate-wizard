# GitHub Pages Deployment

This repository is ready to publish the MkDocs documentation site with GitHub Pages and GitHub Actions.

## One-time GitHub repository setup

1. Open the repository on GitHub.
2. Go to **Settings → Pages**.
3. Under **Build and deployment**, set **Source** to **GitHub Actions**.
4. Save the setting.

Without this setting, the workflow can build the documentation artifact but `actions/deploy-pages` may fail with `HttpError: Not Found` during deployment.

## Deployment workflow

The workflow is defined in:

```text
.github/workflows/docs.yml
```

It runs when changes are pushed to the `main` branch and can also be started manually from **Actions → Docs → Run workflow**.

The workflow does the following:

1. Checks out the repository.
2. Configures GitHub Pages.
3. Installs MkDocs Material.
4. Builds the site with `mkdocs build --strict`.
5. Uploads the generated `site/` directory as a Pages artifact.
6. Deploys the artifact to GitHub Pages.

## Expected site URL

For the `ami3go/ubuntu-hibernate-wizard` repository, the site URL is:

```text
https://ami3go.github.io/ubuntu-hibernate-wizard/
```

## Troubleshooting

### `HttpError: Not Found` while creating Pages deployment

Most likely GitHub Pages is not enabled for the repository or the source is not set to **GitHub Actions**.

Fix:

1. Open **Settings → Pages**.
2. Set **Source** to **GitHub Actions**.
3. Re-run the workflow.

### Node deprecation warning

Warnings such as `Node 20 is being deprecated` or `punycode module is deprecated` are not normally the root cause of deployment failure. The workflow uses the current GitHub Pages action versions intended for newer GitHub Actions runners.
