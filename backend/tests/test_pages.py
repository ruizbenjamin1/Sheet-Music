import pymupdf as fitz
import pytest

from app.pages import (
    MAX_IMAGE_PIXELS,
    MAX_PAGES,
    PDF_DPI,
    PDF_MAX_SIDE_PX,
    InputError,
    check_upload,
    image_size,
    kind_of,
    pdf_page_dpi,
    sniff_format,
    to_page_images,
)
from tests.helpers import WEBP_HEAD, make_big_pdf, make_jpeg, make_pdf, make_png, png_head, webp_head


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_pdf_de_una_pagina(tmp_path):
    src = _write(tmp_path, "upload.pdf", make_pdf(1))
    images = to_page_images(src, "pdf", tmp_path / "pages")
    assert [p.name for p in images] == ["page_01.png"]
    pix = fitz.Pixmap(str(images[0]))
    assert pix.n == 1  # escala de grises
    assert pix.width == pytest.approx(200 * 300 / 72, abs=2)  # 300 ppp


def test_pdf_de_varias_paginas(tmp_path):
    src = _write(tmp_path, "upload.pdf", make_pdf(3))
    images = to_page_images(src, "pdf", tmp_path / "pages")
    assert [p.name for p in images] == ["page_01.png", "page_02.png", "page_03.png"]
    assert all(p.exists() for p in images)


def test_pdf_justo_en_el_limite(tmp_path):
    src = _write(tmp_path, "upload.pdf", make_pdf(MAX_PAGES))
    assert len(to_page_images(src, "pdf", tmp_path / "pages")) == MAX_PAGES


def test_pdf_con_demasiadas_paginas(tmp_path):
    src = _write(tmp_path, "upload.pdf", make_pdf(MAX_PAGES + 1))
    with pytest.raises(InputError, match="máximo es 10"):
        to_page_images(src, "pdf", tmp_path / "pages")
    assert not list((tmp_path / "pages").glob("*.png"))  # no convirtió nada


def test_pdf_roto(tmp_path):
    src = _write(tmp_path, "upload.pdf", b"%PDF-1.7\nesto no es un pdf de verdad")
    with pytest.raises(InputError, match="No pude"):
        to_page_images(src, "pdf", tmp_path / "pages")


def test_pdf_truncado(tmp_path):
    data = make_pdf(2)
    src = _write(tmp_path, "upload.pdf", data[: len(data) // 3])
    # PyMuPDF a veces repara; si no puede, tiene que ser un InputError en español.
    try:
        to_page_images(src, "pdf", tmp_path / "pages")
    except InputError as exc:
        assert "PDF" in str(exc)


def test_pdf_con_contrasena(tmp_path):
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="clave", owner_pw="clave")
    src = _write(tmp_path, "upload.pdf", data)
    with pytest.raises(InputError, match="contraseña"):
        to_page_images(src, "pdf", tmp_path / "pages")


def test_imagen_se_devuelve_tal_cual(tmp_path):
    src = _write(tmp_path, "upload.png", make_png())
    assert to_page_images(src, "image", tmp_path / "pages") == [src]


def test_kind_of():
    assert kind_of("a.PDF", None) == "pdf"
    assert kind_of("x", "application/pdf") == "pdf"
    assert kind_of("foto.jpeg", None) == "image"
    assert kind_of("x", "image/webp") == "image"
    with pytest.raises(InputError, match="Formato no soportado"):
        kind_of("notas.txt", "text/plain")


def test_sniff_format():
    assert sniff_format(make_pdf(1)) == "pdf"
    assert sniff_format(make_png()) == "png"
    assert sniff_format(make_jpeg()) == "jpeg"
    assert sniff_format(WEBP_HEAD) == "webp"
    with pytest.raises(InputError):
        sniff_format(b"hola, soy un texto")


def test_check_upload_rechaza_tipo_falso():
    with pytest.raises(InputError):
        check_upload("vals.pdf", "application/pdf", b"MZ\x90\x00 un ejecutable")
    with pytest.raises(InputError, match="al revés"):
        check_upload("vals.pdf", "application/pdf", make_png())
    assert check_upload("foto.jpg", "image/jpeg", make_jpeg()) == "jpeg"


# --- Tope de píxeles (E1-15) ---


def test_pdf_con_pagina_enorme_baja_los_ppp(tmp_path):
    # 3000 x 2000 pt (unos 106 x 70 cm): a 300 ppp serían 12500 x 8333 px.
    src = _write(tmp_path, "upload.pdf", make_big_pdf(3000, 2000))
    images = to_page_images(src, "pdf", tmp_path / "pages")
    pix = fitz.Pixmap(str(images[0]))
    assert max(pix.width, pix.height) <= PDF_MAX_SIDE_PX + 1
    assert pix.width == pytest.approx(PDF_MAX_SIDE_PX, abs=2)
    assert pix.height == pytest.approx(PDF_MAX_SIDE_PX * 2000 / 3000, abs=2)


def test_pdf_dpi():
    assert pdf_page_dpi(595, 842) == PDF_DPI  # A4 queda a 300 ppp
    assert pdf_page_dpi(14400, 14400) == pytest.approx(25)  # 200 pulgadas -> 5000 px
    assert pdf_page_dpi(0, 0) == PDF_DPI


def test_image_size_lee_el_encabezado():
    assert image_size(make_png()) == (8, 8)
    assert image_size(make_jpeg()) == (8, 8)
    assert image_size(webp_head(640, 480)) == (640, 480)
    assert image_size(png_head(30000, 20000)) == (30000, 20000)


def test_imagen_con_demasiados_pixeles_se_rechaza(tmp_path):
    # Solo el encabezado dice 30000 x 20000 (600 MP); el archivo pesa unos pocos bytes.
    src = _write(tmp_path, "upload.png", png_head(30000, 20000))
    with pytest.raises(InputError, match="demasiado grande"):
        to_page_images(src, "image", tmp_path / "pages")


def test_webp_con_demasiados_pixeles_se_rechaza(tmp_path):
    src = _write(tmp_path, "upload.webp", webp_head(16000, 16000))
    with pytest.raises(InputError, match="megapíxeles"):
        to_page_images(src, "image", tmp_path / "pages")


def test_imagen_justo_en_el_limite_pasa(tmp_path):
    src = _write(tmp_path, "upload.png", png_head(10000, MAX_IMAGE_PIXELS // 10000))
    assert to_page_images(src, "image", tmp_path / "pages") == [src]


def test_imagen_sin_tamano_legible(tmp_path):
    src = _write(tmp_path, "upload.jpg", bytes([0xFF, 0xD8, 0xFF, 0xD9]))
    with pytest.raises(InputError, match="dañada"):
        to_page_images(src, "image", tmp_path / "pages")
