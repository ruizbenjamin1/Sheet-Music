import pymupdf as fitz
import pytest

from app.pages import (
    MAX_PAGES,
    InputError,
    check_upload,
    kind_of,
    sniff_format,
    to_page_images,
)
from tests.helpers import WEBP_HEAD, make_jpeg, make_pdf, make_png


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
