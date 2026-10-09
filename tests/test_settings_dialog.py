"""Ayarlar penceresi: değişiklikler canlı uygulanır, İptal geri alır."""
from src.overlay.settings_dialog import STYLE_KEYS, SettingsDialog


def test_live_change_and_cancel_restores(qapp, font_family):
    seen = []
    d = SettingsDialog(dict(STYLE_KEYS), font_family, on_change=seen.append)
    d.bold.setChecked(True)
    d.max_px.setValue(40)
    d.opacity.setValue(70)
    d.color.setCurrentIndex(d.color.findData("black"))
    v = d.values()
    assert (v["font_bold"], v["font_max_px"], v["box_opacity"], v["text_color"]) == (True, 40, 70, "black")
    assert seen and seen[-1] == v  # her değişiklik ekrana anında gider
    d.reject()
    assert seen[-1]["font_bold"] is False and seen[-1]["font_max_px"] == 28  # İptal: eski hali


def test_min_max_kept_consistent_and_bundled_font_saved_as_default(qapp, font_family):
    d = SettingsDialog(dict(STYLE_KEYS), font_family)
    d.max_px.setValue(14)
    d.min_px.setValue(20)
    v = d.values()
    assert v["font_min_px"] <= v["font_max_px"]
    assert v["font_family"] == ""  # uygulamayla gelen font "" olarak saklanır
