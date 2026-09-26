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

## Share bundle filesystem boundary

Share bundles accept artifact files only under the configured exports and processed directories,
or under the configured data directory's `colmap/<reconstruction-id>` subtree. A
reconstruction's stored paths (including `colmap_dir`) do not authorize additional roots.
POSIX bundle creation opens child directories and source files relative to directory
descriptors without following child symlinks; non-regular files are rejected without blocking
on FIFOs. The configured storage roots and **all of their ancestors** must be owned by a
trusted operator and must not be replaceable by an untrusted local user: resolving or creating
the roots before opening their descriptors is outside the descriptor-anchored boundary. Do not
serve untrusted writers from storage-root ancestors.

On Windows, Python does not provide the same `dir_fd`/`O_NOFOLLOW` operations. Path checks and
regular-file checks there are best effort; a local user able to replace directory entries in
configured storage trees during bundling can race them. Restrict write access to those trees.
