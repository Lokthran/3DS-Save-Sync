import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import json
import os
import threading
import socket
from ftplib import FTP, error_perm
import shutil
from datetime import datetime
import logging

# --- Konfiguration ---
# Das Skript findet seinen eigenen Speicherort
script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(script_dir, 'config.json')
LOG_FILE = os.path.join(script_dir, 'sync_tool.log')

# Logging konfigurieren
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename=LOG_FILE, filemode='w')

# FTP Konstanten
FTP_PORT = 5000
FTP_TIMEOUT = 2

class CategoryManager(ctk.CTkToplevel):
    """Ein separates Fenster, um die Speicherkategorien zu verwalten."""
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.title("Manage Categories")
        self.geometry("400x400")
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        add_frame = ctk.CTkFrame(self)
        add_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        add_frame.grid_columnconfigure(0, weight=1)
        
        self.new_category_entry = ctk.CTkEntry(add_frame, placeholder_text="New category name")
        self.new_category_entry.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(add_frame, text="Add", width=50, command=self.add_category).grid(row=0, column=1, padx=5, pady=5)

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Existing Categories")
        self.scroll_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.scroll_frame.grid_columnconfigure(0, weight=1)
        
        self.refresh_list()

    def refresh_list(self):
        """Aktualisiert die Liste der Kategorien."""
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
            
        for name in sorted(self.master.path_data.keys()):
            frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            frame.grid(sticky="ew", pady=2)
            frame.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(frame, text=name).grid(row=0, column=0, sticky="w")
            ctk.CTkButton(frame, text="Remove", width=60, command=lambda n=name: self.remove_category(n)).grid(row=0, column=1, padx=5)

    def add_category(self):
        new_name = self.new_category_entry.get()
        if new_name and new_name not in self.master.path_data:
            self.master.add_category(new_name)
            self.new_category_entry.delete(0, tk.END)
            self.refresh_list()
        elif not new_name:
            messagebox.showwarning("Input Error", "Category name cannot be empty.", parent=self)
        else:
            messagebox.showwarning("Duplicate", f"A category named '{new_name}' already exists.", parent=self)
            
    def remove_category(self, name):
        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to remove the '{name}' category?", parent=self):
            self.master.remove_category(name)
            self.refresh_list()

class BackupSyncApp(ctk.CTk):
    """Hauptklasse der Anwendung."""
    def __init__(self):
        super().__init__()
        
        self.title("3DS Backup & Sync Tool")
        self.geometry("600x520")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Standard-Konfiguration (wird nur beim allerersten Start verwendet) ---
        saves_dir = os.path.join(script_dir, 'Saves')
        self.default_config = {
            'ip_address': '', 'backup_path': os.path.join(saves_dir, 'Backups').replace("\\", "/"),
            'categories': {
                '3DS': {'enabled': True, 'pc_path': os.path.join(saves_dir, '3DS').replace("\\", "/"), 'console_path': '3ds/Checkpoint/saves'},
                'NDS': {'enabled': True, 'pc_path': os.path.join(saves_dir, 'NDS').replace("\\", "/"), 'console_path': 'roms/nds/saves'},
                'GBA': {'enabled': True, 'pc_path': os.path.join(saves_dir, 'GBA').replace("\\", "/"), 'console_path': 'roms/gba/saves'}
            }
        }
        
        # --- UI Aufbau ---
        self.action_frame = ctk.CTkFrame(self)
        self.action_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.action_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.action_frame, text="3DS IP:").grid(row=0, column=0, padx=10, pady=5)
        self.ip_entry = ctk.CTkEntry(self.action_frame, placeholder_text="Enter IP or leave empty to scan")
        self.ip_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        self.download_button = ctk.CTkButton(self.action_frame, text="⬇️ Download to PC", command=lambda: self.start_process('download'))
        self.download_button.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.upload_button = ctk.CTkButton(self.action_frame, text="⬆️ Upload to 3DS", command=lambda: self.start_process('upload'))
        self.upload_button.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        
        self.path_frame = ctk.CTkFrame(self)
        self.path_frame.grid(row=1, column=0, padx=10, pady=0, sticky="nsew")
        self.path_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.path_frame, text="Category:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.category_combobox = ctk.CTkComboBox(self.path_frame, command=self.on_category_select)
        self.category_combobox.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self.manage_button = ctk.CTkButton(self.path_frame, text="Manage...", width=80, command=self.open_category_manager)
        self.manage_button.grid(row=0, column=2, padx=10, pady=10)

        self.previous_category = None # Zum Speichern der Änderungen beim Wechseln
        self.enabled_var = ctk.BooleanVar()
        self.pc_path_var = ctk.StringVar()
        self.console_path_var = ctk.StringVar()
        
        ctk.CTkCheckBox(self.path_frame, text="Enable this category for sync", variable=self.enabled_var).grid(row=1, column=0, columnspan=3, padx=10, pady=10, sticky="w")
        ctk.CTkLabel(self.path_frame, text="PC Path:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.pc_path_entry = ctk.CTkEntry(self.path_frame, textvariable=self.pc_path_var)
        self.pc_path_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkButton(self.path_frame, text="...", width=30, command=lambda: self.browse_pc_path(self.pc_path_entry)).grid(row=2, column=2, padx=5, pady=5)
        ctk.CTkLabel(self.path_frame, text="Console Path:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.console_path_entry = ctk.CTkEntry(self.path_frame, textvariable=self.console_path_var)
        self.console_path_entry.grid(row=3, column=1, columnspan=2, padx=10, pady=5, sticky="ew")
        
        self.path_data = {}
        
        self.backup_frame = ctk.CTkFrame(self)
        self.backup_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        self.backup_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.backup_frame, text="Backup Folder (PC):").grid(row=0, column=0, padx=10, pady=5)
        self.backup_entry = ctk.CTkEntry(self.backup_frame)
        self.backup_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkButton(self.backup_frame, text="...", width=30, command=lambda: self.browse_pc_path(self.backup_entry)).grid(row=0, column=2, padx=5, pady=5)
        
        self.status_frame = ctk.CTkFrame(self)
        self.status_frame.grid(row=3, column=0, padx=10, pady=10, sticky="ew")
        self.status_frame.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(self.status_frame, text="Status: Ready", anchor="w")
        self.status_label.grid(row=0, column=0, padx=10, pady=(5,0), sticky="ew")
        self.progressbar = ctk.CTkProgressBar(self.status_frame, mode='indeterminate')
        
        self.load_config()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_category_select(self, selected_category):
        """Speichert die alte Kategorie und lädt die neue."""
        if self.previous_category and self.previous_category in self.path_data:
            self.path_data[self.previous_category]['enabled'] = self.enabled_var.get()
            self.path_data[self.previous_category]['pc_path'] = self.pc_path_var.get()
            self.path_data[self.previous_category]['console_path'] = self.console_path_var.get()

        if selected_category in self.path_data:
            data = self.path_data[selected_category]
            self.enabled_var.set(data.get('enabled', False))
            self.pc_path_var.set(data.get('pc_path', ''))
            self.console_path_var.set(data.get('console_path', ''))
        
        self.previous_category = selected_category

    def load_config(self):
        """Lädt Einstellungen und erstellt die Standard-Ordnerstruktur, falls nötig."""
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = self.default_config
            try:
                for category in config['categories'].values():
                    os.makedirs(category['pc_path'], exist_ok=True)
                os.makedirs(config['backup_path'], exist_ok=True)
            except OSError as e:
                logging.error(f"Could not create default directories: {e}")
        
        self.ip_entry.insert(0, config.get('ip_address', ''))
        self.backup_entry.insert(0, config.get('backup_path', ''))
        self.path_data = config.get('categories', {})
        
        category_names = sorted(self.path_data.keys())
        if category_names:
            self.category_combobox.configure(values=category_names)
            self.category_combobox.set(category_names[0])
            self.after(20, self.on_category_select, category_names[0])
        else:
            self.category_combobox.configure(values=[]); self.category_combobox.set("")

    def save_config(self):
        """Speichert alle Kategorien und ihre Einstellungen."""
        self.on_category_select(self.category_combobox.get())
        config = {'ip_address': self.ip_entry.get(), 'backup_path': self.backup_entry.get(), 'categories': self.path_data}
        with open(CONFIG_FILE, 'w') as f: json.dump(config, f, indent=4)
            
    def open_category_manager(self):
        """Öffnet das Fenster zum Verwalten der Kategorien."""
        self.on_category_select(self.category_combobox.get())
        manager = CategoryManager(self)
        manager.wait_window()
        category_names = sorted(self.path_data.keys())
        current_selection = self.category_combobox.get()
        self.category_combobox.configure(values=category_names)
        if current_selection in category_names:
            self.category_combobox.set(current_selection)
        elif category_names:
            self.category_combobox.set(category_names[0])
        else:
            self.category_combobox.set("")
            self.enabled_var.set(False); self.pc_path_var.set(""); self.console_path_var.set("")
        self.on_category_select(self.category_combobox.get())
        
    def add_category(self, name):
        """Fügt eine neue Kategorie hinzu."""
        saves_dir = os.path.join(script_dir, 'Saves')
        default_pc_path = os.path.join(saves_dir, name).replace("\\", "/")
        os.makedirs(default_pc_path, exist_ok=True)
        self.path_data[name] = {'enabled': False, 'pc_path': default_pc_path, 'console_path': ''}

    def remove_category(self, name):
        """Entfernt eine Kategorie."""
        if name in self.path_data:
            del self.path_data[name]

    def on_closing(self): self.save_config(); self.destroy()
    def update_status(self, message): self.after(0, self.status_label.configure, {"text": f"Status: {message}"})
    def set_buttons_state(self, state):
        self.download_button.configure(state=state); self.upload_button.configure(state=state)
        if state == "disabled": self.progressbar.grid(row=1, column=0, padx=10, pady=5, sticky="ew"); self.progressbar.start()
        else: self.progressbar.stop(); self.progressbar.grid_remove()

    def start_process(self, mode): self.set_buttons_state("disabled"); threading.Thread(target=self.run_process, args=(mode,), daemon=True).start()

    def run_process(self, mode):
        logging.info(f"--- Starting process: {mode} ---")
        try:
            self.on_category_select(self.category_combobox.get())
            backup_base_path = self.backup_entry.get()
            if not backup_base_path or not os.path.isdir(backup_base_path):
                msg = "Error: Please set a valid Backup Folder."; logging.error(msg); self.update_status(msg); return
            
            tasks_to_run = []
            for key, data in self.path_data.items():
                if data.get('enabled'):
                    if not data.get('pc_path') or not data.get('console_path'):
                        msg = f"Warning: Skipping '{key}' because paths are incomplete."
                        logging.warning(msg); self.update_status(msg); continue
                    tasks_to_run.append({
                        'key': key, 'pc_path': data.get('pc_path'),
                        'console_path': data.get('console_path').strip("/")
                    })

            if not tasks_to_run:
                msg = "Error: No valid & enabled categories to process."; logging.error(msg); self.update_status(msg); return
            ip = self.ip_entry.get()
            if not ip or not self.check_ip(ip):
                self.update_status("Invalid IP. Scanning network..."); ip = self.scan_network()
                if not ip: self.update_status("Error: Could not find 3DS on the network."); return
                self.after(0, self.ip_entry.delete, 0, tk.END); self.after(0, self.ip_entry.insert, 0, ip)
            
            with FTP() as ftp:
                self.update_status(f"Connecting to {ip}..."); ftp.connect(ip, FTP_PORT, timeout=10); ftp.login()
                
                for task in tasks_to_run:
                    active_key, pc_path, console_path = task['key'], task['pc_path'], task['console_path']
                    self.update_status(f"Processing '{active_key}'..."); logging.info(f"--- Processing category: {active_key} ---")
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    
                    if mode == 'download':
                        self.update_status(f"Backing up PC: '{active_key}'...");
                        if os.path.exists(pc_path) and os.listdir(pc_path):
                            shutil.copytree(pc_path, os.path.join(backup_base_path, f"pc_{active_key}_backup_{timestamp}"))
                        self.update_status(f"Downloading from 3DS: '{active_key}'...");
                        if os.path.exists(pc_path): shutil.rmtree(pc_path)
                        self.download_recursive(ftp, console_path, pc_path)
                    elif mode == 'upload':
                        self.update_status(f"Backing up 3DS: '{active_key}'...");
                        backup_dest = os.path.join(backup_base_path, f"3ds_{active_key}_backup_{timestamp}")
                        self.download_recursive(ftp, console_path, backup_dest)
                        self.update_status(f"Uploading to 3DS: '{active_key}'...");
                        self.upload_recursive(ftp, pc_path, console_path)
            self.update_status("All tasks completed successfully!")
        except Exception as e:
            self.update_status(f"Error: {e}")
            logging.error(f"An error occurred in the main process: {e}", exc_info=True)
        finally:
            self.after(0, self.set_buttons_state, "normal")
            
    def download_recursive(self, ftp, remote_dir, local_dir):
        # This function is now robust enough for flat and nested directories
        os.makedirs(local_dir, exist_ok=True)
        try:
            # Navigate to the target directory step-by-step
            ftp.cwd('/')
            for part in remote_dir.split('/'):
                ftp.cwd(part)
        except error_perm as e:
            msg = f"Error: Console path '{remote_dir}' not found."
            logging.error(f"{msg} - {e}"); self.update_status(msg); return

        for item_path in ftp.nlst():
            item_name = item_path.split('/')[-1]
            local_item_path = os.path.join(local_dir, item_name)
            
            try:
                # Attempt to change into the item to see if it's a directory
                ftp.cwd(item_name)
                # If successful, it's a directory -> recursive call
                # We need to pass the full path for the next level
                full_next_remote_dir = f"{remote_dir}/{item_name}"
                self.download_recursive(ftp, full_next_remote_dir, local_item_path)
                ftp.cwd("..") # Go back up to the parent directory
            except error_perm:
                # If it fails, it's a file -> download it
                with open(local_item_path, 'wb') as f:
                    ftp.retrbinary(f"RETR {item_name}", f.write)

    def upload_recursive(self, ftp, local_dir, remote_dir):
        # Navigate to the target directory, creating parts if they don't exist
        ftp.cwd('/')
        for part in remote_dir.split('/'):
            try: ftp.cwd(part)
            except error_perm: ftp.mkd(part); ftp.cwd(part)
        
        # Upload contents of the current local directory
        for item_name in os.listdir(local_dir):
            local_item_path = os.path.join(local_dir, item_name)
            if os.path.isfile(local_item_path):
                with open(local_item_path, 'rb') as f: ftp.storbinary(f"STOR {item_name}", f)
            elif os.path.isdir(local_item_path):
                try: ftp.mkd(item_name)
                except error_perm: pass # Directory probably already exists
                # The recursive call must be for the sub-directory
                self.upload_recursive(ftp, local_item_path, f"{remote_dir}/{item_name}")

    def check_ip(self, ip):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(FTP_TIMEOUT)
            try: s.connect((ip, FTP_PORT)); return True
            except (socket.timeout, ConnectionRefusedError, OSError): return False

    def scan_network(self):
        local_subnets = []
        try:
            _, _, ip_list = socket.gethostbyname_ex(socket.gethostname())
            for ip in ip_list:
                if ip.startswith(('192.168.', '10.', '172.')):
                    subnet = ".".join(ip.split('.')[:-1])
                    if subnet not in local_subnets: local_subnets.append(subnet)
        except socket.gaierror: return None
        if not local_subnets: return None
        self.update_status(f"Scanning networks: {local_subnets}...")
        for subnet in local_subnets:
            found_ip_list = []
            threads = []
            for i in range(1, 255):
                thread = threading.Thread(target=self.check_ip_thread_worker, args=(f"{subnet}.{i}", found_ip_list), daemon=True)
                threads.append(thread); thread.start()
            for t in threads: t.join() 
            if found_ip_list: return found_ip_list[0]
        return None

    def check_ip_thread_worker(self, ip, found_ip_list):
        if found_ip_list: return
        if self.check_ip(ip):
            if not found_ip_list: found_ip_list.append(ip)

if __name__ == "__main__":
    app = BackupSyncApp()
    app.mainloop()