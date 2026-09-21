import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
import base64
import io
import threading
import time
import socket
import sqlite3
import os
import csv
import webbrowser
from datetime import datetime
from flask import Flask
from flask_socketio import SocketIO
from mss import mss

app_instance = None
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

clients_ui = {} 
mac_database = {} 

def init_db():
    conn = sqlite3.connect('pclab_monitor.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS pc_info (pc_name TEXT PRIMARY KEY, mac_address TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS activity_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, action_type TEXT, pc_name TEXT, student_name TEXT, student_id TEXT)''')
    conn.commit()
    conn.close()

init_db()

def log_activity(action_type, pc_name, name="", student_id=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect('pclab_monitor.db')
    conn.execute("INSERT INTO activity_logs (timestamp, action_type, pc_name, student_name, student_id) VALUES (?, ?, ?, ?, ?)",
                 (timestamp, action_type, pc_name, name, student_id))
    conn.commit()
    conn.close()

def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception: ip = '127.0.0.1'
    finally: s.close()
    return ip

def start_udp_broadcast():
    server_ip = get_lan_ip()
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
        try: udp_sock.sendto(f"PCLAB_SERVER_IP:{server_ip}".encode('utf-8'), ('255.255.255.255', 5001))
        except: pass
        time.sleep(2)

def send_magic_packet(mac_address):
    try:
        mac_clean = mac_address.replace(':', '').replace('-', '')
        if len(mac_clean) != 12: return False
        data = bytes.fromhex('FF' * 6 + mac_clean * 16)
        
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            # ❌ ลบ sock.bind ออก เพื่อให้ Windows เป็นคนหาช่องทางที่ส่งทะลุ Switch ได้ดีที่สุดเอง
            
            # 🛠️ ส่งคำสั่งปลุกไปยังทุกช่องทางที่เป็นไปได้ของวง Lab
            destinations = [
                '255.255.255.255', 
                '172.28.29.255',   # Broadcast สำหรับ Subnet 255.255.254.0
                '172.28.255.255'   # ยิงกราดเผื่อ Switch บล็อกวงแคบ
            ]
            
            for dest in destinations:
                try: 
                    sock.sendto(data, (dest, 9))
                    sock.sendto(data, (dest, 7))
                except: pass
                
        return True
    except: return False

@socketio.on('register_mac')
def handle_mac_registration(data):
    pc_name, mac_address = data['pc_name'], data['mac_address']
    conn = sqlite3.connect('pclab_monitor.db')
    conn.execute("REPLACE INTO pc_info (pc_name, mac_address) VALUES (?, ?)", (pc_name, mac_address))
    conn.commit()
    conn.close()
    mac_database[pc_name] = mac_address
    log_activity("Connected", pc_name)

@socketio.on('screen_update')
def handle_screen_update(data):
    if app_instance:
        app_instance.after(0, app_instance.update_pc_screen, data['pc_name'], data['image_data'], data.get('cpu', 0), data.get('ram', 0), data.get('net_status', 'OK'))
        if app_instance.exhibit_pc == data['pc_name']:
            socketio.emit('broadcast_frame', {'image_data': data['image_data']})

@socketio.on('register_data')
def handle_registration(data):
    pc_name, name, student_id = data['pc_name'], data['name'], data['student_id']
    log_activity("Registered", pc_name, name, student_id)
    if app_instance:
        app_instance.after(0, app_instance.update_pc_registration, pc_name, name, student_id)

@socketio.on('submit_work')
def handle_submit_work(data):
    try:
        pc_name = data['pc_name']
        filename = data['filename']
        file_data = data['file_data']
        save_folder = r"C:\PCLab_Teacher_Works"
        os.makedirs(save_folder, exist_ok=True)
        save_path = os.path.join(save_folder, f"[{pc_name}]_{filename}")
        with open(save_path, 'wb') as f: f.write(base64.b64decode(file_data))
        log_activity(f"Submitted Work: {filename}", pc_name)
        if app_instance: app_instance.after(0, lambda: app_instance.notify_new_work(pc_name, filename, save_folder))
    except Exception as e: print(e)

def run_server():
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)

ctk.set_appearance_mode("Dark") 
ctk.set_default_color_theme("blue") 
FONT_MAIN = ("Segoe UI", 12)
FONT_BOLD = ("Segoe UI", 12, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")

class PCLabMonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        global app_instance
        app_instance = self  
        
        self.title("PC Lab Monitor - Teacher Management System (LAB 7203)")
        self.geometry("1450x850")
        self.minsize(1200, 700)
        self.is_broadcasting = False 
        self.zoomed_pc = None 
        self.exhibit_pc = None 
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.create_sidebar()
        self.create_main_content()
        self.create_status_bar()
        
        threading.Thread(target=run_server, daemon=True).start()
        threading.Thread(target=start_udp_broadcast, daemon=True).start()

    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.sidebar.grid_rowconfigure(8, weight=1) 
        
        self.logo_label = ctk.CTkLabel(self.sidebar, text="🖥️ LAB 7203", font=("Segoe UI", 20, "bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(25, 20))
        
        self.control_lbl = ctk.CTkLabel(self.sidebar, text="SYSTEM CONTROLS", font=FONT_BOLD, text_color="gray")
        self.control_lbl.grid(row=1, column=0, padx=20, pady=(5, 5), sticky="w")
        
        power_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        power_frame.grid(row=2, column=0, padx=15, pady=5, sticky="ew")
        ctk.CTkButton(power_frame, text="⚡ Power On", command=lambda: self.btn_action("wake"), fg_color="#27AE60", hover_color="#1E8449", width=110, font=FONT_BOLD).pack(side="left", padx=3)
        ctk.CTkButton(power_frame, text="🔴 Shut All", command=lambda: self.btn_action("shutdown"), fg_color="#C0392B", hover_color="#922B21", width=110, font=FONT_BOLD).pack(side="right", padx=3)
        
        action_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        action_frame.grid(row=3, column=0, padx=15, pady=5, sticky="ew")
        ctk.CTkButton(action_frame, text="🔒 Lock All", command=lambda: self.btn_action("lock"), fg_color="#E74C3C", hover_color="#C0392B", width=72, font=FONT_BOLD).pack(side="left", padx=2)
        ctk.CTkButton(action_frame, text="🔓 Unlock", command=lambda: self.btn_action("unlock"), fg_color="#2ECC71", hover_color="#27AE60", width=72, font=FONT_BOLD).pack(side="left", padx=2)
        self.share_btn = ctk.CTkButton(action_frame, text="🖥️ Share", command=lambda: self.btn_action("show"), fg_color="#3498DB", hover_color="#2980B9", width=95, font=FONT_BOLD)
        self.share_btn.pack(side="left", padx=2)

        # 🛠️ ย้ายปุ่มจัดการชั้นเรียนทั้งหมดมาไว้ด้านซ้าย เรียงแนวตั้ง
        self.class_lbl = ctk.CTkLabel(self.sidebar, text="CLASS MANAGEMENT", font=FONT_BOLD, text_color="gray")
        self.class_lbl.grid(row=4, column=0, padx=20, pady=(15, 5), sticky="w")
        
        class_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        class_frame.grid(row=5, column=0, padx=15, pady=0, sticky="ew")
        ctk.CTkButton(class_frame, text="📝 เปิดลงทะเบียน", command=lambda: self.btn_action("register"), fg_color="#E67E22", hover_color="#D56F14", font=FONT_BOLD).pack(fill="x", pady=3, padx=5)
        ctk.CTkButton(class_frame, text="💬 ประกาศแจ้งเตือน", command=lambda: self.btn_action("notify"), fg_color="#8E44AD", hover_color="#71368A", font=FONT_BOLD).pack(fill="x", pady=3, padx=5)
        ctk.CTkButton(class_frame, text="📤 ส่งไฟล์งาน", command=lambda: self.btn_action("send_all"), fg_color="#9B59B6", hover_color="#8E44AD", font=FONT_BOLD).pack(fill="x", pady=3, padx=5)
        ctk.CTkButton(class_frame, text="📄 ดึงรายงาน Logs", command=self.export_logs, fg_color="#F39C12", hover_color="#D68910", font=FONT_BOLD).pack(fill="x", pady=3, padx=5)
        ctk.CTkButton(class_frame, text="🛑 ยกเลิกฉายจอเพื่อน", command=self.stop_exhibit, fg_color="#C0392B", hover_color="#922B21", font=FONT_BOLD).pack(fill="x", pady=3, padx=5)

        self.web_lbl = ctk.CTkLabel(self.sidebar, text="FILTERING (WEB & APP)", font=FONT_BOLD, text_color="gray")
        self.web_lbl.grid(row=6, column=0, padx=20, pady=(15, 5), sticky="w")
        
        self.web_frame = ctk.CTkFrame(self.sidebar, corner_radius=10)
        self.web_frame.grid(row=7, column=0, padx=15, pady=5, sticky="nwe")
        ctk.CTkButton(self.web_frame, text="⚙️ เลือกแอป/เว็บที่จะบล็อก", command=self.open_filter_popup, fg_color="#E67E22", hover_color="#D35400", font=FONT_BOLD, height=35).pack(pady=(15, 5), padx=10, fill="x")
        ctk.CTkButton(self.web_frame, text="✅ ปลดบล็อกทั้งหมด", command=self.disable_blocks, fg_color="#34495E", hover_color="#2C3E50", font=FONT_BOLD, height=35).pack(pady=(5, 15), padx=10, fill="x")

        self.theme_btn = ctk.CTkButton(self.sidebar, text="☀️ Light Mode", command=self.toggle_theme, fg_color="gray25", hover_color="gray35", font=FONT_BOLD)
        self.theme_btn.grid(row=8, column=0, padx=20, pady=20, sticky="s")

    def open_filter_popup(self):
        popup = ctk.CTkToplevel(self)
        popup.title("⚙️ ตั้งค่าการจำกัดสิทธิ์ (Filter Rules)")
        popup.geometry("450x550")
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        ctk.CTkLabel(popup, text="เลือกเว็บไซต์และโปรแกรมที่ต้องการบล็อก", font=FONT_TITLE).pack(pady=(20, 10))
        
        sites_to_block = {
            # 🛠️ เพิ่มโดเมนย่อยของ YouTube ทั้งหมด
            "YouTube (ดูวิดีโอ)": ["youtube.com", "youtu.be", "m.youtube.com", "googlevideo.com", "ytimg.com"],
            "Facebook (โซเชียล)": ["facebook.com", "messenger.com"],
            "Instagram (โซเชียล)": ["instagram.com"],
            "X / Twitter (โซเชียล)": ["x.com", "twitter.com"],
            "TikTok (โซเชียล)": ["tiktok.com"],
            "Netflix (ดูหนัง)": ["netflix.com"]
        }
        apps_to_block = {
            "Discord (แชทเล่นเกม)": ["discord.exe"],
            "Steam / Epic Games (เกม)": ["steam.exe", "epicgameslauncher.exe"],
            "Line (โปรแกรมแชท)": ["line.exe"]
        }
        
        self.site_checkboxes = {}
        self.app_checkboxes = {}
        
        site_frame = ctk.CTkFrame(popup)
        site_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(site_frame, text="🌐 รายชื่อเว็บไซต์", font=FONT_BOLD).pack(anchor="w", padx=10, pady=5)
        for name, domains in sites_to_block.items():
            var = ctk.BooleanVar(value=False)
            chk = ctk.CTkCheckBox(site_frame, text=name, variable=var, font=FONT_MAIN)
            chk.pack(anchor="w", padx=20, pady=2)
            self.site_checkboxes[name] = (var, domains)
            
        app_frame = ctk.CTkFrame(popup)
        app_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(app_frame, text="🖥️ รายชื่อโปรแกรม", font=FONT_BOLD).pack(anchor="w", padx=10, pady=5)
        for name, processes in apps_to_block.items():
            var = ctk.BooleanVar(value=False)
            chk = ctk.CTkCheckBox(app_frame, text=name, variable=var, font=FONT_MAIN)
            chk.pack(anchor="w", padx=20, pady=2)
            self.app_checkboxes[name] = (var, processes)
            
        def apply_selected():
            sites = [s for name, (var, doms) in self.site_checkboxes.items() if var.get() for s in doms]
            apps = [a for name, (var, procs) in self.app_checkboxes.items() if var.get() for a in procs]
            if sites: socketio.emit('execute_command', {'action': 'block_web', 'sites': sites})
            if apps: socketio.emit('execute_command', {'action': 'block_app', 'apps': apps})
            self.status_lbl.configure(text=f"🚫 สั่งบล็อกแล้ว: เว็บ {len(set(sites))} | โปรแกรม {len(set(apps))}")
            popup.destroy()
            messagebox.showinfo("สำเร็จ", "ส่งคำสั่งบล็อกไปยังเครื่องนักศึกษาเรียบร้อยแล้ว!")

        ctk.CTkButton(popup, text="🚀 ยืนยันการบล็อก", command=apply_selected, fg_color="#E67E22", hover_color="#D35400", font=FONT_BOLD, height=40).pack(pady=15)

    def disable_blocks(self):
        socketio.emit('execute_command', {'action': 'unblock_web'})
        socketio.emit('execute_command', {'action': 'unblock_app'})
        self.status_lbl.configure(text="✅ ปลดล็อกการบล็อกทั้งหมด")

    def show_send_message_dialog(self, target):
        dialog = tk.Toplevel(self)
        dialog.title("ส่งข้อความ")
        dialog.geometry("400x380")
        dialog.configure(bg="#FADCD9")
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        dialog.update_idletasks()
        dialog.geometry(f"+{int(dialog.winfo_screenwidth()/2 - 200)}+{int(dialog.winfo_screenheight()/2 - 190)}")

        card = tk.Frame(dialog, bg="white", bd=0)
        card.place(relx=0.5, rely=0.5, anchor="center", width=340, height=320)
        tk.Label(card, text="💬", font=("Segoe UI", 36), bg="white").pack(pady=(20, 0))
        tk.Label(card, text="ข้อความ", font=("Segoe UI", 16, "bold"), bg="white", fg="#333333").pack(pady=(0, 15))

        msg_entry = tk.Text(card, font=("Segoe UI", 12), relief="solid", bd=1, width=28, height=4)
        msg_entry.pack(padx=20, pady=(0, 20))

        def submit():
            msg = msg_entry.get("1.0", tk.END).strip()
            if msg:
                socketio.emit('execute_command', {'action': 'notify', 'message': msg, 'target': target})
                self.status_lbl.configure(text=f"💬 ส่งข้อความถึง {target} สำเร็จ")
                dialog.destroy()
            else: messagebox.showwarning("แจ้งเตือน", "กรุณาพิมพ์ข้อความ", parent=dialog)

        tk.Button(card, text="ส่งข้อความ", font=("Segoe UI", 12, "bold"), bg="#285C8D", fg="white", activebackground="#1F476D", activeforeground="white", relief="flat", command=submit).pack(fill="x", padx=30, ipady=6)

    def create_main_content(self):
        self.right_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        # นำ sub_toolbar ออกเพราะย้ายไปซ้ายมือหมดแล้ว ทำให้มีพื้นที่ดูจอเด็กเต็มที่!
        self.main_frame = ctk.CTkScrollableFrame(self.right_frame, corner_radius=15, fg_color=("gray95", "gray10"))
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=0)

    def create_status_bar(self):
        self.status_lbl = ctk.CTkLabel(self, text=f"🟢 Server IP: {get_lan_ip()} | Port: 5000 | PCs: 0", font=FONT_MAIN, anchor="w", bg_color=("gray85", "gray15"))
        self.status_lbl.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=0)

    def export_logs(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")], title="บันทึกรายงานกิจกรรม")
        if filepath:
            try:
                conn = sqlite3.connect('pclab_monitor.db')
                c = conn.cursor()
                c.execute("SELECT timestamp, action_type, pc_name, student_name, student_id FROM activity_logs")
                rows = c.fetchall()
                conn.close()
                with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                    csv.writer(f).writerow(['เวลา', 'กิจกรรม', 'ชื่อเครื่อง', 'ชื่อนักศึกษา', 'รหัสนักศึกษา'])
                    csv.writer(f).writerows(rows)
                if messagebox.askyesno("สำเร็จ", "ดึงข้อมูลสำเร็จ!\nเปิด Google Sheets เพื่อนำไปวางหรือไม่?"):
                    webbrowser.open("https://sheets.new") 
            except Exception as e: messagebox.showerror("ข้อผิดพลาด", f"ไม่สามารถดึงข้อมูลได้: {e}")

    def notify_new_work(self, pc_name, filename, folder_path):
        try: os.startfile(folder_path) 
        except: pass
        messagebox.showinfo("ได้รับงานใหม่", f"นักศึกษา {pc_name} ส่งไฟล์: {filename}")

    def stop_exhibit(self):
        self.exhibit_pc = None
        socketio.emit('execute_command', {'action': 'stop_broadcast'})
        self.status_lbl.configure(text="🛑 หยุดการแชร์จอ Exhibit แล้ว")

    # 🛠️ คำนวณแกน X, Y แม่นยำขึ้นเมื่อขยายเต็มจอ
    def handle_remote_click(self, event):
        if not hasattr(self, 'zoom_win') or not self.zoom_win.winfo_exists(): return
        # ดึงขนาดความกว้าง/ยาวของหน้าต่างปัจจุบัน เพื่อให้เมาส์ตรงจุดแม้จะขยายจอ
        w = self.zoom_win.winfo_width()
        h = self.zoom_win.winfo_height()
        if w < 100: w = 800
        if h < 100: h = 450
        rx = event.x / w
        ry = event.y / h
        socketio.emit('remote_input', {'target': self.zoomed_pc, 'type': 'click', 'x': rx, 'y': ry})
        
    def handle_remote_key(self, event):
        socketio.emit('remote_input', {'target': self.zoomed_pc, 'type': 'key', 'key': event.keysym})

    def toggle_fullscreen(self, event=None):
        self.zoom_win.attributes("-fullscreen", not self.zoom_win.attributes("-fullscreen"))

    # 🛠️ 1. เพิ่มรับค่า button_type สำหรับคลิกขวา
    def handle_remote_click(self, event, button_type="left"):
        if not hasattr(self, 'zoom_win') or not self.zoom_win.winfo_exists(): return
        w = self.zoom_label.winfo_width()
        h = self.zoom_label.winfo_height()
        if w < 100: w = 800
        if h < 100: h = 450
        rx = event.x / w
        ry = event.y / h
        socketio.emit('remote_input', {'target': self.zoomed_pc, 'type': 'click', 'button': button_type, 'x': rx, 'y': ry})
        
    # 🛠️ 2. แยกระหว่างการกดปุ่มพิเศษ (Enter, ลบ) กับการพิมพ์ตัวอักษร (ภาษาไทย/อังกฤษ)
    def handle_remote_key(self, event):
        special_keys = ['Return', 'BackSpace', 'Escape', 'Tab', 'space', 'Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Caps_Lock']
        if event.keysym in special_keys or not event.char:
            socketio.emit('remote_input', {'target': self.zoomed_pc, 'type': 'key', 'key': event.keysym})
        else:
            socketio.emit('remote_input', {'target': self.zoomed_pc, 'type': 'char', 'char': event.char})

    def open_zoom_window(self, pc_name):
        if hasattr(self, 'zoom_win') and self.zoom_win.winfo_exists(): self.zoom_win.destroy()
        self.zoomed_pc = pc_name
        self.zoom_win = ctk.CTkToplevel(self)
        self.zoom_win.title(f"ส่องและควบคุมหน้าจอ: {pc_name} [Remote Control]")
        self.zoom_win.geometry("800x450") 
        self.zoom_win.resizable(True, True) 
        
        self.zoom_win.lift()
        self.zoom_win.focus_force()
        self.zoom_win.attributes("-topmost", True)
        self.zoom_win.after(500, lambda: self.zoom_win.attributes("-topmost", False) if self.zoom_win.winfo_exists() else None)

        self.zoom_label = tk.Label(self.zoom_win, text="กำลังเปิดกล้องรับภาพ...", font=("Segoe UI", 16, "bold"), bg="black", fg="white")
        self.zoom_label.pack(expand=True, fill="both")
        
        # 🛠️ 3. เพิ่มการดักจับเมาส์คลิกขวา (<Button-3>)
        self.zoom_label.bind("<Button-1>", lambda e: self.handle_remote_click(e, "left"))
        self.zoom_label.bind("<Button-3>", lambda e: self.handle_remote_click(e, "right"))
        self.zoom_win.bind("<Key>", self.handle_remote_key)
        self.zoom_win.focus_set() 
        
        socketio.emit('execute_command', {'action': 'set_high_fps', 'target': pc_name})
        def on_close():
            socketio.emit('execute_command', {'action': 'set_low_fps', 'target': self.zoomed_pc})
            self.zoomed_pc = None
            self.zoom_win.destroy()
        self.zoom_win.protocol("WM_DELETE_WINDOW", on_close)

    def handle_individual_command(self, pc_name, command_type):
        if command_type == "⚡ สั่งการเครื่องนี้...": return
        if command_type == "🔒 ล็อกเครื่องนี้": socketio.emit('execute_command', {'action': 'lock', 'target': pc_name})
        elif command_type == "🔓 ปลดล็อกเครื่องนี้": socketio.emit('execute_command', {'action': 'unlock', 'target': pc_name})
        elif command_type == "👁️ แชร์จอนี้ (Exhibit)":
            self.exhibit_pc = pc_name
            socketio.emit('execute_command', {'action': 'start_broadcast'})
        elif command_type == "💬 ส่งข้อความ": self.show_send_message_dialog(pc_name)
        elif command_type == "🔴 ปิดเครื่องนี้":
            if messagebox.askyesno("ยืนยัน", f"ต้องการปิดเครื่อง {pc_name}?"): socketio.emit('execute_command', {'action': 'shutdown', 'target': pc_name})

    def update_pc_screen(self, pc_name, img_base64, cpu, ram, net_status):
        img_data = base64.b64decode(img_base64)
        img = Image.open(io.BytesIO(img_data))
        
        # 🛠️ แก้ไข: แยกก๊อปปี้ภาพ (Copy) สำหรับจอเล็ก ป้องกันภาพตีกันกับจอซูม
        thumb_img = img.copy()
        ctk_image = ctk.CTkImage(light_image=thumb_img, dark_image=thumb_img, size=(220, 120))
        
        if pc_name not in clients_ui:
            current_count = len(clients_ui)
            pc_frame = ctk.CTkFrame(self.main_frame, width=260, height=330, corner_radius=15, border_width=2, border_color=("gray75", "gray30"))
            pc_frame.grid(row=current_count // 4, column=current_count % 4, padx=15, pady=15)
            title = ctk.CTkLabel(pc_frame, text=pc_name, font=FONT_TITLE, cursor="hand2")
            title.pack(pady=(5, 0))
            screen_label = ctk.CTkLabel(pc_frame, image=ctk_image, text="", corner_radius=8, cursor="hand2")
            screen_label.pack(pady=5, padx=15)
            hw_label = ctk.CTkLabel(pc_frame, text=f"⚙️ CPU: {cpu}% | 💾 RAM: {ram}%\n🌐 Net: {net_status}", font=("Segoe UI", 11), text_color="gray50")
            hw_label.pack(pady=(0, 2))
            status_label = ctk.CTkLabel(pc_frame, text="👤 (เชื่อมต่อแล้ว)", text_color=("#27AE60", "#2ECC71"), font=FONT_BOLD)
            status_label.pack(pady=(0, 5))
            
            menu_options = ["⚡ สั่งการเครื่องนี้...", "🔒 ล็อกเครื่องนี้", "🔓 ปลดล็อกเครื่องนี้", "👁️ แชร์จอนี้ (Exhibit)", "💬 ส่งข้อความ", "🔴 ปิดเครื่องนี้"]
            cmd_menu = ctk.CTkOptionMenu(pc_frame, values=menu_options, width=180, height=28, font=("Segoe UI", 11), command=lambda val, p=pc_name: self.handle_individual_command(p, val))
            cmd_menu.pack(pady=(5, 10))
            screen_label.bind("<Button-1>", lambda e, pc=pc_name: self.open_zoom_window(pc))
            title.bind("<Button-1>", lambda e, pc=pc_name: self.open_zoom_window(pc))
            
            clients_ui[pc_name] = {'frame': pc_frame, 'image_label': screen_label, 'status_label': status_label, 'hw_label': hw_label, 'img_ref': ctk_image}
            self.status_lbl.configure(text=f"🟢 Server IP: {get_lan_ip()} | Port: 5000 | PCs: {len(clients_ui)}")
        else:
            clients_ui[pc_name]['img_ref'] = ctk_image 
            clients_ui[pc_name]['image_label'].configure(image=ctk_image, text="")
            clients_ui[pc_name]['hw_label'].configure(text=f"⚙️ CPU: {cpu}% | 💾 RAM: {ram}%\n🌐 Net: {net_status}")

        # 🛠️ ใช้ ImageTk.PhotoImage ธรรมดาบังคับยืดรูปให้พอดีกรอบ 100%
        if self.zoomed_pc == pc_name and hasattr(self, 'zoom_label') and self.zoom_label.winfo_exists():
            win_w = self.zoom_label.winfo_width()
            win_h = self.zoom_label.winfo_height()
            
            if win_w < 100: win_w = 800
            if win_h < 100: win_h = 450
            
            zoom_img = img.copy().resize((win_w, win_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(zoom_img)
            self.zoom_label.configure(image=photo, text="")
            self.zoom_label.image_ref = photo

    def update_pc_registration(self, pc_name, name, student_id):
        if pc_name in clients_ui: clients_ui[pc_name]['status_label'].configure(text=f"👤 {name} ({student_id})", text_color=("#2980B9", "#3498DB"))

    def toggle_theme(self):
        if ctk.get_appearance_mode() == "Light": ctk.set_appearance_mode("Dark"); self.theme_btn.configure(text="☀️ Light Mode")
        else: ctk.set_appearance_mode("Light"); self.theme_btn.configure(text="🌙 Dark Mode")

    def broadcast_teacher_screen(self):
        socketio.emit('execute_command', {'action': 'start_broadcast'})
        with mss() as sct:
            monitor = sct.monitors[1]
            while self.is_broadcasting:
                try:
                    sct_img = sct.grab(monitor)
                    # 🛠️ ปรับเป็น 720p เช่นเดียวกัน
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX").resize((1280, 720))
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=60)
                    socketio.emit('broadcast_frame', {'image_data': base64.b64encode(buffer.getvalue()).decode('utf-8')})
                    time.sleep(0.1) 
                except: pass

    def btn_action(self, action):
        if action in ["lock", "unlock", "register"]: socketio.emit('execute_command', {'action': action, 'target': 'all'})
        elif action == "shutdown":
            if messagebox.askyesno("ยืนยัน", "ต้องการปิดเครื่องนักเรียนทั้งหมด?"): socketio.emit('execute_command', {'action': 'shutdown', 'target': 'all'})
        elif action == "wake":
            conn = sqlite3.connect('pclab_monitor.db')
            rows = conn.execute("SELECT pc_name, mac_address FROM pc_info").fetchall()
            conn.close()
            if not rows: return
            
            # 🛠️ สร้าง Thread ค่อยๆ ยิงทีละเครื่อง ป้องกัน Switch บล็อกและ UI ค้าง
            def wake_all_pcs():
                success_count = 0
                for row in rows:
                    if send_magic_packet(row[1]):
                        success_count += 1
                    time.sleep(0.15)  # ⏳ หน่วงเวลา 0.15 วินาทีต่อเครื่อง
                
                # อัปเดตข้อความเมื่อส่งครบทุกเครื่อง
                self.after(0, lambda: self.status_lbl.configure(
                    text=f"⚡ สั่งเปิดเครื่องสำเร็จ {success_count}/{len(rows)} เครื่อง"
                ))

            self.status_lbl.configure(text=f"⚡ กำลังทยอยส่งคำสั่งปลุกเครื่อง ({len(rows)} เครื่อง)...")
            threading.Thread(target=wake_all_pcs, daemon=True).start()
        elif action == "notify": self.show_send_message_dialog('all')
        elif action == "send_all":
            filepath = filedialog.askopenfilename()
            if filepath: 
                with open(filepath, "rb") as f: file_data = base64.b64encode(f.read()).decode('utf-8')
                socketio.emit('execute_command', {'action': 'receive_file', 'filename': filepath.split("/")[-1], 'file_data': file_data, 'target': 'all'})
        elif action == "show":
            if not self.is_broadcasting:
                self.is_broadcasting = True
                self.share_btn.configure(fg_color="#E74C3C", hover_color="#C0392B", text="🛑 Stop Sharing")
                threading.Thread(target=self.broadcast_teacher_screen, daemon=True).start()
            else:
                self.is_broadcasting = False
                self.share_btn.configure(fg_color="#3498DB", hover_color="#2980B9", text="🖥️ Share")
                socketio.emit('execute_command', {'action': 'stop_broadcast'})

if __name__ == "__main__":
    window = PCLabMonitorApp() 
    window.mainloop()