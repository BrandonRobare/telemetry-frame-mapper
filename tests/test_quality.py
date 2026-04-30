from __future__ import annotations

import os
import tempfile

import cv2
import numpy as np

from backend.services.quality import flag_image, score_brightness, score_sharpness


def make_temp_jpeg(array: np.ndarray) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    cv2.imwrite(path, array)
    return path


def test_sharp_image_scores_high():
    img = np.zeros((100, 100), dtype=np.uint8)
    img[::2, ::2] = 255
    img[1::2, 1::2] = 255
    path = make_temp_jpeg(img)
    score = score_sharpness(path)
    assert score > 100
    os.unlink(path)


def test_blurry_image_scores_low():
    img = np.full((100, 100), 128, dtype=np.uint8)
    path = make_temp_jpeg(img)
    score = score_sharpness(path)
    assert score < 10
    os.unlink(path)


def test_brightness_dark_image():
    img = np.full((100, 100), 20, dtype=np.uint8)
    path = make_temp_jpeg(img)
    assert score_brightness(path) < 50
    os.unlink(path)


def test_brightness_bright_image():
    img = np.full((100, 100), 240, dtype=np.uint8)
    path = make_temp_jpeg(img)
    assert score_brightness(path) > 210
    os.unlink(path)


def test_flag_good():
    assert flag_image(sharpness=200.0, brightness=128.0, has_gps=True) == "good"


def test_flag_blurry():
    assert flag_image(sharpness=50.0, brightness=128.0, has_gps=True) == "blurry"


def test_flag_dark():
    assert flag_image(sharpness=200.0, brightness=30.0, has_gps=True) == "dark"


def test_flag_bright():
    assert flag_image(sharpness=200.0, brightness=220.0, has_gps=True) == "bright"


def test_flag_no_gps():
    assert flag_image(sharpness=200.0, brightness=128.0, has_gps=False) == "no_gps"
