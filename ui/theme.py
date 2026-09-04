"""Minimal glassmorphic-black theme for the single RewardVision window."""

from __future__ import annotations

COLORS = {
    "bg": "#050506",
    "glass": "rgba(0, 0, 0, 0.60)",
    "hairline": "rgba(255, 255, 255, 0.06)",
    "hairline_strong": "rgba(255, 255, 255, 0.12)",
    "accent": "#6C5CE7",
    "accent_soft": "rgba(108, 92, 231, 0.16)",
    "success": "#27E18C",
    "danger": "#FF4D6D",
    "text": "#EDEEF2",
    "text_muted": "#7C808B",
}

FONT_STACK = '"Segoe UI", "Inter", system-ui, sans-serif'


def build_qss() -> str:
    c = COLORS
    return f"""
    * {{ font-family: {FONT_STACK}; color: {c['text']}; font-size: 13px; }}

    QWidget#Root {{ background-color: {c['bg']}; }}

    QLabel#Title {{ color: {c['text']}; font-size: 18px; font-weight: 600; letter-spacing: 0.5px; }}
    QLabel#FolderPath {{ color: {c['text_muted']}; }}
    QLabel#FolderPathSet {{ color: {c['text']}; }}
    QLabel#Status {{ color: {c['text_muted']}; font-size: 12px; }}

    QListWidget {{
        background-color: {c['glass']};
        border: 1px solid {c['hairline']};
        border-top: 1px solid rgba(255,255,255,0.05);
        border-radius: 12px;
        padding: 6px;
        outline: none;
    }}
    QListWidget::item {{
        border-radius: 8px;
        padding: 8px;
        margin: 2px;
        color: {c['text_muted']};
    }}
    QListWidget::item:selected {{
        background-color: {c['accent_soft']};
        color: {c['text']};
    }}
    QListWidget::item:hover {{ color: {c['text']}; }}

    QPushButton {{
        background-color: transparent;
        border: 1px solid {c['hairline_strong']};
        border-radius: 9px;
        padding: 8px 16px;
        color: {c['text']};
    }}
    QPushButton:hover {{ border-color: {c['accent']}; background-color: {c['accent_soft']}; }}
    QPushButton:pressed {{ background-color: rgba(255,255,255,0.04); }}
    QPushButton:disabled {{ color: rgba(255,255,255,0.28); border-color: {c['hairline']}; }}

    QPushButton#Primary {{
        background-color: {c['accent']}; border: none; color: white;
        font-weight: 600; letter-spacing: 0.5px; padding: 9px 22px; border-radius: 10px;
    }}
    QPushButton#Primary:hover {{ background-color: #7e6ff2; }}
    QPushButton#Primary:disabled {{ background-color: rgba(108,92,231,0.25); color: rgba(255,255,255,0.4); }}

    QPushButton#Danger {{
        background-color: transparent; border: 1px solid {c['danger']};
        color: {c['danger']}; font-weight: 600; padding: 9px 22px; border-radius: 10px;
    }}
    QPushButton#Danger:hover {{ background-color: rgba(255,77,109,0.14); }}
    QPushButton#Danger:disabled {{ border-color: {c['hairline']}; color: rgba(255,255,255,0.28); }}

    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['hairline_strong']}; border-radius: 4px; min-height: 28px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['text_muted']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

    QFileDialog, QMessageBox {{ background-color: #0c0c0f; }}
    """
