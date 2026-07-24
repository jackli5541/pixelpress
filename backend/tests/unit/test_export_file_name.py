import pytest

from app.services.export_service import validate_export_file_name


def test_export_file_name_accepts_windows_safe_unicode_name():
    assert validate_export_file_name(" 家庭旅行.PDF ", "pdf") == "家庭旅行.pdf"


@pytest.mark.parametrize("file_name", ["wrong.html", "bad/name.pdf", "CON.pdf", "bad?.pdf", "x" * 117 + ".pdf"])
def test_export_file_name_rejects_invalid_windows_names(file_name):
    with pytest.raises(ValueError):
        validate_export_file_name(file_name, "pdf")
