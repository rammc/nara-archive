# Security policy

## Supported versions

Only the **latest minor release** of `actari` receives security fixes.
Older minor versions are not patched.

| Version | Supported |
| --- | --- |
| 1.0.x | ✅ |
| < 1.0 | ❌ — pre-1.0 release candidates ship "as is" |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security reports.

Two private channels, pick either:

1. **GitHub Security Advisory** (preferred) — at
   <https://github.com/rammc/actari/security/advisories/new>. This gives
   us a private space to discuss the issue with you and coordinate a fix
   and disclosure timeline.
2. **Email** — <hello@cramm.dev>. Use a clear subject like
   `actari security: <one-line summary>`.

## What to include

- Affected version (`actari --version`)
- Operating system
- A description of the vulnerability and its impact
- Reproduction steps or proof-of-concept code, if you have one
- Whether you've disclosed it elsewhere

You don't need to fix the bug yourself — a clear report is enough.

## Response timeline

| Step | Target |
| --- | --- |
| Acknowledge receipt | within **7 days** |
| Initial assessment + severity rating | within **14 days** |
| Patch released (where feasible) | depends on severity; critical issues prioritised |
| Public disclosure | coordinated with you — typically after a fix is shipped |

## Scope

In scope:
- Vulnerabilities in `actari`'s own code (CLI, server, bundled `.app`)
- Path-traversal or sandbox escapes in the PDF / static-file serving
- Credential leakage in logs or memory
- Issues that allow remote actors to read or modify local state when
  the server is bound to `127.0.0.1`

Out of scope:
- Vulnerabilities in NARA's Catalog API itself (report to NARA directly)
- Issues caused by user-supplied API keys being leaked outside `actari`
  (e.g. committed to a public git repository)
- Vulnerabilities in upstream dependencies — please report those to the
  upstream project; we'll bump versions when fixes ship
- Issues that require the user to bind the server to a non-localhost
  interface (`--host 0.0.0.0`) without understanding the implications.
  The CLI warns about this; binding broadly is documented as user-owned risk.

Thanks for helping keep `actari` and its users safe.
