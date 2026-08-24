from __future__ import annotations

import json
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.services import splat_trainer
from backend.services.splat_trainer import TrainerConfig, smoothstep


def _noop_progress(step: str, pct: float) -> None:
    pass


# Setting a sys.modules entry to None makes `import <name>` raise ImportError, so
# these tests simulate a torch-less environment deterministically — they must pass
# both in CI (no torch installed) and on the GPU dev machine (torch installed).
_NO_GPU_STACK = {"torch": None, "gsplat": None}


def test_module_imports_without_torch():
    # Clean-room subprocess: with the GPU stack blocked before anything else
    # imports, the module must still import — proving its top level never pulls
    # in torch/gsplat. (An in-process importlib.reload would re-create the
    # module's classes and break `except ReconstructionCancelled` identity in
    # reconstruction.py for every test that runs afterwards.)
    code = (
        "import sys; sys.modules['torch'] = None; sys.modules['gsplat'] = None; "
        "import backend.services.splat_trainer as m; "
        "assert all(hasattr(m, n) for n in ('train_splats', 'render_thumbnail', "
        "'render_flythrough', 'TrainerConfig')); "
        "assert issubclass(m.ReconstructionCancelled, RuntimeError)"
    )
    subprocess.run(
        [sys.executable, "-c", code], check=True, cwd=Path(__file__).parents[2]
    )


def test_train_splats_without_torch_raises_colmap_only_guidance(tmp_path: Path):
    config = TrainerConfig.from_preset({"iterations": 1000})
    with (
        patch.dict(sys.modules, _NO_GPU_STACK),
        pytest.raises(RuntimeError, match="COLMAP sparse cloud only"),
    ):
        splat_trainer.train_splats(
            tmp_path, tmp_path / "splat.ply", config, _noop_progress, threading.Event()
        )


def test_render_thumbnail_without_torch_returns_none(tmp_path: Path):
    with patch.dict(sys.modules, _NO_GPU_STACK):
        result = splat_trainer.render_thumbnail(tmp_path / "splat.ply", tmp_path / "thumb.jpg")
    assert result is None


def test_render_flythrough_without_torch_mentions_browser_recording(tmp_path: Path):
    keyframes = [
        {"position": [0.0, 0.0, 0.0], "target": [0.0, 0.0, 1.0], "duration_s": 1.0},
        {"position": [1.0, 0.0, 0.0], "target": [1.0, 0.0, 1.0], "duration_s": 1.0},
    ]
    with (
        patch.dict(sys.modules, _NO_GPU_STACK),
        pytest.raises(
            RuntimeError,
            match="Use browser recording or install optional reconstruction dependencies",
        ),
    ):
        splat_trainer.render_flythrough(
            tmp_path / "splat.ply", tmp_path / "out.mp4", keyframes,
            fps=30, width=1280, height=720,
        )


def test_render_flythrough_without_ffmpeg_raises_install_guidance(tmp_path: Path):
    keyframes = [
        {"position": [0.0, 0.0, 0.0], "target": [0.0, 0.0, 1.0], "duration_s": 1.0},
        {"position": [1.0, 0.0, 0.0], "target": [1.0, 0.0, 1.0], "duration_s": 1.0},
    ]
    with (
        patch.dict(sys.modules, {"torch": MagicMock(), "gsplat": MagicMock()}),
        patch("backend.services.splat_trainer.shutil.which", return_value=None),
        pytest.raises(RuntimeError, match="ffmpeg.*browser recording"),
    ):
        splat_trainer.render_flythrough(
            tmp_path / "splat.ply", tmp_path / "out.mp4", keyframes,
            fps=30, width=1280, height=720,
        )


def test_trainer_config_from_preset_quick_and_full_defaults():
    quick = TrainerConfig.from_preset({"iterations": 1000, "max_frames": 500})
    assert quick.iterations == 1000
    assert quick.sh_degree == 1
    assert quick.downscale_factor == 4
    assert quick.max_gaussians == 350_000
    assert (quick.refine_start_iter, quick.refine_stop_iter, quick.refine_every) == (
        300, 800, 100,
    )
    assert quick.reset_every > quick.iterations  # opacity reset disabled on quick
    assert (quick.eval_every, quick.eval_views) == (250, 4)
    assert quick.sh_warmup_every == 500
    assert quick.ssim_lambda == 0.2
    assert quick.init_opacity == 0.1

    full = TrainerConfig.from_preset({"iterations": 30000, "max_frames": None})
    assert full.iterations == 30000
    assert full.sh_degree == 2
    assert full.downscale_factor == 2
    assert full.max_gaussians == 1_000_000
    assert (full.refine_start_iter, full.refine_stop_iter, full.refine_every) == (
        500, 15_000, 100,
    )
    assert full.reset_every == 3000
    assert (full.eval_every, full.eval_views) == (1000, 4)
    assert full.sh_warmup_every == 1000

    # Per-preset overrides in config.yaml win over profile defaults.
    overridden = TrainerConfig.from_preset({"iterations": 1000, "max_gaussians": 123})
    assert overridden.max_gaussians == 123


def test_smoothstep_keyframe_interpolation_endpoints():
    assert smoothstep(0.0) == 0.0
    assert smoothstep(1.0) == 1.0
    assert smoothstep(0.5) == 0.5
    # Must mirror frontend/src/features/splat/smoothstep.ts exactly.
    for t in (0.1, 0.25, 0.6, 0.9):
        assert smoothstep(t) == pytest.approx(t * t * (3 - 2 * t), abs=1e-12)
    assert smoothstep(0.1) < 0.1
    assert smoothstep(0.9) > 0.9


def test_training_pct_maps_into_rebalanced_window():
    # COLMAP now owns 0-40%, so training's window starts at 40.0 and ends at 99.0
    # (leaving headroom at the end for LOD/thumbnail generation).
    from backend.services.splat_trainer import _training_pct

    assert splat_trainer._PROGRESS_START == 40.0
    assert splat_trainer._PROGRESS_END == 99.0
    assert _training_pct(0, 1000) == pytest.approx(40.0)
    assert _training_pct(1000, 1000) == pytest.approx(99.0)
    midpoint = _training_pct(500, 1000)
    assert 40.0 < midpoint < 99.0


def test_train_uses_largest_fragmented_colmap_submodel(tmp_path: Path):
    """Splat training must share reconstruction's largest-model selection policy."""
    sparse = tmp_path / "sparse"
    for name, image_count in (("0", 1), ("1", 2)):
        submodel = sparse / name
        submodel.mkdir(parents=True)
        headers = [
            f"{index} 1 0 0 0 0 0 0 1 frame_{index}.jpg\n"
            for index in range(1, image_count + 1)
        ]
        (submodel / "images.txt").write_text("".join(headers))
    no_images_model = MagicMock(images=[], points_xyz=np.empty((0, 3)))
    torch = MagicMock()
    torch.cuda.is_available.return_value = False

    with (
        patch.object(
            splat_trainer.colmap_io, "read_model", return_value=no_images_model
        ) as read_model,
        pytest.raises(RuntimeError, match="no registered images"),
    ):
        splat_trainer._train(
            torch, MagicMock(), tmp_path, tmp_path / "splat.ply",
            TrainerConfig.from_preset({"iterations": 1}), _noop_progress, threading.Event(),
        )

    read_model.assert_called_once_with(sparse / "1")


class _ArrayTensor:
    def __init__(self, value):
        self._value = np.asarray(value)

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self._value


def test_write_cancel_checkpoint_persists_ply_and_sidecar(tmp_path: Path):
    params = {
        "means": _ArrayTensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
        "sh0": _ArrayTensor([[[0.1, 0.2, 0.3]], [[0.4, 0.5, 0.6]]]),
        "shN": _ArrayTensor(np.zeros((2, 0, 3), dtype=np.float32)),
        "opacities": _ArrayTensor([0.0, 1.0]),
        "scales": _ArrayTensor(np.zeros((2, 3), dtype=np.float32)),
        "quats": _ArrayTensor([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]),
    }
    output_path = tmp_path / "splat.ply"

    result = splat_trainer._write_cancel_checkpoint(
        output_path,
        params,
        completed_iterations=125,
        metrics=[{"iter": 100, "psnr": 12.3, "ssim": 0.45}],
    )

    assert result == output_path
    assert output_path.exists()
    cloud = splat_trainer.ply_io.read_3dgs_ply(output_path)
    assert cloud.means.shape == (2, 3)
    sidecar = json.loads((tmp_path / "splat.ply.checkpoint.json").read_text())
    assert sidecar == {
        "reason": "cancelled_by_user",
        "completed_iterations": 125,
        "gaussian_count": 2,
        "training_metrics": [{"iter": 100, "psnr": 12.3, "ssim": 0.45}],
    }


# --- render_flythrough / ffmpeg plumbing (issue #626) ------------------------
#
# The deadlock is between two blocking writes, so a faithful reproduction would
# hang the suite. Instead the fake below raises the moment ffmpeg *would* block,
# turning "this deadlocks" into "this fails fast".


class _StderrPipeFull(RuntimeError):
    """Raised where the real ffmpeg would block writing into an undrained pipe."""


class _FakeStdin:
    def __init__(self, process: _FakeFfmpeg):
        self._process = process
        self.closed = False
        self.frames_written = 0

    def write(self, data: bytes) -> int:
        assert not self.closed, "wrote a frame after closing ffmpeg's stdin"
        self.frames_written += 1
        self._process.consume_frame()
        return len(data)

    def close(self) -> None:
        self.closed = True


class _FakeFfmpeg:
    """Stand-in for the ffmpeg child, modelling only what issue #626 turns on.

    ffmpeg chatters on stderr as it consumes frames, and an OS pipe holds a few
    KB before its writer blocks — a few KB being the Windows ``CreatePipe``
    default, and Windows is this project's primary target.
    """

    pipe_capacity = 4096
    progress_line = (
        b"frame=  120 fps= 29 q=28.0 size=    1024kB time=00:00:04.00 bitrate=N/A speed=1x\r"
    )

    def __init__(self, command, *, stdin=None, stdout=None, stderr=None, exit_code=0):
        self.command = list(command)
        self.stdin = _FakeStdin(self)
        self.returncode = None
        self.killed = False
        self.exit_code = exit_code
        self._stderr_sink = stderr
        self._unread_pipe_bytes = 0
        self._output_path = Path(self.command[-1])

    def _emit_stderr(self, blob: bytes) -> None:
        if self._stderr_sink is subprocess.PIPE:
            self._unread_pipe_bytes += len(blob)
            if self._unread_pipe_bytes > self.pipe_capacity:
                raise _StderrPipeFull(
                    "ffmpeg blocked writing stderr into a pipe nobody is draining "
                    "(the real process would deadlock against our stdin write)"
                )
        elif self._stderr_sink not in (None, subprocess.DEVNULL):
            self._stderr_sink.write(blob)

    def consume_frame(self) -> None:
        self._emit_stderr(self.progress_line)

    def wait(self, timeout=None):
        if self.returncode is None:
            self._emit_stderr(b"[libx264 @ 0xdead] the encoder had something to say\n")
            if self.exit_code == 0:
                self._output_path.parent.mkdir(parents=True, exist_ok=True)
                self._output_path.write_bytes(b"not really an mp4")
            self.returncode = self.exit_code
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self) -> None:
        # Mirrors Popen.kill(): a no-op once the process has been reaped.
        if self.returncode is None:
            self.killed = True
            self.returncode = -9


@contextmanager
def _fake_render_stack(spawned: list, *, exit_code: int = 0, rasterize=None):
    """Run render_flythrough against fake torch/gsplat/ffmpeg on a CPU-only box."""
    torch = MagicMock()
    torch.cuda.is_available.return_value = False
    frame = _ArrayTensor(np.zeros((8, 8, 3)))

    def popen(command, **kwargs):
        process = _FakeFfmpeg(command, exit_code=exit_code, **kwargs)
        spawned.append(process)
        return process

    with (
        patch.object(
            splat_trainer, "_import_training_deps", return_value=(torch, MagicMock())
        ),
        patch.object(splat_trainer.shutil, "which", return_value="/usr/bin/ffmpeg"),
        patch.object(splat_trainer.ply_io, "read_3dgs_ply", return_value=MagicMock()),
        patch.object(
            splat_trainer,
            "_rasterize_cloud",
            side_effect=rasterize or (lambda *a, **k: frame),
        ),
        patch.object(splat_trainer.subprocess, "Popen", side_effect=popen),
    ):
        yield


def _flythrough_keyframes(duration_s: float = 4.0) -> list[dict]:
    return [
        {"position": [0.0, 0.0, 0.0], "target": [0.0, 0.0, 1.0], "duration_s": duration_s},
        {"position": [1.0, 0.5, 0.0], "target": [1.0, 0.0, 1.0], "duration_s": duration_s},
    ]


def _render_flythrough(tmp_path: Path) -> Path:
    return splat_trainer.render_flythrough(
        tmp_path / "splat.ply", tmp_path / "flythrough.mp4", _flythrough_keyframes(),
        fps=30, width=8, height=8,
    )


def test_render_flythrough_survives_more_ffmpeg_stderr_than_a_pipe_holds(tmp_path: Path):
    """#626: stderr must not be a pipe left undrained until the frame loop ends."""
    spawned: list[_FakeFfmpeg] = []
    with _fake_render_stack(spawned):
        result = _render_flythrough(tmp_path)

    # 121 frames of progress chatter is ~10 KB — well past a Windows pipe buffer.
    assert spawned[0].stdin.frames_written == 121
    assert result == tmp_path / "flythrough.mp4"
    assert result.exists()


def test_render_flythrough_asks_ffmpeg_to_stop_chattering(tmp_path: Path):
    """Progress lines are the bulk of the volume; -nostats keeps stderr tiny."""
    spawned: list[_FakeFfmpeg] = []
    with _fake_render_stack(spawned):
        _render_flythrough(tmp_path)

    command = spawned[0].command
    assert "-nostats" in command
    assert command[command.index("-loglevel") + 1] == "error"


def test_render_flythrough_reaps_ffmpeg_when_a_frame_fails(tmp_path: Path):
    """#626: a raise inside the write loop must not leave an orphan ffmpeg."""
    spawned: list[_FakeFfmpeg] = []
    calls = {"n": 0}

    def exploding_rasterize(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 5:
            raise RuntimeError("CUDA kernel went sideways")
        return _ArrayTensor(np.zeros((8, 8, 3)))

    with (
        _fake_render_stack(spawned, rasterize=exploding_rasterize),
        pytest.raises(RuntimeError, match="CUDA kernel went sideways"),
    ):
        _render_flythrough(tmp_path)

    process = spawned[0]
    assert process.stdin.closed
    assert process.killed, "ffmpeg was left running after the render blew up"
    assert process.returncode is not None
    # The lock has to be free for the next GPU job, whatever happened here.
    assert splat_trainer._GPU_LOCK.acquire(timeout=0)
    splat_trainer._GPU_LOCK.release()


def test_render_flythrough_surfaces_ffmpeg_stderr_when_encoding_fails(tmp_path: Path):
    spawned: list[_FakeFfmpeg] = []
    with (
        _fake_render_stack(spawned, exit_code=1),
        pytest.raises(RuntimeError, match="the encoder had something to say"),
    ):
        _render_flythrough(tmp_path)
