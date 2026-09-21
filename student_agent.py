import time
import base64
import socketio
import io
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from mss import mss
from PIL import Image, ImageTk
import sys
import os
import psutil
import uuid
import ctypes
import socket
import keyboard 
import pyautogui 

try:
    whnd = ctypes.windll.kernel32.GetConsoleWindow()
    if whnd != 0: ctypes.windll.user32.ShowWindow(whnd, 0)
except: pass

def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    sys.exit()

sio = socketio.Client()
PC_NAME = socket.gethostname()  
TEACHER_IP = ""
SEND_INTERVAL = 0.3 
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
IS_LOCKED = False  
BLOCKED_APPS = [] 

def discover_server():
    global TEACHER_IP
    setup_root = tk.Tk()
    setup_root.title("PC-LAB Monitor")
    setup_root.geometry("350x180")
    setup_root.eval('tk::PlaceWindow . center')
    setup_root.resizable(False, False)
    setup_root.attributes("-topmost", True)
    tk.Label(setup_root, text="PC Lab Monitor - Student Connection", font=("Segoe UI", 12, "bold")).pack(pady=15)
    tk.Label(setup_root, text="กำลังค้นหาคอมพิวเตอร์อาจารย์ในวง LAN...", font=("Segoe UI", 10), fg="#34495E").pack(pady=5)
    
    def listen_udp_broadcast():
        global TEACHER_IP
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_sock.bind(('', 5001))
        while True:
            try:
                data, addr = udp_sock.recvfrom(1024)
                message = data.decode('utf-8')
                if message.startswith("PCLAB_SERVER_IP:"):
                    server_ip = message.split(":")[1]
                    TEACHER_IP = f"http://{server_ip}:5000"
                    udp_sock.close()
                    setup_root.after(0, setup_root.destroy)
                    break
            except: time.sleep(1)
                
    threading.Thread(target=listen_udp_broadcast, daemon=True).start()
    setup_root.mainloop()

discover_server()
if not TEACHER_IP: sys.exit()

@sio.event
def connect():
    sio.emit('register_mac', {'pc_name': PC_NAME, 'mac_address': get_mac_address()})

def get_mac_address():
    try:
        # 🛠️ บังคับค้นหา MAC Address จาก "สายแลน" (Ethernet) โดยเฉพาะ
        for interface, addrs in psutil.net_if_addrs().items():
            if "ethernet" in interface.lower() or "อีเทอร์เน็ต" in interface:
                for addr in addrs:
                    if addr.family == psutil.AF_LINK:
                        return addr.address.replace(':', '-').upper()
    except: pass
    
    # 🛠️ สำรองกรณีหาไม่เจอ (แก้บั๊กเลขศูนย์หาย)
    mac_num = hex(uuid.getnode())[2:].zfill(12).upper()
    return '-'.join(mac_num[i: i + 2] for i in range(0, 12, 2))
def background_monitor_task():
    while True:
        if BLOCKED_APPS:
            for proc in psutil.process_iter(['name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() in BLOCKED_APPS:
                        proc.kill()
                except: pass
        time.sleep(2)
        
threading.Thread(target=background_monitor_task, daemon=True).start()

def apply_hosts_blocking(sites_list):
    try:
        with open(HOSTS_PATH, 'r', encoding='utf-8') as f: lines = f.readlines()
        new_lines = []
        inside_block = False
        for line in lines:
            if "# PCLAB_START" in line: inside_block = True; continue
            if "# PCLAB_END" in line: inside_block = False; continue
            if not inside_block: new_lines.append(line)
            
        new_lines.append("\n# PCLAB_START\n")
        for site in sites_list:
            domain = site.strip().lower()
            if domain:
                new_lines.append(f"127.0.0.1 {domain}\n")
                new_lines.append(f"::1 {domain}\n") # 🛠️ บล็อกผ่าน IPv6 ด้วย
                if not domain.startswith("www."): 
                    new_lines.append(f"127.0.0.1 www.{domain}\n")
                    new_lines.append(f"::1 www.{domain}\n")
        new_lines.append("# PCLAB_END\n")
        
        with open(HOSTS_PATH, 'w', encoding='utf-8') as f: f.writelines(new_lines)
        
        # 🛠️ ล้างแคชเครือข่ายของ Windows ทันที
        os.system("ipconfig /flushdns")
        
        # 🛠️ บังคับปิดเบราว์เซอร์เพื่อล้างแคชภายใน (ถ้าไม่ทำ เบราว์เซอร์จะยังเข้าเว็บได้จากความจำเดิม)
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] in ['chrome.exe', 'msedge.exe', 'firefox.exe']:
                    proc.kill()
            except: pass
    except: pass

def clear_hosts_blocking():
    try:
        with open(HOSTS_PATH, 'r', encoding='utf-8') as f: lines = f.readlines()
        new_lines = []
        inside_block = False
        for line in lines:
            if "# PCLAB_START" in line: inside_block = True; continue
            if "# PCLAB_END" in line: inside_block = False; continue
            if not inside_block: new_lines.append(line)
        with open(HOSTS_PATH, 'w', encoding='utf-8') as f: f.writelines(new_lines)
        
        # 🛠️ ล้างแคชเมื่อปลดบล็อก
        os.system("ipconfig /flushdns")
    except: pass

def freeze_hardware():
    try: ctypes.windll.user32.BlockInput(True)
    except: pass
    try:
        for key in ['windows', 'alt', 'tab', 'ctrl', 'esc', 'left windows', 'right windows']:
            keyboard.block_key(key)
    except: pass

def unfreeze_hardware():
    try: ctypes.windll.user32.BlockInput(False)
    except: pass
    try: keyboard.unhook_all()
    except: pass

def keep_focus_loop():
    if IS_LOCKED:
        try:
            root.attributes('-topmost', True)
            root.focus_force()
            root.grab_set()
        except: pass
        root.after(500, keep_focus_loop) 

def show_fullscreen_ui(text="", bg_color="black", text_color="white", show_image=False):
    global IS_LOCKED
    if not IS_LOCKED:
        IS_LOCKED = True
        freeze_hardware() 
        keep_focus_loop()

    try:
        student_dashboard_frame.pack_forget()
        root.withdraw() 
        
        root.overrideredirect(True)
        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        root.geometry(f"{screen_w}x{screen_h}+0+0")
        root.configure(bg=bg_color, cursor="none") 
        
        if show_image:
            msg_label.place_forget()
            broadcast_label.configure(bg="black")
            broadcast_label.place(x=0, y=0, relwidth=1, relheight=1)
        else:
            broadcast_label.place_forget()
            msg_label.config(text=text, fg=text_color, bg="black")
            msg_label.place(relx=0.5, rely=0.5, anchor="center")
            
        root.deiconify()
        root.attributes('-fullscreen', True)
        root.attributes('-topmost', True) 
        root.update() 
    except: pass

def hide_fullscreen_ui():
    global IS_LOCKED
    IS_LOCKED = False
    try:
        root.grab_release() 
        root.configure(cursor="") 
        unfreeze_hardware()
        
        root.withdraw()
        root.attributes('-fullscreen', False)
        root.attributes('-topmost', False) 
        root.overrideredirect(False)
        root.geometry("400x250")
        root.eval('tk::PlaceWindow . center')
        root.configure(bg="#F8F9F9")
        root.deiconify()
        
        msg_label.place_forget()
        broadcast_label.place_forget()
        student_dashboard_frame.pack(expand=True, fill="both")
    except: pass

def send_work_to_teacher():
    filepath = filedialog.askopenfilename(title="เลือกไฟล์งานที่ต้องการส่งให้อาจารย์")
    if filepath:
        filename = filepath.split("/")[-1]
        try:
            with open(filepath, "rb") as f: file_data = base64.b64encode(f.read()).decode('utf-8')
            sio.emit('submit_work', {'pc_name': PC_NAME, 'filename': filename, 'file_data': file_data})
            messagebox.showinfo("สำเร็จ", "ส่งไฟล์งานให้อาจารย์เรียบร้อยแล้ว!")
        except Exception as e: messagebox.showerror("ข้อผิดพลาด", f"ไม่สามารถส่งไฟล์ได้: {e}")

def show_register_dialog():
    dialog = tk.Toplevel(root)
    dialog.title("ลงทะเบียนเรียน")
    dialog.geometry("400x550")
    dialog.configure(bg="#FADCD9")
    dialog.attributes("-topmost", True)
    dialog.resizable(False, False)

    dialog.update_idletasks()
    w = dialog.winfo_screenwidth()
    h = dialog.winfo_screenheight()
    x = int(w/2 - 400/2)
    y = int(h/2 - 550/2)
    dialog.geometry(f"400x550+{x}+{y}")

    card = tk.Frame(dialog, bg="white", bd=0)
    card.place(relx=0.5, rely=0.5, anchor="center", width=340, height=480)

    tk.Label(card, text="🎓", font=("Segoe UI", 40), bg="white").pack(pady=(30, 5))
    tk.Label(card, text="ลงชื่อ", font=("Segoe UI", 18, "bold"), bg="white", fg="#333333").pack(pady=(0, 30))

    def add_placeholder(entry, text):
        entry.insert(0, text)
        entry.config(fg='#7F8C8D')
        def on_focus_in(event):
            if entry.get() == text:
                entry.delete(0, 'end')
                entry.config(fg='black')
        def on_focus_out(event):
            if not entry.get():
                entry.insert(0, text)
                entry.config(fg='#7F8C8D')
        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    name_entry = tk.Entry(card, font=("Segoe UI", 11), relief="solid", bd=1, highlightthickness=1, highlightcolor="#3498DB", highlightbackground="#BDC3C7")
    name_entry.pack(fill="x", padx=30, ipady=8, pady=(0, 15))
    add_placeholder(name_entry, "ชื่อ-สกุล (Name - Surname)")

    id_entry = tk.Entry(card, font=("Segoe UI", 11), relief="solid", bd=1, highlightthickness=1, highlightcolor="#3498DB", highlightbackground="#BDC3C7")
    id_entry.pack(fill="x", padx=30, ipady=8, pady=(0, 25))
    add_placeholder(id_entry, "รหัสนักศึกษา (Student ID)")

    def submit():
        name = name_entry.get()
        student_id = id_entry.get()
        if name and student_id and name != "ชื่อ-สกุล (Name - Surname)" and student_id != "รหัสนักศึกษา (Student ID)":
            sio.emit('register_data', {'pc_name': PC_NAME, 'name': name, 'student_id': student_id})
            dialog.destroy()
        else:
            messagebox.showwarning("แจ้งเตือน", "กรุณากรอกข้อมูลให้ครบถ้วน", parent=dialog)

    submit_btn = tk.Button(card, text="ตกลง", font=("Segoe UI", 12, "bold"), bg="#285C8D", fg="white", activebackground="#1F476D", activeforeground="white", relief="flat", command=submit)
    submit_btn.pack(fill="x", padx=30, ipady=6, pady=(0, 10))
    
    footer_frame = tk.Frame(card, bg="white")
    footer_frame.pack(side="bottom", pady=20)
    tk.Label(footer_frame, text="2FA Setting and Recovery", font=("Segoe UI", 9), bg="white", fg="#5D6D7E").pack()
    tk.Label(footer_frame, text="Forgot password ⚪ Sign-up ⚪ Terms of use", font=("Segoe UI", 9), bg="white", fg="#5D6D7E").pack()

def show_message_dialog(message):
    dialog = tk.Toplevel(root)
    dialog.title("ข้อความจากอาจารย์")
    dialog.geometry("450x380")
    dialog.configure(bg="#FADCD9")
    dialog.attributes("-topmost", True)
    dialog.resizable(False, False)

    dialog.update_idletasks()
    w = dialog.winfo_screenwidth()
    h = dialog.winfo_screenheight()
    x = int(w/2 - 450/2)
    y = int(h/2 - 380/2)
    dialog.geometry(f"+{x}+{y}")

    card = tk.Frame(dialog, bg="white", bd=0)
    card.place(relx=0.5, rely=0.5, anchor="center", width=390, height=320)

    tk.Label(card, text="🔔", font=("Segoe UI", 36), bg="white").pack(pady=(20, 5))
    tk.Label(card, text="ประกาศจากอาจารย์", font=("Segoe UI", 14, "bold"), bg="white", fg="#E74C3C").pack(pady=(0, 15))

    tk.Label(card, text=message, font=("Segoe UI", 16, "bold"), bg="white", fg="#333333", wraplength=350, justify="center").pack(pady=(0, 20), expand=True)

    close_btn = tk.Button(card, text="รับทราบ", font=("Segoe UI", 12, "bold"), bg="#285C8D", fg="white", activebackground="#1F476D", activeforeground="white", relief="flat", command=dialog.destroy)
    close_btn.pack(fill="x", padx=40, ipady=6, side="bottom", pady=25)

@sio.on('remote_input')
def on_remote_input(data):
    if data.get('target') != PC_NAME: return
    try:
        if data['type'] == 'click':
            sw, sh = pyautogui.size()
            x = int(data['x'] * sw)
            y = int(data['y'] * sh)
            # 🛠️ ดึงค่าปุ่มเมาส์ (ซ้าย/ขวา) มาสั่งกด
            btn = data.get('button', 'left') 
            pyautogui.click(x, y, button=btn)
            
        elif data['type'] == 'char':
            # 🛠️ ใช้ไลบรารี keyboard เขียนตัวอักษร Unicode (ภาษาไทย) โดยตรง
            keyboard.write(data['char'])
            
        elif data['type'] == 'key':
            key = data['key'].lower()
            if key == 'return': key = 'enter'
            elif key == 'space': key = 'space'
            elif 'shift' in key: key = 'shift'
            elif 'control' in key: key = 'ctrl'
            elif 'alt' in key: key = 'alt'
            elif key == 'backspace': key = 'backspace'
            
            try: pyautogui.press(key)
            except: pass
    except: pass
@sio.on('execute_command')
def on_command(data):
    global SEND_INTERVAL, BLOCKED_APPS
    action = data.get('action')
    target = data.get('target', 'all')
    
    if target != 'all' and target != PC_NAME: return

    if action == 'lock': root.after(0, lambda: show_fullscreen_ui("🔒\nถูกล็อกการใช้งานโดยอาจารย์", "black", "red"))
    elif action in ['unlock', 'stop_broadcast']: root.after(0, hide_fullscreen_ui)
    elif action == 'register': root.after(0, show_register_dialog)
    elif action == 'start_broadcast': root.after(0, lambda: show_fullscreen_ui(show_image=True))
    elif action == 'shutdown': 
        root.after(0, lambda: show_fullscreen_ui("🔴\nระบบกำลังปิดเครื่อง...", "black", "red"))
        os.system("shutdown /s /t 5")
    elif action == 'restart': 
        root.after(0, lambda: show_fullscreen_ui("🔄\nระบบกำลังรีสตาร์ท...", "black", "orange"))
        os.system("shutdown /r /t 5")
    elif action == 'notify': root.after(0, lambda: show_message_dialog(data['message']))
    elif action == 'receive_file':
        try:
            filename = data.get('filename')
            file_base64 = data.get('file_data')
            
            save_folder = r"C:\PCLab_Student_Works"
            os.makedirs(save_folder, exist_ok=True)
            save_path = os.path.join(save_folder, filename)
            
            file_bytes = base64.b64decode(file_base64)
            with open(save_path, 'wb') as f: f.write(file_bytes)
            
            try: os.startfile(save_folder)
            except: pass
            
            root.after(0, lambda: messagebox.showinfo("ไฟล์ใหม่จากอาจารย์", f"ได้รับไฟล์: {filename}\nระบบบันทึกและเปิดโฟลเดอร์ {save_folder} ให้แล้ว!"))
        except: pass
            
    elif action == 'set_high_fps' and data.get('target') == PC_NAME: SEND_INTERVAL = 0.05 
    elif action == 'set_low_fps' and data.get('target') == PC_NAME: SEND_INTERVAL = 0.3 
    elif action == 'block_web': apply_hosts_blocking(data['sites'])
    elif action == 'unblock_web': clear_hosts_blocking()
    elif action == 'block_app': BLOCKED_APPS = data['apps']
    elif action == 'unblock_app': BLOCKED_APPS = []

@sio.on('broadcast_frame')
def on_broadcast(data):
    if IS_LOCKED:
        def update_image():
            img_data = base64.b64decode(data['image_data'])
            img = Image.open(io.BytesIO(img_data))
            
            user32 = ctypes.windll.user32
            screen_w = user32.GetSystemMetrics(0)
            screen_h = user32.GetSystemMetrics(1)
            img = img.resize((screen_w, screen_h)) 
            
            photo = ImageTk.PhotoImage(image=img)
            broadcast_label.config(image=photo)
            broadcast_label.image = photo 
        root.after(0, update_image)

def capture_and_send_screen():
    global SEND_INTERVAL
    with mss() as sct:
        monitor = sct.monitors[1] 
        while True:
            try:
                sct_img = sct.grab(monitor)
                # 🛠️ ปรับเป็น 720p (1280x720) และลด Quality เหลือ 60 เพื่อให้ส่งข้อมูลได้เร็วและไม่ค้าง
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX").resize((1280, 720)) 
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=60)
                
                cpu_usage = psutil.cpu_percent(interval=None)
                ram_usage = psutil.virtual_memory().percent
                ping = "OK" if psutil.net_io_counters().bytes_sent > 0 else "Low"
                
                sio.emit('screen_update', {
                    'pc_name': PC_NAME, 
                    'image_data': base64.b64encode(buffer.getvalue()).decode('utf-8'),
                    'cpu': cpu_usage,
                    'ram': ram_usage,
                    'net_status': ping
                })
                time.sleep(SEND_INTERVAL) 
            except: time.sleep(1)

if __name__ == '__main__':
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except: pass

    root = tk.Tk()
    root.title("PC-LAB Student Agent")
    root.geometry("400x250")
    root.eval('tk::PlaceWindow . center')
    root.configure(bg="#F8F9F9")
    root.protocol("WM_DELETE_WINDOW", lambda: None) 
    
    student_dashboard_frame = tk.Frame(root, bg="#F8F9F9")
    student_dashboard_frame.pack(expand=True, fill="both")
    
    tk.Label(student_dashboard_frame, text=f"💻 ประจำเครื่อง: {PC_NAME}", font=("Segoe UI", 16, "bold"), bg="#F8F9F9").pack(pady=(30, 5))
    tk.Label(student_dashboard_frame, text="สถานะ: 🟢 เชื่อมต่อกับระบบส่วนกลางแล้ว", font=("Segoe UI", 10), fg="#27AE60", bg="#F8F9F9").pack(pady=5)
    
    btn_send = tk.Button(student_dashboard_frame, text="📤 ส่งไฟล์งานให้อาจารย์", font=("Segoe UI", 11, "bold"), bg="#3498DB", fg="white", 
                         width=20, height=2, relief="flat", cursor="hand2", command=send_work_to_teacher)
    btn_send.pack(pady=20)
    
    msg_label = tk.Label(root, font=("Segoe UI", 36, "bold"), bg="black", bd=0, highlightthickness=0)
    broadcast_label = tk.Label(root, bg="black", bd=0, highlightthickness=0) 
    
    root.bind("<FocusOut>", lambda e: keep_focus_loop())
    
    threading.Thread(target=lambda: (sio.connect(TEACHER_IP), capture_and_send_screen()), daemon=True).start()
    root.mainloop()