"""Smart crop: OpenCV face detection on sampled frames keeps the speaker centered."""
from __future__ import annotations

import statistics


def find_face_center_x(media_path: str, start: float, end: float, samples: int = 12) -> float | None:
    """Return the median face-center x as a 0..1 fraction of frame width, or None."""
    try:
        import cv2
    except ImportError:
        return None  # opencv optional: fall back to center crop

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        return None

    cap = cv2.VideoCapture(media_path)
    if not cap.isOpened():
        return None
    try:
        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0
        if not width:
            return None
        centers: list[float] = []
        step = (end - start) / (samples + 1)
        for i in range(1, samples + 1):
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + i * step) * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5,
                                             minSize=(int(width * 0.05), int(width * 0.05)))
            if len(faces) == 0:
                continue
            # largest face = the speaker
            x, _, w, _ = max(faces, key=lambda f: f[2] * f[3])
            centers.append((x + w / 2) / width)
        if len(centers) < max(2, samples // 6):
            return None  # too few detections to trust
        return statistics.median(centers)
    finally:
        cap.release()
