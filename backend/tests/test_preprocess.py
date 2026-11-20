"""Pruebas del preprocesado de fotos (app/preprocess.py) con imágenes sintéticas."""

import cv2
import numpy as np
import pytest

from app.preprocess import TARGET_PIXELS, find_page, normalize_light, preprocess_file, preprocess_image

PAGE_W, PAGE_H = 850, 1100  # proporción tipo A4/carta


def _page(with_shadow: bool = False) -> np.ndarray:
    """Hoja blanca con 3 pentagramas de líneas finas (1 px) y algunas 'notas'."""
    page = np.full((PAGE_H, PAGE_W), 235, np.uint8)
    for top in (150, 450, 750):
        for i in range(5):
            y = top + i * 14
            cv2.line(page, (80, y), (PAGE_W - 80, y), 30, 1)
        for x in range(150, PAGE_W - 100, 90):
            cv2.ellipse(page, (x, top + 21), (8, 6), -20, 0, 360, 20, -1)
            cv2.line(page, (x + 7, top + 21), (x + 7, top - 25), 20, 2)
    if with_shadow:
        ramp = np.linspace(1.0, 0.55, PAGE_W, dtype=np.float32)[None, :]
        page = (page.astype(np.float32) * ramp).astype(np.uint8)
    return page


def _photo(page: np.ndarray, dst_corners, size=(1200, 1600), bg=25) -> np.ndarray:
    """Pone la hoja en perspectiva sobre un fondo oscuro, como una foto de celular (BGR)."""
    w, h = size
    src = np.float32([[0, 0], [PAGE_W - 1, 0], [PAGE_W - 1, PAGE_H - 1], [0, PAGE_H - 1]])
    m = cv2.getPerspectiveTransform(src, np.float32(dst_corners))
    warped = cv2.warpPerspective(page, m, (w, h), borderValue=0)
    mask = cv2.warpPerspective(np.full_like(page, 255), m, (w, h), borderValue=0)
    rng = np.random.default_rng(0)
    background = np.clip(rng.normal(bg, 6, (h, w)), 0, 255).astype(np.uint8)
    gray = np.where(mask > 0, warped, background)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


CORNERS = [(260, 180), (1010, 260), (1080, 1450), (150, 1380)]  # rotada y en perspectiva


def _staff_rows(img: np.ndarray) -> int:
    """Cuenta filas que son casi enteras oscuras (líneas de pentagrama) en el centro de la imagen."""
    h, w = img.shape
    band = img[:, w // 4 : 3 * w // 4]
    dark = (band < 128).mean(axis=1) > 0.6
    # agrupar filas consecutivas
    return int(np.count_nonzero(dark[1:] & ~dark[:-1]) + dark[0])


def test_encuentra_la_hoja_en_perspectiva():
    photo = _photo(_page(), CORNERS)
    quad = find_page(cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY))
    assert quad is not None
    for found, real in zip(quad, CORNERS):
        assert np.linalg.norm(found - np.float32(real)) < 30


def test_recorta_endereza_y_no_pierde_lineas_finas():
    result = preprocess_image(_photo(_page(), CORNERS))
    assert result.cropped
    img = result.image
    assert img.ndim == 2 and img.dtype == np.uint8
    # Tamaño razonable para oemer y la proporción de la hoja (alta).
    assert img.shape[0] * img.shape[1] == pytest.approx(TARGET_PIXELS, rel=0.05)
    assert img.shape[0] / img.shape[1] == pytest.approx(PAGE_H / PAGE_W, rel=0.08)
    # No quedó fondo oscuro en los bordes.
    assert img[:20].mean() > 200 and img[-20:].mean() > 200
    assert img[:, :20].mean() > 200 and img[:, -20:].mean() > 200
    # Las 15 líneas de pentagrama siguen ahí y quedaron horizontales.
    assert _staff_rows(img) == 15


def test_normaliza_la_sombra_sin_borrar_lineas():
    norm = normalize_light(_page(with_shadow=True))
    paper_left = np.median(norm[50:120, 100:200])
    paper_right = np.median(norm[50:120, PAGE_W - 200 : PAGE_W - 100])
    assert abs(float(paper_left) - float(paper_right)) < 15  # la sombra desapareció
    assert _staff_rows(norm) == 15


def test_sin_hoja_clara_devuelve_la_original():
    rng = np.random.default_rng(1)
    noise = rng.integers(0, 255, (600, 800, 3), dtype=np.uint8)
    result = preprocess_image(noise)
    assert not result.cropped
    assert result.image is noise


def test_escaneo_sin_fondo_devuelve_la_original():
    scan = cv2.cvtColor(_page(), cv2.COLOR_GRAY2BGR)
    result = preprocess_image(scan)
    assert not result.cropped
    assert result.image is scan


def test_preprocess_file(tmp_path):
    src = tmp_path / "foto.jpg"
    ok, buf = cv2.imencode(".jpg", _photo(_page(), CORNERS))
    assert ok
    src.write_bytes(buf.tobytes())
    dst = tmp_path / "página.png"  # con acento: tiene que andar en Windows
    assert preprocess_file(src, dst) is True
    out = cv2.imdecode(np.fromfile(str(dst), np.uint8), cv2.IMREAD_UNCHANGED)
    assert out is not None and out.ndim == 2


def test_preprocess_file_con_basura_copia_tal_cual(tmp_path):
    src = tmp_path / "roto.jpg"
    src.write_bytes(b"esto no es una imagen")
    dst = tmp_path / "salida.png"
    assert preprocess_file(src, dst) is False
    assert dst.read_bytes() == src.read_bytes()
