# Security policy

## Supported code

Security fixes target the latest code on `main`. This community integration does not yet maintain separate release support branches. Upstream Laya and third-party dependencies have their own security policies.

## Report a vulnerability

Use GitHub's [private vulnerability reporting](https://github.com/Maxwell00000086/laya-agent-kit/security/advisories/new). Include affected versions, the impact and a minimal reproduction with synthetic data. Do not open a public issue containing exploit details or credentials.

If the reporting form is unavailable, open a public issue asking the maintainer to enable private reporting; omit vulnerability details. There is no promised response time or bounty program.

## Credentials and execution

Do not upload API keys, `.env` files, local MCP client configurations, model caches or unredacted diagnostic logs. If a credential is exposed, revoke it at its provider; deleting a comment or file alone does not invalidate it.

Laya runs locally, but the optional ChatGPT connection sends tool requests and results through OpenAI's tunnel. Keep runtime keys on the local machine and use the documented runtime permissions. The kit's model judgments are advisory and must not replace authorization, security reviews or publication checks.
