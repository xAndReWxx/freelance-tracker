# Freelance Tracker 🚀

A modern, fast, and lightweight desktop application built with Python and CustomTkinter to silently monitor popular freelance platforms (Mostaql, Nafezly, FreelanceYard, Kafiil, Khamsat) and deliver real-time Windows toast notifications for new projects.

## 🌟 Features
- **Real-Time Monitoring:** Fetches projects within seconds of posting.
- **Smart Filters:** Set custom keywords to only get notified for projects that match your skills.
- **Background Execution:** Minimizes to the system tray and runs silently.
- **Windows Integration:** Auto-start with Windows and native Toast Notifications.
- **Modern UI:** Built with CustomTkinter for a sleek, dark-mode native experience.

## 🛠️ Installation & Usage (For Developers)

1. Clone the repository:
   ```bash
   git clone https://github.com/xAndReWxx/freelance-tracker.git
   cd freelance-tracker
   ```
2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install customtkinter pystray win11toast beautifulsoup4 requests winshell pypiwin32 pillow pyinstaller
   ```
4. Run the application:
   ```bash
   python app.py
   ```

## 📦 Download (For Users)
You don't need Python installed to run this! 
Just head over to the [Releases](https://github.com/xAndReWxx/freelance-tracker/releases) page and download the latest `.zip` file. Extract it and run `Freelance Tracker.exe`.

## 🤝 Contributing
Feel free to fork the repository, add new scrapers for other platforms in the `scrapers/` folder, and submit a pull request!
