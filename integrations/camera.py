"""Stilstaand beeld ophalen van een camera via RTSP (bijv. eufy met 'NAS (RTSP)' aan)."""

from __future__ import annotations

import concurrent.futures as cf
import os
import re

# eufy en de meeste camera's werken het betrouwbaarst via TCP.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

_POOL = cf.ThreadPoolExecutor(max_workers=4)


class CameraError(Exception):
    pass


def mask_url(url: str) -> str:
    """rtsp://gebruiker:wachtwoord@ip/live0 -> rtsp://gebruiker:•••@ip/live0"""
    return re.sub(r"(//[^:/@]+:)[^@]+@", r"\1•••@", url)


def _grab(url: str, timeout_s: float) -> bytes:
    import cv2

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    try:
        for prop in ("CAP_PROP_OPEN_TIMEOUT_MSEC", "CAP_PROP_READ_TIMEOUT_MSEC"):
            if hasattr(cv2, prop):
                cap.set(getattr(cv2, prop), timeout_s * 1000)
        if not cap.isOpened():
            raise CameraError("Kan de stream niet openen. Klopt het adres, en staat RTSP aan in de app?")
        frame = None
        for _ in range(5):  # de eerste beelden zijn soms grijs of half
            ok, f = cap.read()
            if ok:
                frame = f
        if frame is None:
            raise CameraError("Verbinding gemaakt, maar geen beeld ontvangen.")
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise CameraError("Kon het beeld niet omzetten naar JPEG.")
        return jpg.tobytes()
    finally:
        cap.release()


def snapshot(url: str, timeout_s: float = 8.0) -> bytes:
    """Geeft één JPEG-beeld van de camera. Gooit CameraError bij problemen."""
    fut = _POOL.submit(_grab, url, timeout_s)
    try:
        return fut.result(timeout=timeout_s + 4)
    except cf.TimeoutError:
        raise CameraError("De camera reageert niet (time-out).") from None
    except CameraError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CameraError(str(exc)) from exc
