import customtkinter as ctk
import threading
import time
import requests
import os
import webbrowser
import re
from datetime import datetime
from PIL import Image

from config import COLORS, PLATFORMS_CONFIG, get_asset_path, HEADERS
from managers.settings_manager import SettingsManager
from managers.startup_manager import StartupManager
from managers.install_tracker import InstallTracker
from managers.notification_manager import NotificationManager
from managers.tray_manager import TrayManager
from scrapers import SCRAPER_REGISTRY


class FreelanceTrackerApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        # ---- Window Setup ----
        self.title("Freelance Tracker")
        self.geometry("1050x720")
        self.minsize(940, 700)
        self.configure(fg_color=COLORS["bg_dark"])

        try:
            self.iconbitmap(get_asset_path("assets/icons/FWT.ico"))
        except Exception:
            pass

        # ---- State ----
        self.is_monitoring = False
        self.workers = []
        self.seen_projects = {}     
        self.seen_lock = threading.Lock() 
        self.project_list = []      
        self.card_widgets = []      
        
        self.platform_vars = {}
        self.platform_cbs = {}
        for site, config in PLATFORMS_CONFIG.items():
            self.platform_vars[site] = ctk.BooleanVar(value=config["default"])

        self._icon_cache = {}
        for site, config in PLATFORMS_CONFIG.items():
            icon_path = config.get("icon", "")
            self._icon_cache[site] = self._load_platform_icon(icon_path, site[0], config["color"])
            
        self.session_new = 0

        # ---- Managers ----
        self.settings = SettingsManager()
        self.settings.load()
        
        # We need UI Vars for switches to bind to settings
        self.ui_filters_enabled = ctk.BooleanVar(value=self.settings.filters_enabled)
        self.ui_notifications_enabled = ctk.BooleanVar(value=self.settings.notifications_enabled)
        self.ui_autostart_enabled = ctk.BooleanVar(value=self.settings.autostart_enabled)

        self.startup_mgr = StartupManager()
        self.startup_mgr.sync(self.settings.autostart_enabled)
        
        self.notif_mgr = NotificationManager(self.settings)
        self.tray_mgr = TrayManager(self)
        self.tracker = InstallTracker(self.settings, self)
        self.tracker.run_silently()

        # ---- Build UI ----
        self._build_layout()
        self._build_sidebar()
        self._build_main_area()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ==========================================
    # LAYOUT
    # ==========================================

    def _build_layout(self):
        self.grid_columnconfigure(0, weight=0, minsize=260)
        self.grid_columnconfigure(1, weight=1, minsize=500)
        self.grid_rowconfigure(0, weight=1)

    def _load_platform_icon(self, icon_path, fallback_text, fallback_color):
        try:
            if os.path.exists(icon_path):
                img = Image.open(icon_path)
                return ctk.CTkImage(light_image=img, dark_image=img, size=(24, 24))
        except Exception:
            pass
        try:
            from PIL import ImageDraw
            img = Image.new("RGBA", (64, 64), (0,0,0,0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((0, 0, 64, 64), fill=fallback_color)
            return ctk.CTkImage(light_image=img, dark_image=img, size=(24, 24))
        except Exception:
            return None

    # ==========================================
    # SIDEBAR
    # ==========================================

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, fg_color=COLORS["bg_sidebar"], corner_radius=0, border_width=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(14, weight=1)

        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.grid(row=0, column=0, padx=20, pady=(28, 4), sticky="w")

        fwt_img = self._load_platform_icon(get_asset_path("assets/icons/FWT.ico"), "", COLORS["accent"])

        dot = ctk.CTkLabel(logo_frame, text="" if fwt_img else "⚡", image=fwt_img, font=ctk.CTkFont(size=22), text_color=COLORS["accent"])
        dot.grid(row=0, column=0, padx=(0, 8))

        brand = ctk.CTkLabel(logo_frame, text="Freelance Tracker", font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"), text_color=COLORS["text_primary"])
        brand.grid(row=0, column=1)

        subtitle = ctk.CTkLabel(sidebar, text="Monitor Freelance Platforms", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=COLORS["text_muted"], anchor="w")
        subtitle.grid(row=1, column=0, padx=52, pady=(0, 14), sticky="w")

        self._divider(sidebar, row=2)

        section_label = ctk.CTkLabel(sidebar, text="PLATFORMS", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=COLORS["text_muted"], anchor="w")
        section_label.grid(row=3, column=0, padx=24, pady=(12, 6), sticky="w")

        row_idx = 4
        for site, config in PLATFORMS_CONFIG.items():
            platform_frame = ctk.CTkFrame(sidebar, fg_color="transparent", corner_radius=8)
            pad_bottom = 8 if row_idx - 4 == len(PLATFORMS_CONFIG) - 1 else 2
            platform_frame.grid(row=row_idx, column=0, padx=16, pady=(0, pad_bottom), sticky="ew")

            def on_enter(e, f=platform_frame): f.configure(fg_color=COLORS["bg_card_hover"])
            def on_leave(e, f=platform_frame): f.configure(fg_color="transparent")
            platform_frame.bind("<Enter>", on_enter)
            platform_frame.bind("<Leave>", on_leave)

            cb = ctk.CTkCheckBox(
                platform_frame, text=site, variable=self.platform_vars[site],
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=COLORS["text_primary"], fg_color=config["color"],
                hover_color=config.get("hover", config["color"]),
                border_color=COLORS["border"], checkmark_color="#ffffff",
                corner_radius=6, border_width=2
            )
            cb.pack(side="left", pady=4, padx=(12, 0))
            cb.bind("<Enter>", on_enter)
            cb.bind("<Leave>", on_leave)

            icon_img = self._icon_cache.get(site)
            if icon_img:
                icon_lbl = ctk.CTkLabel(platform_frame, text="", image=icon_img)
                icon_lbl.pack(side="right", padx=(0, 12), pady=4)
                icon_lbl.bind("<Enter>", on_enter)
                icon_lbl.bind("<Leave>", on_leave)
            
            self.platform_cbs[site] = cb
            row_idx += 1

        self._divider(sidebar, row=row_idx)
        row_idx += 1

        stats_label = ctk.CTkLabel(sidebar, text="STATISTICS", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=COLORS["text_muted"], anchor="w")
        stats_label.grid(row=row_idx, column=0, padx=24, pady=(10, 6), sticky="w")
        row_idx += 1

        stats_frame = ctk.CTkFrame(sidebar, fg_color=COLORS["bg_card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        stats_frame.grid(row=row_idx, column=0, padx=18, pady=(0, 6), sticky="ew")

        self.stat_new = self._stat_row(stats_frame, "New Projects", "0", COLORS["success"], 0)
        self.stat_tracked = self._stat_row(stats_frame, "Tracked", "0", COLORS["text_muted"], 1)
        row_idx += 1

        sidebar.grid_rowconfigure(row_idx, weight=1)
        row_idx += 1

        self.status_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        self.status_frame.grid(row=row_idx, column=0, padx=20, pady=(0, 8), sticky="ew")
        row_idx += 1

        self.status_dot = ctk.CTkLabel(self.status_frame, text="●", font=ctk.CTkFont(size=12), text_color=COLORS["danger"])
        self.status_dot.grid(row=0, column=0, padx=(0, 6))

        self.status_text = ctk.CTkLabel(self.status_frame, text="Stopped", font=ctk.CTkFont(family="Segoe UI", size=12), text_color=COLORS["text_secondary"])
        self.status_text.grid(row=0, column=1)

        self.tray_btn = ctk.CTkButton(
            sidebar, text="🔽  Minimize to Tray", font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=COLORS["tray_btn"], hover_color=COLORS["tray_btn_hover"], text_color=COLORS["text_secondary"],
            corner_radius=10, height=32, command=self.tray_mgr.hide
        )
        self.tray_btn.grid(row=row_idx, column=0, padx=18, pady=(6, 4), sticky="ew")
        row_idx += 1

        self.toggle_btn = ctk.CTkButton(
            sidebar, text="▶  Start Monitoring", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="#ffffff",
            corner_radius=12, height=42, command=self._toggle_monitoring
        )
        self.toggle_btn.grid(row=row_idx, column=0, padx=18, pady=(4, 18), sticky="ew")

    # ==========================================
    # MAIN CONTENT AREA
    # ==========================================

    def _build_main_area(self):
        main = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_rowconfigure(2, weight=0)
        main.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(main, fg_color=COLORS["bg_card"], corner_radius=0, height=56, border_width=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(header, text="📋  Project Feed", font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), text_color=COLORS["text_primary"])
        title.grid(row=0, column=0, padx=24, pady=14, sticky="w")

        self.feed_count = ctk.CTkLabel(header, text="No projects yet", font=ctk.CTkFont(family="Segoe UI", size=12), text_color=COLORS["text_muted"])
        self.feed_count.grid(row=0, column=1, padx=(0, 24), pady=14, sticky="e")

        self.notif_switch = ctk.CTkSwitch(
            header, text="Notifications", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            variable=self.ui_notifications_enabled,
            progress_color=COLORS["success"] if self.ui_notifications_enabled.get() else COLORS["danger"],
            button_color="#ffffff", button_hover_color="#f0f0f0", command=self._on_notif_toggle
        )
        self.notif_switch.grid(row=0, column=2, padx=(0, 20), pady=14, sticky="e")

        self.autostart_switch = ctk.CTkSwitch(
            header, text="Auto Start", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            variable=self.ui_autostart_enabled,
            progress_color=COLORS["success"] if self.ui_autostart_enabled.get() else COLORS["danger"],
            button_color="#ffffff", button_hover_color="#f0f0f0", command=self._on_autostart_toggle
        )
        self.autostart_switch.grid(row=0, column=3, padx=(0, 20), pady=14, sticky="e")

        clear_btn = ctk.CTkButton(
            header, text="🗑  Clear", font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="transparent", hover_color=COLORS["bg_card_hover"], text_color=COLORS["text_secondary"],
            corner_radius=8, width=80, height=32, command=self._clear_feed
        )
        clear_btn.grid(row=0, column=4, padx=(0, 24), pady=14, sticky="e")

        self.feed_scroll = ctk.CTkScrollableFrame(main, fg_color=COLORS["bg_dark"], corner_radius=0, scrollbar_button_color=COLORS["border"], scrollbar_button_hover_color=COLORS["text_muted"])
        self.feed_scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.feed_scroll.grid_columnconfigure(0, weight=1)

        self.empty_label = ctk.CTkLabel(
            self.feed_scroll, text="🚀\n\nStart monitoring to see new projects here\n\nSelect platforms and click 'Start Monitoring'",
            font=ctk.CTkFont(family="Segoe UI", size=14), text_color=COLORS["text_muted"], justify="center"
        )
        self.empty_label.pack(pady=120)

        self._build_filter_panel(main)

        self.log_bar = ctk.CTkLabel(main, text="  Ready", font=ctk.CTkFont(family="Consolas", size=11), text_color=COLORS["text_muted"], fg_color=COLORS["bg_sidebar"], anchor="w", height=28, corner_radius=0)
        self.log_bar.grid(row=3, column=0, sticky="ew")

    # ==========================================
    # FILTER PANEL BUILDER
    # ==========================================

    def _build_filter_panel(self, parent):
        self._filter_expanded = True
        self.filter_panel = ctk.CTkFrame(parent, fg_color=COLORS["bg_sidebar"], corner_radius=0, border_width=0)
        self.filter_panel.grid(row=2, column=0, sticky="ew")
        self.filter_panel.grid_columnconfigure(0, weight=1)

        topbar = ctk.CTkFrame(self.filter_panel, fg_color="transparent")
        topbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(6, 4))
        topbar.grid_columnconfigure(1, weight=1)

        self.filter_arrow = ctk.CTkButton(
            topbar, text="▲ Smart Filters", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="transparent", hover_color=COLORS["bg_card"], text_color=COLORS["accent"],
            width=120, height=24, corner_radius=6, anchor="w", command=self._toggle_filter_panel
        )
        self.filter_arrow.grid(row=0, column=0, sticky="w")

        self.filter_toggle = ctk.CTkSwitch(
            topbar, text="Active", variable=self.ui_filters_enabled,
            font=ctk.CTkFont(family="Segoe UI", size=11), text_color=COLORS["text_secondary"],
            fg_color=COLORS["border"], progress_color=COLORS["accent"], button_color=COLORS["text_primary"],
            button_hover_color=COLORS["accent_hover"], width=40, height=20,
            command=self._on_filter_toggle
        )
        self.filter_toggle.grid(row=0, column=1, sticky="e")

        self.filter_body = ctk.CTkFrame(self.filter_panel, fg_color="transparent")
        self.filter_body.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))
        self.filter_body.grid_columnconfigure(1, weight=1)

        self.kw_entry = ctk.CTkEntry(
            self.filter_body, placeholder_text="Add keyword and press Enter...",
            font=ctk.CTkFont(family="Segoe UI", size=12), fg_color=COLORS["bg_card"],
            border_color=COLORS["border"], text_color=COLORS["text_primary"], height=30, corner_radius=8, width=200
        )
        self.kw_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.kw_entry.bind("<Return>", lambda e: self._add_keyword())

        ctk.CTkButton(
            self.filter_body, text="+", font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="#fff", width=30, height=30, corner_radius=8,
            command=self._add_keyword
        ).grid(row=0, column=1, sticky="w")

        self.chips_frame = ctk.CTkScrollableFrame(
            self.filter_body, fg_color="transparent", corner_radius=0, height=34, orientation="horizontal",
            scrollbar_button_color=COLORS["border"], scrollbar_button_hover_color=COLORS["text_muted"]
        )
        self.chips_frame.grid(row=0, column=2, sticky="ew", padx=(10, 0))
        self.filter_body.grid_columnconfigure(2, weight=1)

        self._refresh_chips()

    def _toggle_filter_panel(self):
        if self._filter_expanded:
            self.filter_body.grid_remove()
            self.filter_arrow.configure(text="▼ Smart Filters")
            self._filter_expanded = False
        else:
            self.filter_body.grid()
            self.filter_arrow.configure(text="▲ Smart Filters")
            self._filter_expanded = True

    def _on_filter_toggle(self):
        self.settings.filters_enabled = self.ui_filters_enabled.get()
        self.settings.save()

    # ==========================================
    # HELPERS
    # ==========================================

    def _divider(self, parent, row):
        div = ctk.CTkFrame(parent, fg_color=COLORS["border"], height=1, corner_radius=0)
        div.grid(row=row, column=0, sticky="ew", padx=18)

    def _stat_row(self, parent, label, value, color, row):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, padx=16, pady=(12, 6), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=0)
        lbl = ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(family="Segoe UI", size=12), text_color=COLORS["text_secondary"], anchor="w")
        lbl.grid(row=0, column=0, sticky="w", padx=(0, 12))
        val = ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"), text_color=color, anchor="e")
        val.grid(row=0, column=1, sticky="e", padx=(0, 4))
        return val

    def _update_log(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_bar.configure(text=f"  [{timestamp}] {text}")

    def _update_stats(self):
        self.stat_new.configure(text=str(self.session_new))
        self.stat_tracked.configure(text=str(len(self.seen_projects)))
        self.feed_count.configure(text=f"{len(self.project_list)} new project{'s' if len(self.project_list) != 1 else ''}")

    def _refresh_scroll_region(self):
        try:
            self.feed_scroll.update_idletasks()
            canvas = self.feed_scroll._parent_canvas
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    # ==========================================
    # SETTINGS TOGGLES
    # ==========================================

    def _on_autostart_toggle(self):
        state = self.ui_autostart_enabled.get()
        self.settings.autostart_enabled = state
        self.settings.save()
        if state:
            self.autostart_switch.configure(progress_color=COLORS["success"])
            self._update_log("Auto Start Enabled")
            self.startup_mgr.enable()
        else:
            self.autostart_switch.configure(progress_color=COLORS["danger"])
            self._update_log("Auto Start Disabled")
            self.startup_mgr.disable()

    def _on_notif_toggle(self):
        state = self.ui_notifications_enabled.get()
        self.settings.notifications_enabled = state
        self.settings.save()
        if state:
            self.notif_switch.configure(progress_color=COLORS["success"])
            self._update_log("Notifications Enabled")
        else:
            self.notif_switch.configure(progress_color=COLORS["danger"])
            self._update_log("Notifications Disabled")
            
        if self.tray_mgr.tray_icon:
            self.tray_mgr.tray_icon.update_menu()
            
    def _sync_notification_ui(self):
        self.ui_notifications_enabled.set(self.settings.notifications_enabled)
        self._on_notif_toggle()

    # ==========================================
    # KEYWORD CHIPS
    # ==========================================

    def _add_keyword(self):
        kw = self.kw_entry.get()
        if self.settings.add_keyword(kw):
            self.kw_entry.delete(0, "end")
            self._refresh_chips()
            self._update_log(f"Filter added: {kw.strip().lower()}")

    def _remove_keyword(self, kw):
        self.settings.remove_keyword(kw)
        self._refresh_chips()

    def _refresh_chips(self):
        for w in self.chips_frame.winfo_children():
            w.destroy()

        if not self.settings.keywords:
            ctk.CTkLabel(self.chips_frame, text="No filters active", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=COLORS["text_muted"]).grid(row=0, column=0, padx=8, pady=6)
            return

        for col, kw in enumerate(self.settings.keywords):
            chip = ctk.CTkFrame(self.chips_frame, fg_color=COLORS["accent"], corner_radius=14)
            chip.grid(row=0, column=col, padx=(0, 5), pady=2)
            ctk.CTkLabel(chip, text=kw, font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#ffffff").grid(row=0, column=0, padx=(8, 2), pady=3)
            ctk.CTkButton(chip, text="✕", font=ctk.CTkFont(size=9, weight="bold"), fg_color="transparent", hover_color=COLORS["accent_hover"], text_color="#dddddd", width=18, height=18, corner_radius=9, command=lambda k=kw: self._remove_keyword(k)).grid(row=0, column=1, padx=(0, 4), pady=3)

    # ==========================================
    # PROJECT CARD
    # ==========================================

    def _add_project_card(self, project):
        if self.empty_label.winfo_exists():
            try:
                self.empty_label.destroy()
            except Exception:
                pass

        card_index = len(self.project_list)
        desc_text  = project.description or "No description available"
        PREVIEW_LEN = 160
        is_long     = len(desc_text) > PREVIEW_LEN
        expanded    = [False]

        card = ctk.CTkFrame(self.feed_scroll, fg_color=COLORS["bg_card"], corner_radius=14, border_width=1, border_color=COLORS["border"])
        if self.card_widgets:
            card.pack(fill="x", padx=14, pady=(6, 3), before=self.card_widgets[0])
        else:
            card.pack(fill="x", padx=14, pady=(6, 3))

        card.grid_columnconfigure(0, weight=1)

        def _on_enter(e): card.configure(border_color=COLORS["border_accent"])
        def _on_leave(e): card.configure(border_color=COLORS["border"])
        card.bind("<Enter>", _on_enter)
        card.bind("<Leave>", _on_leave)

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        top_row.grid_columnconfigure(1, weight=1)

        site_name = project.site
        site_config = PLATFORMS_CONFIG.get(site_name, {})
        icon_img = self._icon_cache.get(site_name)
            
        if icon_img:
            badge = ctk.CTkLabel(top_row, text="", image=icon_img)
        else:
            badge_color = site_config.get("color", COLORS["text_muted"])
            badge_letter = site_name[0].upper() if site_name else "?"
            badge = ctk.CTkLabel(top_row, text=badge_letter, font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color="#ffffff", fg_color=badge_color, corner_radius=8, width=32, height=32)
        badge.grid(row=0, column=0, padx=(0, 10), sticky="w")

        title_lbl = ctk.CTkLabel(top_row, text=project.title, font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color=COLORS["text_primary"], anchor="w", justify="left")
        title_lbl.grid(row=0, column=1, sticky="w")

        site_color = site_config.get("color", COLORS["text_muted"])
        platform_lbl = ctk.CTkLabel(top_row, text=site_name, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=site_color, fg_color="transparent")
        platform_lbl.grid(row=0, column=2, padx=(10, 4), sticky="e")

        detected_at = project.detected_at or datetime.now()
        local_time = detected_at.strftime("%I:%M %p")
        time_lbl = ctk.CTkLabel(top_row, text=f"[{local_time}]", font=ctk.CTkFont(family="Consolas", size=10), text_color=COLORS["text_muted"])
        time_lbl.grid(row=0, column=3, padx=(0, 8), sticky="e")

        budget_text = project.budget.strip() if project.budget else ""
        if not budget_text:
            budget_text = "Budget not specified"
            b_color = COLORS["text_muted"]
            b_bg = "transparent"
        else:
            if not any(x in budget_text.lower() for x in ["budget", "ميزانية", "سعر", "price"]):
                budget_text = f"Budget: {budget_text}"
            b_color = COLORS["success"]
            b_bg = COLORS["bg_dark"]

        budget_lbl = ctk.CTkLabel(top_row, text=budget_text, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=b_color, fg_color=b_bg, corner_radius=6, padx=8, pady=4)
        budget_lbl.grid(row=0, column=4, padx=(0, 12), sticky="e")

        link = project.link
        ctk.CTkButton(top_row, text="Open →", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="#ffffff", corner_radius=8, width=68, height=28, command=lambda url=link: webbrowser.open(url)).grid(row=0, column=5, sticky="e")

        desc_row = ctk.CTkFrame(card, fg_color="transparent")
        desc_row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        desc_row.grid_columnconfigure(0, weight=1)

        clean_desc = desc_text.replace("\n", "  ").strip()
        preview = clean_desc[:PREVIEW_LEN].rstrip() + ("…" if is_long else "")
        
        is_arabic = bool(re.search(r"[\u0600-\u06FF]", desc_text))
        desc_anchor = "ne" if is_arabic else "nw"
        desc_justify = "right" if is_arabic else "left"
        desc_sticky = "e" if is_arabic else "w"
        
        desc_lbl = ctk.CTkLabel(desc_row, text=preview, font=ctk.CTkFont(family="Segoe UI", size=11), text_color=COLORS["text_secondary"], anchor=desc_anchor, justify=desc_justify)
        desc_lbl.grid(row=0, column=0, sticky=desc_sticky)

        def _toggle(event=None):
            if not is_long: return
            if expanded[0]:
                desc_lbl.configure(text=preview)
                expanded[0] = False
                self.feed_scroll.after(50, self._refresh_scroll_region)
            else:
                desc_lbl.configure(text=desc_text)
                expanded[0] = True

        if is_long:
            card.configure(cursor="hand2")
            desc_lbl.configure(cursor="hand2")
            title_lbl.configure(cursor="hand2")
            top_row.configure(cursor="hand2")
            desc_row.configure(cursor="hand2")
            for w in [card, top_row, desc_row, desc_lbl, title_lbl, platform_lbl, time_lbl, budget_lbl, badge]:
                w.bind("<Button-1>", _toggle)

        def _on_card_resize(event, _last_w=[0]):
            if event.width == _last_w[0]: return
            _last_w[0] = event.width
            safe_title_width = event.width - 260
            if safe_title_width > 150: title_lbl.configure(wraplength=safe_title_width)
            safe_desc_width = min(event.width - 32, 850)
            if safe_desc_width > 150: desc_lbl.configure(wraplength=safe_desc_width)
                
        card.bind("<Configure>", _on_card_resize)

        self.project_list.insert(0, project)
        self.card_widgets.insert(0, card)
        
        MAX_FEED_CARDS = 100
        if len(self.card_widgets) > MAX_FEED_CARDS:
            oldest_card = self.card_widgets.pop()
            if oldest_card and oldest_card.winfo_exists():
                oldest_card.destroy()
            if self.project_list:
                self.project_list.pop()
                
        self._update_stats()

    def _clear_feed(self):
        for widget in self.feed_scroll.winfo_children():
            widget.destroy()

        self.project_list.clear()
        self.card_widgets.clear()
        self.session_new = 0

        self.empty_label = ctk.CTkLabel(
            self.feed_scroll, text="🧹\n\nFeed cleared\n\nNew projects will appear here",
            font=ctk.CTkFont(family="Segoe UI", size=14), text_color=COLORS["text_muted"], justify="center"
        )
        self.empty_label.grid(row=0, column=0, pady=120)
        self._update_stats()

    # ==========================================
    # MONITORING LOGIC
    # ==========================================

    def _platform_worker(self, site, config):
        session = requests.Session()
        session.headers.update(HEADERS)
        interval = config.get("interval", 20)
        scraper_class = SCRAPER_REGISTRY.get(site)
        if not scraper_class:
            return
            
        scraper = scraper_class()
        
        try:
            try:
                initial = scraper.scrape(session)
                count = 0
                for p in initial:
                    if p.link:
                        with self.seen_lock:
                            self.seen_projects[p.link] = True
                        count += 1
                self.after(0, lambda c=count, s=site: self._update_log(f"[{s}] Skipped {c} existing projects"))
            except Exception as e:
                self.after(0, lambda err=e, s=site: self._update_log(f"[{s}] Load error: {err}"))
                
            time.sleep(2)

            while self.is_monitoring:
                try:
                    projects = scraper.scrape(session)
                    self.after(0, lambda s=site: self._update_log(f"Checked {s} ✓"))
                    
                    for project in reversed(projects):
                        unique_id = project.link
                        if not unique_id:
                            continue
                            
                        is_new = False
                        with self.seen_lock:
                            if unique_id not in self.seen_projects:
                                self.seen_projects[unique_id] = True
                                is_new = True
                                
                                if len(self.seen_projects) > 3000:
                                    first_key = next(iter(self.seen_projects))
                                    del self.seen_projects[first_key]
                                    
                        if is_new:
                            project.detected_at = datetime.now()
                            self.after(0, lambda p=project: self._update_log(f"Fetching details: {p.title[:40]}..."))
                            
                            desc, budget = scraper.fetch_full_description(project, session)
                            project.description = desc
                            if budget and not project.budget:
                                project.budget = budget

                            if self.settings.matches_filters(project):
                                def _on_new_project(p=project):
                                    self.session_new += 1
                                    self._add_project_card(p)
                                self.after(0, _on_new_project)
                                self.notif_mgr.send(project)
                                self.after(0, lambda p=project: self._update_log(f"🆕 {p.site}: {p.title[:50]}"))
                            else:
                                self.after(0, lambda p=project: self._update_log(f"Filtered out: {p.title[:40]}"))
                                
                except Exception as e:
                    self.after(0, lambda err=e, s=site: self._update_log(f"{s} error: {err}"))

                for _ in range(interval):
                    if not self.is_monitoring:
                        break
                    time.sleep(1)
        finally:
            session.close()

    def _khamsat_worker(self, config):
        """
        Specialized worker for Khamsat ID-based crawling.

        Startup:
        - Calls establish_baseline() ONCE to discover the true frontier.
          This scans forward (listing page + HEAD probes) silently —
          no UI cards, no notifications, no sounds.
        - Persists the frontier immediately.

        Main loop:
        - Only IDs beyond the frontier trigger UI/notifications.
        - High-water mark + seen cache saved on every detection.
        """
        from scrapers.khamsat import KhamsatScraper

        session = requests.Session()
        session.headers.update(HEADERS)
        interval = config.get("interval", 20)

        scraper = KhamsatScraper()
        scraper.set_last_id(self.settings.last_khamsat_id)

        # ── Restore persisted seen-cache ─────────────────────────────
        if self.settings.khamsat_recent_seen:
            scraper.load_seen_cache(self.settings.khamsat_recent_seen)

        self.after(0, lambda: self._update_log(
            f"[Khamsat] Establishing baseline from #{self.settings.last_khamsat_id}..."
        ))

        # ── Silent baseline — find the true frontier ─────────────────
        # This scans forward (listing page + batched HEAD probes) to
        # discover the latest valid request ID.  Returns nothing to UI.
        try:
            baseline_id = scraper.establish_baseline(session)
        except Exception as e:
            baseline_id = scraper.get_last_id()
            self.after(0, lambda err=e: self._update_log(
                f"[Khamsat] Baseline error: {err}"
            ))

        # Persist the baseline immediately
        if baseline_id > self.settings.last_khamsat_id:
            self.settings.last_khamsat_id = baseline_id
        self.settings.khamsat_recent_seen = scraper.get_seen_cache()
        self.settings.save()

        self.after(0, lambda cid=baseline_id: self._update_log(
            f"[Khamsat] Baseline at #{cid} — monitoring for new requests"
        ))

        # ── Main monitoring loop ─────────────────────────────────────
        # Everything from here is genuinely new (post-baseline).
        try:
            while self.is_monitoring:
                for _ in range(interval):
                    if not self.is_monitoring:
                        break
                    time.sleep(1)

                if not self.is_monitoring:
                    break

                try:
                    projects = scraper.scrape(session)
                    current_id = scraper.get_last_id()

                    # ── Persist state immediately on detection ────────
                    if current_id > self.settings.last_khamsat_id or projects:
                        self.settings.last_khamsat_id = current_id
                        self.settings.khamsat_recent_seen = scraper.get_seen_cache()
                        self.settings.save()

                    found = len(projects)
                    self.after(0, lambda f=found, cid=current_id: self._update_log(
                        f"Checked Khamsat ✓ (ID→{cid}, found {f})"
                    ))

                    for project in projects:
                        unique_id = project.link
                        if not unique_id:
                            continue

                        is_new = False
                        with self.seen_lock:
                            if unique_id not in self.seen_projects:
                                self.seen_projects[unique_id] = True
                                is_new = True

                                if len(self.seen_projects) > 3000:
                                    first_key = next(iter(self.seen_projects))
                                    del self.seen_projects[first_key]

                        if is_new:
                            project.detected_at = datetime.now()

                            if self.settings.matches_filters(project):
                                def _on_new_project(p=project):
                                    self.session_new += 1
                                    self._add_project_card(p)
                                self.after(0, _on_new_project)
                                self.notif_mgr.send(project)
                                self.after(0, lambda p=project: self._update_log(
                                    f"🆕 Khamsat: {p.title[:50]}"
                                ))
                            else:
                                self.after(0, lambda p=project: self._update_log(
                                    f"Filtered out: {p.title[:40]}"
                                ))

                except Exception as e:
                    self.after(0, lambda err=e: self._update_log(f"Khamsat error: {err}"))
        finally:
            session.close()

    def _toggle_monitoring(self):
        if not self.is_monitoring:
            any_selected = any(var.get() for var in self.platform_vars.values())
            if not any_selected:
                self._update_log("⚠ Select at least one platform!")
                return

            self.is_monitoring = True
            with self.seen_lock:
                self.seen_projects.clear()
            self.workers = []

            self.toggle_btn.configure(text="■  Stop Monitoring", fg_color=COLORS["danger"], hover_color="#e05555")
            self.status_dot.configure(text_color=COLORS["success"])
            self.status_text.configure(text="Monitoring...")
            for cb in self.platform_cbs.values():
                cb.configure(state="disabled")
            self._update_log("Starting monitor workers...")

            for site, config in PLATFORMS_CONFIG.items():
                if self.platform_vars[site].get():
                    if site == "Khamsat":
                        # Khamsat uses a dedicated ID-based worker
                        t = threading.Thread(
                            target=self._khamsat_worker, args=(config,), daemon=True
                        )
                    else:
                        t = threading.Thread(
                            target=self._platform_worker, args=(site, config), daemon=True
                        )
                    self.workers.append(t)
                    t.start()

        else:
            self.is_monitoring = False
            self.toggle_btn.configure(text="▶  Start Monitoring", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
            self.status_dot.configure(text_color=COLORS["danger"])
            self.status_text.configure(text="Stopped")
            for cb in self.platform_cbs.values():
                cb.configure(state="normal")
            self._update_log("Monitoring stopped")

    def _on_close(self):
        self.is_monitoring = False
        self.tray_mgr.stop()
        # Shutdown persistent Playwright browser
        try:
            from scrapers.browser_manager import browser_mgr
            browser_mgr.shutdown()
        except Exception:
            pass
        self.after(350, self.destroy)

    def _start_from_tray(self):
        if not self.is_monitoring:
            self._toggle_monitoring()

    def _stop_from_tray(self):
        if self.is_monitoring:
            self._toggle_monitoring()
