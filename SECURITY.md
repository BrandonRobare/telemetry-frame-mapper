# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 2.0.x   | ✅        |
| 1.0.x   | ❌        |
| < 1.0   | ❌        |

## Reporting a vulnerability

Report security issues privately through GitHub's
[Security Advisories](https://github.com/BrandonRobare/telemetry-frame-mapper/security/advisories/new)
for this repository. Do not open a public issue for a vulnerability.

Include the affected component (CLI, backend, or frontend), a reproduction, and the
impact you observed. Expect an initial response within 72 hours. If the report is
confirmed, a fix is released as a patch version (e.g. 2.0.1) and the advisory is
published with credit unless you ask otherwise.

## Scope notes

This is a local-first tool: the backend binds to localhost and invokes external binaries
(ffmpeg, exiftool, COLMAP) as argv lists, never through a shell. Import, export, and
storage paths are validated against traversal. Reports about these boundaries are
especially welcome.

PIN unlock sessions, share-link unlock sessions, and PIN/share throttles are process-local.
In v2.0.4, run exactly one API process on one host; multi-process and cross-host API serving are
unsupported. A remote GPU worker performs reconstruction work only and is not a second API process.
The backend enforces this where the throttles matter: a process that does not own the job-queue
lock refuses to start when PIN lock is enabled or a live password-protected share link exists, and
refuses to create a password-protected share link.
