# TheSNMC RustDB Security Policy

## Supported versions

This project is pre-1.0 and under active development. Security fixes are applied to the latest main branch.

## Reporting a vulnerability

Please do not open a public issue for sensitive findings.

Report privately with:
- impact summary
- reproduction steps
- suggested remediation (if known)

Until a dedicated security contact is published, coordinate with the repository owner directly.

## Operational recommendations

- Rotate API keys (`RUSTDB_API_KEYS`) regularly.
- Do not expose admin endpoints publicly without authentication and network controls.
- Use HTTPS and reverse proxy in non-local environments.
