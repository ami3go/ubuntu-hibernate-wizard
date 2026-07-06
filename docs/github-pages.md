---
title: GitHub Pages deployment and SEO notes
description: Deploy Ubuntu Hibernate Wizard documentation to GitHub Pages with MkDocs Material, screenshots, sitemap, robots.txt, GitHub Actions, and search-friendly page structure.
---

# GitHub Pages deployment and SEO notes

This repository publishes the documentation site with MkDocs Material, GitHub Actions, and GitHub Pages.

## One-time repository setup

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

It runs when changes are pushed to `main` and can also be started manually from **Actions → Docs → Run workflow**.

The workflow:

1. checks out the repository;
2. configures GitHub Pages;
3. installs MkDocs Material;
4. runs `mkdocs build --strict`;
5. uploads the generated `site/` directory;
6. deploys the artifact to GitHub Pages.

## Expected site URL

```text
https://ami3go.github.io/ubuntu-hibernate-wizard/
```

## Search visibility checklist

The site is structured around real Ubuntu hibernation search questions:

- **Ubuntu hibernation setup**;
- **Ubuntu hibernate with swap file**;
- **resume UUID and resume_offset**;
- **GRUB initramfs hibernation**;
- **zram cannot hibernate**;
- **Ubuntu hibernate troubleshooting**.

The documentation includes:

- a descriptive `site_name` and `site_description` in `mkdocs.yml`;
- focused page titles and descriptions in front matter;
- one H1 per page;
- descriptive image alt text;
- GTK4 screenshots and examples;
- internal links between Installation, Usage, Troubleshooting, Rollback, Architecture, and FAQ;
- `robots.txt` pointing to the generated sitemap;
- `site_url` configured for the public GitHub Pages URL.

After publishing, submit this sitemap in Google Search Console:

```text
https://ami3go.github.io/ubuntu-hibernate-wizard/sitemap.xml
```

## Local documentation preview

```bash
python3 -m pip install mkdocs-material
mkdocs serve
```

Then open:

```text
http://127.0.0.1:8000/
```

## Troubleshooting deployment

### `HttpError: Not Found` while creating Pages deployment

Most likely GitHub Pages is not enabled for the repository or the source is not set to **GitHub Actions**.

Fix:

1. Open **Settings → Pages**.
2. Set **Source** to **GitHub Actions**.
3. Re-run the workflow.

### Sitemap not visible immediately

Search engines do not index new GitHub Pages sites immediately. Confirm that the generated page loads publicly, then submit the sitemap in Search Console and wait for crawling.

### Node deprecation warning

Warnings such as `Node 20 is being deprecated` or `punycode module is deprecated` are usually not the root cause of deployment failure. Keep the GitHub Actions versions current and check the final failing step.
