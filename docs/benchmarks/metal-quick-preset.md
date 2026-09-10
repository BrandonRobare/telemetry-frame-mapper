# Metal quick-preset benchmark — Aukerman

Issue: [#820](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/820)
Run: [34484368719](https://github.com/BrandonRobare/telemetry-frame-mapper/actions/runs/34484368719)
Artifact: `10156768777`

## Fixture and protocol

The fixture is the 77-image OpenDroneMap Aukerman aerial survey, CC0-1.0, pinned at source commit `4e8031630f4193494c79b1c1d3524108826d1ba9`. The benchmark generated one fixed COLMAP 4.1.1 sparse model with a 1200-pixel extraction bound, at most 2048 SIFT features, and GPS spatial pairing with eight neighbors, a 100 m radius, and altitude ignored. It registered 75 views and produced 10,883 sparse points.

Hashes:

- image manifest: `e03b500730f4a94c5dc6a67d7978d336c0c4b2bdde3e7ee28bd0151da96fefb3`
- sparse model: `06722b99e2482ce493bfa7ce203e9dcd9c0cb0ca1287fe52451db5da35c8428a`
- sparse-model archive: `23d420aac01e86cf263242003798db39af92611f7a9d94aad55afddf38d2dfe4`
- committed JSON evidence: `6fe548ad1a2b395de84e38df2169c73ea493957c77524e26add44409e970ce9b`

The preregistered quick settings were SH degree 1, downscale 4, and a 350,000 Gaussian cap. Candidate iteration counts were 1,250, 1,500, 2,000, 2,500, and 3,000. The smallest candidate producing at least 1.25x the sparse count wins. Metal is synchronized inside the backend before timing returns.

## Results

The runner was arm64 on macOS 26.6.2 with 7 GiB unified memory, Python 3.12.10, and msplat 1.1.4. The hosted runner did not report a chip model.

| Iterations | Final Gaussians | Growth | Wall time | Maximum RSS |
|---:|---:|---:|---:|---:|
| 1,250 | 27,215 | 2.501x | 72.85 s | 2.40 GiB |
| 1,500 | 35,123 | 3.227x | 80.85 s | 2.88 GiB |
| 2,000 | 35,393 | 3.252x | 104.89 s | 2.88 GiB |
| 2,500 | 36,815 | 3.383x | 129.52 s | 2.91 GiB |
| 3,000 | 37,240 | 3.422x | 144.59 s | 2.95 GiB |

The 1,250-iteration candidate is the smallest passing result and therefore becomes Metal's `quick` default. CUDA remains at 1,000 iterations.

The preregistered 500,000-cap probe at 1,250 iterations produced 26,912 Gaussians versus 27,215 at the 350,000 cap (0.989x), with 2.95 GiB maximum RSS (42.2% of unified memory). It failed the required 1.10x count gain, so Metal retains the 350,000 cap. The `full` cap remains 1,000,000 because this quick-preset run did not measure a full training workload.

## Scope and limitations

This benchmark establishes that Metal `quick` measurably densifies a survey-sized public scene and chooses the smallest passing iteration count. It does not establish CUDA-vs-Metal quality parity; held-out PSNR/SSIM and throughput comparison remain the separate #784 gate. Raw imagery is not committed. The JSON evidence is stored in `docs/benchmarks/evidence/metal-quick-preset-aukerman.json`; the generated sparse model is the fixed input for #784.
