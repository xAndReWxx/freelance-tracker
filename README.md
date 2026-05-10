<div align="center">

# 🚀 Freelance Tracker

**Realtime freelance project monitor with desktop notifications**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)](https://github.com/xAndReWxx/freelance-tracker)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-7c6cf0)](https://github.com/TomSchimansky/CustomTkinter)
[![Release](https://img.shields.io/github/v/release/xAndReWxx/freelance-tracker?color=orange)](https://github.com/xAndReWxx/freelance-tracker/releases)

A lightweight, modern desktop application that silently monitors popular Arabic & international freelance platforms and delivers instant Windows notifications when new projects are posted.

---

**Supported Platforms**

| Platform | Type | Interval |
|:--------:|:----:|:--------:|
| ![Mostaql](https://img.shields.io/badge/-Mostaql-2ecc71?style=flat-square) | Listing | 15s |
| ![Nafezly](https://img.shields.io/badge/-Nafezly-3498db?style=flat-square) | Listing | 20s |
| ![Khamsat](https://img.shields.io/badge/-Khamsat-f39c12?style=flat-square) | Incremental ID | 20s |
| ![Kafiil](https://img.shields.io/badge/-Kafiil-1abc9c?style=flat-square) | Listing | 25s |
| ![FreelanceYard](https://img.shields.io/badge/-FreelanceYard-e74c3c?style=flat-square) | Listing | 30s |

</div>

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🔔 Realtime Monitoring
- Detects new projects within seconds of posting
- Per-platform scan intervals for optimal coverage
- Concurrent multi-platform tracking

### 🎯 Smart Filtering
- Custom keyword filters (AND/OR logic)
- Collapsible filter panel with tag chips
- Filters apply across all platforms

### 📡 Khamsat Incremental Tracker
- HEAD-based redirect probing (no WAF issues)
- Adaptive stop after N consecutive misses
- Persistent high-water mark across restarts
- Silent baseline seeding on first run

</td>
<td width="50%">

### 🖥️ Modern Dark UI
- Premium dark-mode interface (CustomTkinter)
- RTL support for Arabic project titles
- Expandable project cards with budget display
- Live status bar and session statistics

### 🔕 Background Operation
- System tray minimization
- Native Windows toast notifications
- Start with Windows (shortcut-based)
- Crash-safe state persistence

### ⚡ Lightweight Architecture
- No browser automation or Selenium
- Pure HTTP requests + BeautifulSoup
- Threaded workers (no async complexity)
- ~15 MB memory footprint

</td>
</tr>
</table>

---

## 📸 Screenshots

<!-- Replace with actual screenshots after building -->

> **Main Window** — Project feed with realtime cards, platform badges, and budget display.

![Main Window](https://via.placeholder.com/900x500/0a0c18/7c6cf0?text=Main+Window+Screenshot)

> **System Tray** — Runs silently in the background with quick-access menu.

![System Tray](https://via.placeholder.com/400x200/0a0c18/00e5c0?text=Tray+Menu+Screenshot)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│                  app.py (entry)                  │
├─────────────────────────────────────────────────┤
│              ui/main_window.py                   │
│         ┌──────────┼──────────┐                 │
│    Sidebar     Feed Panel    Header              │
│   (platforms)  (cards)     (controls)            │
├─────────────────────────────────────────────────┤
│              Worker Threads                      │
│  ┌─────────┐ ┌─────────┐ ┌───────────────┐     │
│  │ Mostaql │ │ Nafezly │ │ Khamsat       │     │
│  │ Worker  │ │ Worker  │ │ (ID-tracked)  │     │
│  └────┬────┘ └────┬────┘ └──────┬────────┘     │
│       │           │             │                │
│  ┌────▼────┐ ┌────▼────┐ ┌─────▼─────────┐     │
│  │Listing  │ │Listing  │ │HEAD Probe     │     │
│  │Scraper  │ │Scraper  │ │+ Listing Parse│     │
│  └─────────┘ └─────────┘ └───────────────┘     │
├─────────────────────────────────────────────────┤
│                  Managers                        │
│  Settings │ Notifications │ Tray │ Startup      │
└─────────────────────────────────────────────────┘
```

### Detection Strategies

| Platform | Method | Details |
|----------|--------|---------|
| Mostaql, Nafezly, Kafiil, FreelanceYard | **Listing Page Scrape** | Periodic GET → parse HTML → diff against seen projects |
| Khamsat | **Incremental ID Probing** | Concurrent HEAD requests validate IDs via redirect detection → listing page parse for metadata |

### Khamsat Two-Phase Pipeline

1. **Phase 1 — HEAD Probing**: Concurrent HEAD requests to `/community/requests/{id}`. Valid requests redirect (301) to a canonical slug URL. Category validation ensures only `/community/requests/` matches.
2. **Phase 2 — Listing Parse**: A single GET to the listing page fetches metadata for all validated IDs. Individual pages are behind AWS WAF — the listing page is not.
3. **Adaptive Stop**: 5 consecutive invalid IDs → stop current scan cycle.
4. **Startup Baseline**: On launch, the scraper seeks the frontier silently (listing page + forward probing) before entering the monitoring loop. No old projects flood the UI.

---

## 📂 Project Structure

```
freelance-tracker/
├── app.py                    # Entry point
├── config.py                 # Global config, colors, platform definitions
├── models.py                 # Project dataclass
├── settings.json             # Persistent user settings (auto-generated)
│
├── scrapers/
│   ├── base.py               # Abstract base scraper
│   ├── mostaql.py            # Mostaql scraper
│   ├── nafezly.py            # Nafezly scraper
│   ├── freelanceyard.py      # FreelanceYard scraper
│   ├── kafiil.py             # Kafiil scraper
│   └── khamsat.py            # Khamsat incremental ID scraper
│
├── managers/
│   ├── settings_manager.py   # Thread-safe settings persistence
│   ├── notification_manager.py # Windows toast notifications
│   ├── tray_manager.py       # System tray integration
│   ├── startup_manager.py    # Windows startup shortcut
│   └── install_tracker.py    # Anonymous install counter
│
├── ui/
│   └── main_window.py        # Main application window (CustomTkinter)
│
└── assets/
    └── icons/                # Platform & app icons (.ico)
```

---

## 🚀 Quick Start

### Download (Users)

> **No Python required!** Download the latest release and run.

1. Go to [**Releases**](https://github.com/xAndReWxx/freelance-tracker/releases)
2. Download the latest `.zip`
3. Extract and run `Freelance Tracker.exe`

### From Source (Developers)

```bash
# Clone the repository
git clone https://github.com/xAndReWxx/freelance-tracker.git
cd freelance-tracker

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate        # Windows

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

---

## 🔨 Build from Source

Build a standalone Windows executable using PyInstaller:

```bash
# Install build dependencies
pip install pyinstaller

# Build production EXE (windowed, no console)
pyinstaller "Freelance Tracker.spec"
```

The output will be in `dist/Freelance Tracker/`. The spec file is pre-configured with:

- ✅ Windowed mode (no CMD window)
- ✅ Bundled assets and icons
- ✅ All hidden imports (pywin32, winshell, etc.)
- ✅ UPX disabled (prevents AV false positives)
- ✅ Application icon

---

## ⚙️ Configuration

Settings are stored in `settings.json` (created automatically on first run):

```json
{
  "keywords": [],
  "filters_enabled": false,
  "notifications_enabled": true,
  "autostart_enabled": false,
  "last_khamsat_id": 788350,
  "khamsat_recent_seen": [788348, 788349, 788350]
}
```

| Key | Type | Description |
|-----|------|-------------|
| `keywords` | `string[]` | Active keyword filters |
| `filters_enabled` | `bool` | Whether keyword filtering is active |
| `notifications_enabled` | `bool` | Toggle Windows toast notifications |
| `autostart_enabled` | `bool` | Start with Windows |
| `last_khamsat_id` | `int` | High-water mark for Khamsat ID tracking |
| `khamsat_recent_seen` | `int[]` | Recent seen Khamsat IDs (≤200, prevents re-detection) |

---

## 🗺️ Roadmap

- [ ] 🤖 Discord webhook integration
- [ ] 📱 Telegram notification bot
- [ ] 📊 Analytics dashboard (projects/day, response times)
- [ ] 🧠 AI-powered keyword matching
- [ ] 🐧 Linux support (GTK backend)
- [ ] 🌐 Browser extension companion
- [ ] 📋 Project bookmarking & notes
- [ ] 🔄 Export project history (CSV/JSON)

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ for freelancers**

[Report Bug](https://github.com/xAndReWxx/freelance-tracker/issues) · [Request Feature](https://github.com/xAndReWxx/freelance-tracker/issues)

</div>
