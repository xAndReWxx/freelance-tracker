"""
Global configuration: constants, colors, platform definitions, and path helpers.
"""
import sys
import os
import customtkinter as ctk

# ==========================================
# RESOURCE PATHS (PyInstaller support)
# ==========================================

def get_asset_path(filename):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, filename)

def get_settings_path(filename="settings.json"):
    """Get path to settings.json beside the executable/script."""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)

# ==========================================
# NETWORK
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ==========================================
# ICONS
# ==========================================

MOSTAQL_ICON = get_asset_path("assets/icons/mostaql.ico")
NAFEZLY_ICON = get_asset_path("assets/icons/nafezly.ico")
FREELANCEYARD_ICON = get_asset_path("assets/icons/freelanceyard.ico")
KAFIIL_ICON = get_asset_path("assets/icons/kafiil.ico")
KHAMSAT_ICON = get_asset_path("assets/icons/khamsat.ico")
APP_ICON = get_asset_path("assets/icons/FWT.ico")

# ==========================================
# THEME & APPEARANCE
# ==========================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ==========================================
# COLOR PALETTE
# ==========================================

COLORS = {
    "bg_dark":        "#0a0c18",
    "bg_card":        "#12142a",
    "bg_card_hover":  "#1a1d38",
    "bg_sidebar":     "#0e1024",
    "accent":         "#7c6cf0",
    "accent_hover":   "#8e80f8",
    "accent_glow":    "#7c6cf040",
    "success":        "#00e5c0",
    "success_dim":    "#00e5c060",
    "danger":         "#ff6b6b",
    "danger_dim":     "#ff6b6b60",
    "warning":        "#feca57",
    "text_primary":   "#eaeaf5",
    "text_secondary": "#9496b8",
    "text_muted":     "#565880",
    "border":         "#1c1f42",
    "border_accent":  "#2a2d55",
    "tray_btn":       "#1e2148",
    "tray_btn_hover": "#282c58",
}

# ==========================================
# PLATFORMS CONFIGURATION
# ==========================================

PLATFORMS_CONFIG = {
    "Mostaql": {
        "color": "#2ecc71",
        "hover": "#27ae60",
        "icon": MOSTAQL_ICON,
        "default": True,
        "interval": 15
    },
    "Nafezly": {
        "color": "#3498db",
        "hover": "#2980b9",
        "icon": NAFEZLY_ICON,
        "default": True,
        "interval": 20
    },
    "FreelanceYard": {
        "color": "#e74c3c",
        "hover": "#c0392b",
        "icon": FREELANCEYARD_ICON,
        "default": True,
        "interval": 30
    },
    "Kafiil": {
        "color": "#1abc9c",
        "hover": "#16a085",
        "icon": KAFIIL_ICON,
        "default": True,
        "interval": 25
    },
    "Khamsat": {
        "color": "#f39c12",
        "hover": "#d35400",
        "icon": KHAMSAT_ICON,
        "default": True,
        "interval": 10
    }
}

# ==========================================
# INSTALLATION TRACKING
# ==========================================

SUPABASE_URL = "https://rmjxhubrfdoiweeazhjb.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJtanhodWJyZmRvaXdlZWF6aGpiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNzcyOTksImV4cCI6MjA5Mzg1MzI5OX0.eZ_HGWrTFpASCkxy2ynn6SuEr8HZ3SHkOVKQdIgrt04"
