# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Yes |

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability** (security advisories). Include a description, the impact and steps to reproduce.

You can expect an acknowledgement within a few days. Confirmed issues are fixed in a patch release and credited in the changelog unless you prefer otherwise.

## Scope notes

- API keys are read only from environment variables and are never written to reports.
- JSON reports contain the full prompts and model outputs you send and receive; treat them as sensitive if your prompts are.
