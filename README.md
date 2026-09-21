# 🖥️ PC Lab Management System

## 📖 Overview
A comprehensive Client-Server PC Lab Management System developed in Python. Designed for educational environments, this application allows instructors to monitor, manage, and assist students in real-time over a Local Area Network (LAN) without relying on external internet connectivity.

This project was built to optimize CPU and network bandwidth usage through Dynamic Resolution streaming and includes network-level hardware controls like Wake-on-LAN (WoL) using Subnet Broadcasting.

## ✨ Key Features
*   **⚡ Wake-on-LAN (WoL):** Remotely power on all student PCs simultaneously using targeted Magic Packets and Subnet Broadcasting, bypassing standard Switch restrictions.
*   **👁️ Real-Time Screen Monitoring:** View all student screens simultaneously. Utilizes **Dynamic Resolution** (scaling from 320x180 thumbnails to 720p/1080p active views) to prevent server CPU bottlenecks.
*   **🖱️ Remote Control:** Full mouse (left/right click) and keyboard interaction (including Unicode/Thai language support) for remote student assistance.
*   **🛡️ Web & App Filtering:** Restrict distractions by blocking specific websites (via IPv4/IPv6 `hosts` file modification & DNS flushing) and terminating unauthorized applications (e.g., Discord, Steam) in real-time.
*   **🔒 Class Management & Screen Lock:** Instantly lock/unlock all student screens, broadcast the teacher's screen to the class, and send global announcement pop-ups.
*   **🔄 OTA Updates & File Transfer:** Over-The-Air (OTA) deployment system to update the Student Agent software remotely without manual reinstallation. Includes two-way file sharing for assignment distribution and submission.
*   **📝 Activity Logging:** Automated student registration and activity tracking stored in an SQLite database, exportable to CSV for Google Sheets integration.

## 🛠️ Tech Stack
*   **Language:** Python 3.x
*   **GUI Framework:** CustomTkinter, Tkinter
*   **Network & Communication:** Flask-SocketIO (WebSockets), UDP/TCP Sockets
*   **System Control:** PyAutoGUI, Psutil, MSS (Fast Screen Capture), ctypes (Windows API)
*   **Database:** SQLite3
*   **Image Processing:** Pillow (PIL), Base64, OpenCV/ImageTk

## ⚙️ System Requirements
*   **OS:** Windows 10 or Windows 11 (Teacher and Student machines)
*   **Network:** Both machines must be on the same Local Area Network (LAN)
*   **Privileges:** Student machines require Administrator privileges (configured via Task Scheduler) for Web Filtering and Screen Locking.

## 🚀 Installation & Setup

### 1. Teacher (Server) Setup
1. Clone the repository to the Teacher's machine.
2. Install the required dependencies:
   ```bash
   pip install customtkinter flask flask-socketio mss pillow psutil pyautogui keyboard