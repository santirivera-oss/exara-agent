# Publishing Exara Agent

This project publishes to PyPI through GitHub Actions + PyPI Trusted Publishing.
No PyPI API token is required in GitHub secrets.

## One-time PyPI setup

1. Sign in to PyPI: https://pypi.org
2. Open: https://pypi.org/manage/account/publishing/
3. Add a new pending publisher with these exact values:

| Field | Value |
|---|---|
| PyPI project name | `exara-agent` |
| Owner | `santirivera-oss` |
| Repository name | `exara-agent` |
| Workflow filename | `publish.yml` |
| Environment name | `pypi` |

The GitHub environment `pypi` already exists in this repository.

## Release

After Trusted Publishing is configured and the `tests` workflow is green:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The tag triggers `.github/workflows/publish.yml`, which builds the package and publishes it to PyPI.

## Validate locally before tagging

```powershell
python -m pip install --upgrade build twine
python -m build
python -m twine check dist\*
pytest -q
```

## Install after publish

```powershell
pip install exara-agent
exara init
exara chat
```
