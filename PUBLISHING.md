# Publishing To GitHub

## GitHub repository description

Short description:

```text
Template project for ITSS Variant 9: intelligent satellite channel capacity control based on traffic forecasting.
```

Suggested topics:

```text
python time-series forecasting satellite-network educational-template mermaid jupyter
```

## Recommended repository name

```text
itss-satellite-capacity-template
```

## Local git commands

Run from the repository root:

```bash
git init
git add .
git commit -m "Initial template for ITSS variant 9 satellite capacity project"
```

## Example GitHub remote commands

If the empty repository already exists on GitHub:

```bash
git branch -M main
git remote add origin <YOUR_GITHUB_REPO_URL>
git push -u origin main
```

Example:

```bash
git branch -M main
git remote add origin git@github.com:USERNAME/itss-satellite-capacity-template.git
git push -u origin main
```

## Before pushing

Make sure that:

- `datasets/ip_addresses_sample.tar` is not present in the repository;
- no large intermediate CSV files were added to `results/`;
- `README.md` explains how to download the missing archive separately.
