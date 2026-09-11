# CUDA–Metal held-out parity protocol

Issue: [#784](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/784)

Status: preregistered before #784 measurements. Do not edit thresholds after inspecting backend results; protocol corrections require a dated rationale and fresh runs of both backends.

Protocol corrections (2026-09-11): run `34606882358` proved the initial black-background harness executed at `c5ab4357d2b503faeee9f780328454fa671b9ea6`, but its PLY contained 10,194 non-finite rows out of 25,225. That run is invalid, not quality evidence. Because msplat 1.1.4 intentionally trains against magenta by default, both trainers and the common evaluator were switched to that same documented native background without changing the quality thresholds. The exact revised-policy run `34608642410` at `66044124b282372be9acc2f5cc3c046c55e1143c` still exported 4,869 invalid rows out of 27,362. The second failure is also invalid, so the hardware lane is stopped: Metal quality/throughput parity remains unproven, output finiteness is now a mandatory gate, and no CUDA run should be interpreted as completing #784 until the Metal defect is repaired or explicitly accepted as an experimental limitation.

## Objective

Measure one fixed public aerial scene through the production CUDA gsplat and Metal msplat trainer seams. The comparison answers whether the exported Metal splat remains within an explicitly acceptable held-out quality delta, and records hardware-qualified training throughput and convergence counts. It does not claim universal parity across scenes or hardware.

## Immutable fixture and split

- OpenDroneMap Aukerman imagery, CC0-1.0, source commit `4e8031630f4193494c79b1c1d3524108826d1ba9`.
- The repository commits the fixed COLMAP sparse archive and image hash manifest under `tests/fixtures/benchmarks/aukerman-v1/`.
- Required sparse archive SHA-256: `23d420aac01e86cf263242003798db39af92611f7a9d94aad55afddf38d2dfe4`.
- Required sparse-model tree SHA-256: `06722b99e2482ce493bfa7ce203e9dcd9c0cb0ca1287fe52451db5da35c8428a`.
- Required image-manifest SHA-256: `e03b500730f4a94c5dc6a67d7978d336c0c4b2bdde3e7ee28bd0151da96fefb3`.
- Expected model: 75 registered views and 10,883 sparse points.
- Sort registered filenames bytewise. Hold out index `i` when `i % 8 == 0`: 65 training views and 10 held-out views. `fixture.json` records the names and list hash.
- Both hosts must download the same source commit, verify every required image before runtime import, and use the committed sparse archive. Regenerating COLMAP is not a valid substitute.

## Identical explicit trainer policy

Do not use accelerator-dependent product defaults. Construct the same benchmark-only values on both hosts:

| Setting | Value |
|---|---:|
| iterations | 1,250 |
| SH degree | 1 |
| image downscale | 4 |
| Gaussian cap | 350,000 |
| refinement start | 300 |
| refinement stop | 625 |
| refinement interval | 100 |
| opacity reset interval | 3,000 |
| SSIM loss weight | 0.2 |
| initial opacity | 0.1 |
| SH warm-up interval | 500 |
| background | msplat 1.1.4 native magenta `[0.6130, 0.0101, 0.3984]` |
| internal training-view evaluation | disabled |
| exported coordinate frame | original COLMAP frame |

The 1,250 iterations and 350,000 cap are the measured Metal `quick` policy from #820. The 625 refinement stop aligns gsplat with msplat 1.1.4's hard half-run split ceiling. A reset interval longer than the run prevents one backend from resetting opacity while the other does not. CUDA already exports the original COLMAP frame; benchmark-mode Metal sets `keep_crs=true` so one evaluator can apply the same committed camera poses to both PLY files. Production defaults remain unchanged.

Known non-identical implementation details—initial quaternion policy, camera-sampling order, optimizer implementation, and native densification internals—are part of the backend comparison and must be documented, not hidden as matched hyperparameters.

## Execution and timing

Run one backend per fresh worker process on real target hardware. The worker must:

1. verify fixture, image, split, backend, device, and dependency versions;
2. stage the fixed sparse model and source images outside the timed region;
3. start `perf_counter()` immediately before calling the selected production backend's `train()` method;
4. include dataset/runtime initialization, all 1,250 iterations, and PLY export;
5. explicitly synchronize the target accelerator after `train()` returns, then stop the clock;
6. retain native stdout/stderr and count msplat per-tile overflow warnings.

Record OS, architecture, CPU, accelerator model, memory, Python, torch/CUDA/driver/gsplat or msplat versions, exact Git commit, wall seconds, iterations/second, final Gaussian count, output PLY hash, sync confirmation, and process RSS as diagnostic only. Hardware throughput has no pass/fail threshold because the devices differ.

## Portable run artifacts

Each host uploads a bundle containing:

- canonical `run.json` with no absolute paths;
- exported `splat.ply`;
- `environment.txt`;
- complete `backend.log`;
- `SHA256SUMS` for bundle members.

The comparison rejects mismatched schema, fixture, split, policy fingerprint, source commit, Git commit, missing sync, unavailable backend, OOM/cancellation, unreadable PLY, or missing metadata.

The manual CUDA job requires an owner-controlled self-hosted Linux x64 runner labeled `cuda`, NVIDIA CUDA Toolkit 12.4, and a compatible driver. The workflow pins Python 3.12, torch 2.6.0+cu124, and gsplat 1.5.3, and executes a real CUDA rasterization smoke before the benchmark. The manual Metal job pins Python 3.12 and msplat 1.1.4 on the existing arm64 hosted runner. Neither hardware path is reachable from pull-request or push events. Both jobs additionally require the repository owner to dispatch them and supply the exact reviewed commit through `heldout_parity_approved_sha`; checkout fails unless that value equals `GITHUB_SHA`.

## Held-out evaluator

Evaluate both exported PLY files on one real CUDA host with the same application-owned gsplat/PyTorch evaluator, fixed held-out image bytes, COLMAP poses/intrinsics, downscale factor, preregistered magenta background, PSNR formula, and 11×11 Gaussian-window SSIM implementation. Store per-view PSNR, SSIM, and rendered-image SHA-256 plus arithmetic means. The compare command requires an empty evidence directory and an output evidence bundle; it retains both source run bundles, every rendered PNG, canonical comparison JSON, and a checksum manifest.

## Preregistered decision

Let `delta = Metal - CUDA` on the arithmetic mean of the ten held-out views.

- PASS: `PSNR delta >= -1.0 dB` and `SSIM delta >= -0.030`.
- FAIL: either quality delta falls below its threshold.
- INVALID/INCONCLUSIVE: any integrity, configuration, provenance, synchronization, output-readability, or required-metadata gate fails.
- Count alert: investigate a Metal/CUDA Gaussian-count ratio below `0.50x` or above `2.00x`; count alone cannot pass or fail quality.

If PASS, release notes may describe Metal as meeting this fixed-scene quality gate while naming both devices and the measured throughput ratio. If FAIL, do not claim parity: repair and rerun both sides, or ship Metal explicitly labelled preview/experimental with the measured deficit. If INVALID/INCONCLUSIVE, #784 remains open.

## Verification commands

```text
uv lock --check
uv run --frozen --no-sync ruff check .
uv run --frozen --no-sync pytest -q
cd frontend && npm audit --audit-level=moderate && npm test -- --run && npm run lint && npm run build

sha=$(git rev-parse HEAD)
gh workflow run ci.yml --ref wave8/784-cuda-metal-parity -f heldout_parity_target=metal -f heldout_parity_approved_sha="$sha"

uv run --frozen --no-sync python -m scripts.benchmark_heldout_parity compare --cuda-bundle heldout-cuda.tar.gz --metal-bundle heldout-metal.tar.gz --source /path/to/pinned/odm_data_aukerman --output heldout-cuda-metal-aukerman.json --evidence-dir heldout-comparison --evidence-bundle heldout-comparison.tar.gz
```

Real-hardware completion additionally requires a CUDA usability/JIT-rasterization smoke, native Metal/msplat smoke, exact artifact/run/head verification, comparison output at the public PLY boundary, exact-head CI/CodeQL, and independent review.

## Boundaries and stop conditions

Never commit source imagery, private scenes, secrets, local paths, native caches, or unreviewed large output artifacts. Do not treat CPU mocks as accelerator evidence. Stop after one implementation repair pass, on fixture/protocol drift, or when either real target is unavailable. As of preregistration, GitHub-hosted Apple Silicon is available; no local, self-hosted, or GitHub-hosted CUDA runner is configured, so a final verdict cannot be produced until CUDA infrastructure is supplied.
