"""dashboard.styles saf CSS + HTML-builder testleri (Clean Corporate yeniden tasarım)."""
from __future__ import annotations

from dashboard.styles import APP_CSS, header_html


def test_app_css_nonempty_and_hides_chrome() -> None:
    assert isinstance(APP_CSS, str) and len(APP_CSS) > 100
    # Streamlit chrome gizleme + açık zemin zorlama selektörleri.
    assert "#MainMenu" in APP_CSS
    assert 'data-testid="stToolbar"' in APP_CSS or "stToolbar" in APP_CSS
    assert "footer" in APP_CSS
    assert "#ffffff" in APP_CSS or "#f8fafc" in APP_CSS


def test_header_html_contains_brand_and_clock() -> None:
    html = header_html("14:32:05")
    assert "MastGuard" in html
    assert "14:32:05" in html
    assert "mg-header" in html
