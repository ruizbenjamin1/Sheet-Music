"""Preprocesado de fotos de partituras antes del OMR (parte de E1-19).

Pasos:
1. Buscar la hoja: la zona clara más grande de la foto, aproximada por un cuadrilátero.
2. Corregir la perspectiva y recortar el fondo (mesa, teclado, anillado…).
3. Normalizar la iluminación dividiendo por el fondo (la hoja sin tinta, estimada con un
   cierre morfológico y un desenfoque). Así se van las sombras y la luz despareja sin
   binarizar, y las líneas finas del pentagrama no se pierden.
4. Escalar a un tamaño razonable para oemer (que igual lleva todo a unos 3,7 MP).

Si no encuentra una hoja clara (o algo falla), devuelve la imagen original sin tocar.
Nunca debería romper el flujo.

Se usa en `jobs.py` solo con fotos subidas (no con páginas de un PDF).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

# Lado mayor de la imagen con la que se busca la hoja (más rápido y menos ruido).
DETECT_SIDE_PX = 1000
# La hoja tiene que ocupar al menos esta fracción de la foto para recortarla.
MIN_PAGE_AREA = 0.20
# Qué tanto del cuadrilátero tiene que estar cubierto por la zona clara.
MIN_FILL = 0.80
# oemer lleva cada imagen a 3–4,35 MP; apuntamos al medio.
TARGET_PIXELS = 3_700_000
# Margen que se recorta hacia adentro de la hoja ya enderezada, para sacar restos del borde
# (anillado, sombra del canto, fondo). Las partituras tienen márgenes mucho más grandes.
INSET = 0.015


@dataclass
class PreprocessResult:
    image: np.ndarray  # en gris si recortó; si no, la imagen original sin tocar
    cropped: bool  # True si encontró la hoja y la recortó
    quad: np.ndarray | None  # esquinas de la hoja en la foto original (sup-izq, sup-der, inf-der, inf-izq)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Ordena 4 puntos: arriba-izquierda, arriba-derecha, abajo-derecha, abajo-izquierda."""
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = pts[:, 1] - pts[:, 0]
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def _quad_from_contour(contour: np.ndarray) -> np.ndarray | None:
    hull = cv2.convexHull(contour)
    peri = cv2.arcLength(hull, True)
    for frac in (0.01, 0.02, 0.03, 0.05, 0.08):
        approx = cv2.approxPolyDP(hull, frac * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype(np.float32)
        if len(approx) < 4:
            break
    # Si no sale un cuadrilátero limpio, el rectángulo rotado mínimo que lo contiene.
    return cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float32)


def find_page(gray: np.ndarray) -> np.ndarray | None:
    """Busca la hoja en una imagen en gris. Devuelve sus 4 esquinas (en píxeles de `gray`) o None."""
    h, w = gray.shape[:2]
    scale = DETECT_SIDE_PX / max(h, w)
    small = cv2.resize(gray, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else gray
    scale = min(scale, 1.0)
    sh, sw = small.shape[:2]

    side = max(sh, sw)
    blur = cv2.GaussianBlur(small, (5, 5), 0)
    lo, hi = (float(v) for v in np.percentile(blur, [5, 95]))
    if hi - lo < 40:
        return None  # sin contraste entre fondo y papel: no hay hoja que separar
    # Papel = claro respecto del fondo oscuro (umbral global bajo) Y claro respecto de lo que
    # lo rodea (máximo local). Lo segundo deja adentro el papel en sombra y saca el anillado
    # metálico y las cosas grises que están pegadas a la hoja.
    k_local = max(3, round(side * 0.06)) | 1
    local_max = cv2.dilate(blur, cv2.getStructuringElement(cv2.MORPH_RECT, (k_local, k_local)))
    local_max = cv2.blur(local_max, (k_local, k_local))
    mask = ((blur > lo + 0.25 * (hi - lo)) & (blur > 0.6 * local_max)).astype(np.uint8) * 255
    # Apertura: corta uniones finas con otras cosas claras (anillado, teclado, cinta).
    # Se comen también los pentagramas, pero quedan como agujeros adentro de la hoja.
    k_open = max(3, round(side * 0.015)) | 1
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k_open, k_open)))

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
    if n <= 1:
        return None
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    comp = (labels == best).astype(np.uint8) * 255
    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)  # con los agujeros (pentagramas) incluidos
    if area < MIN_PAGE_AREA * sh * sw or area > 0.97 * sh * sw:
        return None  # muy chica, o toda la foto es la hoja (nada que recortar)

    quad = _order_corners(_quad_from_contour(contour))
    quad[:, 0] = np.clip(quad[:, 0], 0, sw - 1)
    quad[:, 1] = np.clip(quad[:, 1], 0, sh - 1)
    quad_area = cv2.contourArea(quad)
    if quad_area <= 0 or not cv2.isContourConvex(quad.reshape(-1, 1, 2).astype(np.int32)):
        return None
    if area / quad_area < MIN_FILL:
        return None  # la mancha clara no tiene forma de hoja

    # Lo de afuera tiene que ser bastante más oscuro que la hoja.
    inside = np.zeros_like(small)
    cv2.fillConvexPoly(inside, quad.astype(np.int32), 255)
    outside = inside == 0
    if outside.mean() > 0.02 and blur[outside].mean() > 0.75 * blur[inside > 0].mean():
        return None
    return quad / scale


def warp_page(gray: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Endereza la hoja: lleva el cuadrilátero a un rectángulo."""
    tl, tr, br, bl = quad
    width = round(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    height = round(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    page = cv2.warpPerspective(gray, m, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    dx, dy = round(width * INSET), round(height * INSET)
    return page[dy : height - dy, dx : width - dx]


def normalize_light(gray: np.ndarray) -> np.ndarray:
    """Saca sombras y luz despareja: divide por el fondo estimado (la hoja sin tinta)."""
    h, w = gray.shape[:2]
    # El elemento tiene que ser más ancho que el trazo más grueso (cabezas de nota, barras).
    k = max(15, round(min(h, w) / 40)) | 1
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    bg = cv2.GaussianBlur(bg, (0, 0), k / 2)
    norm = cv2.divide(gray.astype(np.float32), np.maximum(bg.astype(np.float32), 1.0), scale=255.0)
    norm = np.clip(norm, 0, 255).astype(np.uint8)
    # Estirar el contraste sin cortar los grises de las líneas finas: el papel queda blanco.
    lo = float(np.percentile(norm, 0.5))
    hi = float(np.percentile(norm, 90))
    if hi - lo < 10:
        return norm
    out = (norm.astype(np.float32) - lo) * (255.0 / (hi - lo))
    return np.clip(out, 0, 255).astype(np.uint8)


def resize_for_omr(gray: np.ndarray, target_pixels: int = TARGET_PIXELS) -> np.ndarray:
    h, w = gray.shape[:2]
    ratio = (target_pixels / (h * w)) ** 0.5
    if 0.9 <= ratio <= 1.1:
        return gray
    interp = cv2.INTER_AREA if ratio < 1 else cv2.INTER_CUBIC
    return cv2.resize(gray, (round(w * ratio), round(h * ratio)), interpolation=interp)


def preprocess_image(img: np.ndarray, *, normalize: bool = True, resize: bool = True) -> PreprocessResult:
    """Prepara una foto (BGR o gris) para el OMR.

    No falla: si no encuentra la hoja o algo sale mal, devuelve `img` tal cual con `cropped=False`.
    """
    try:
        gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        quad = find_page(gray)
        if quad is None:
            return PreprocessResult(img, False, None)
        page = warp_page(gray, quad)
        if normalize:
            page = normalize_light(page)
        if resize:
            page = resize_for_omr(page)
        return PreprocessResult(page, True, quad)
    except (cv2.error, ValueError, ZeroDivisionError):
        log.exception("Falló el preprocesado; sigo con la imagen original")
        return PreprocessResult(img, False, None)


def preprocess_file(src: Path, dst: Path, **kwargs) -> bool:
    """Lee `src`, la preprocesa y la guarda en `dst`. Devuelve True si recortó la hoja.

    Si no encuentra la hoja o no puede leer/guardar la imagen, copia los bytes de `src` tal
    cual a `dst` (ojo: entonces `dst` tiene el formato de `src`). Usa imdecode/imencode para
    que ande con rutas con acentos en Windows.
    """
    data = np.fromfile(str(src), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if img is None:
        log.warning("No se pudo decodificar %s para preprocesar; se usa tal cual", src)
        dst.write_bytes(src.read_bytes())
        return False
    result = preprocess_image(img, **kwargs)
    if not result.cropped:
        dst.write_bytes(src.read_bytes())
        return False
    ok, buf = cv2.imencode(dst.suffix or ".png", result.image)
    if not ok:
        dst.write_bytes(src.read_bytes())
        return False
    buf.tofile(str(dst))
    return True
