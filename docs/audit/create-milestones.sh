#!/usr/bin/env bash
# Creates the five repo-audit milestones (continuing after v3.1) and puts each
# audit issue (#937-#983: 5 epics + 42 work items) in its milestone.
# Needs the GitHub CLI signed in with write access to the repo (gh auth status).
# Safe to re-run: existing milestones are reused, not duplicated.
set -euo pipefail
REPO=BrandonRobare/telemetry-frame-mapper

ensure_milestone() {  # <title> <description>
  if gh api "repos/$REPO/milestones?state=all&per_page=100" --paginate --jq '.[].title' | grep -Fxq -- "$1"; then
    echo "exists:  $1"
  else
    gh api "repos/$REPO/milestones" -f title="$1" -f description="$2" --jq '"created #\(.number): \(.title)"'
  fi
}

assign() {  # <milestone title> <issue number>...
  local title=$1; shift
  for n in "$@"; do
    gh issue edit "$n" -R "$REPO" --milestone "$title" >/dev/null
    echo "  #$n -> $title"
  done
}

# M1: epic + 15 work items
T='v3.2 — Correctness & Safety Fixes'
ensure_milestone "$T" 'Stop the defects that corrupt or lose user data, produce wrong survey or flight outputs, crash on ordinary inputs, or weaken security. Every item ships with a regression test that fails on today'"'"'s code. From the 2026-09-29 repo audit (group M1, priority P0/P1). Epic: #937. Plan: docs/audit/M1-correctness-and-safety.md'
assign "$T" 937 942 943 944 945 946 947 948 949 950 951 952 953 954 955 956

# M2: epic + 8 work items
T='v3.3 — Test Strategy & CI Split'
ensure_milestone "$T" 'Make every level of testing explicit (unit, integration, contract, component, end-to-end, platform) and split the suite by coverage area so a pull request runs only the lanes its diff touches, while main, nightly and release still run everything with coverage thresholds. From the 2026-09-29 repo audit (group M2, priority P1). Epic: #938. Plan: docs/audit/M2-test-strategy-and-ci.md'
assign "$T" 938 957 958 959 960 961 962 963 964

# M3: epic + 9 work items
T='v3.4 — Reliability & Error Handling'
ensure_milestone "$T" 'Remove silent failure paths, make writes atomic and bounded, keep derived state consistent, and validate inputs at the API boundary. From the 2026-09-29 repo audit (group M3, priority P2). Epic: #939. Plan: docs/audit/M3-reliability-and-error-handling.md'
assign "$T" 939 965 966 967 968 969 970 971 972 973

# M4: epic + 3 work items
T='v3.5 — Performance & Scale'
ensure_milestone "$T" 'Remove N+1 queries and quadratic hot paths that grow with session, project or splat size. From the 2026-09-29 repo audit (group M4, priority P2/P3). Epic: #940. Plan: docs/audit/M4-performance-and-scale.md'
assign "$T" 940 974 975 976

# M5: epic + 7 work items
T='v3.6 — Maintainability & Type Safety'
ensure_milestone "$T" 'Break up the oversized modules, remove copy-paste, and turn on the stricter compiler and linter settings the code already nearly satisfies. From the 2026-09-29 repo audit (group M5, priority P3). Epic: #941. Plan: docs/audit/M5-maintainability-and-type-safety.md'
assign "$T" 941 977 978 979 980 981 982 983

echo "Done: 5 milestones, 47 issues assigned."
