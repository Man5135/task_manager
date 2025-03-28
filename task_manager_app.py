import tkinter as tk
from tkinter import ttk
import psutil
import logging
import locale
import importlib
import threading
import time
import os
import platform
import subprocess
import sqlite3  # Import SQLite

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class TaskManagerApp:
    def __init__(self, master):
        self.master = master
        self.languages = ["en", "ru", "fr", "de"]
        self.current_language_index = 0
        self.current_locale = self._get_system_locale()
        self.load_locale()
        master.title(self.translate("app_title"))
        master.iconbitmap(default="Task_Manager.ico")
        master.geometry("800x600")
        master.resizable(False, False)
        self.center_window(master)  # Center the main window on startup

        self.dark_blue = "#1E1E2E"  # Dark blue for background
        self.light_text = "#FFFFFF"  # White for text
        self.accent_color = "#4FC3F7"  # Light blue for accents
        self.process_data = {}  # Process data cache
        self.tree_items = {}  # Store Treeview item IDs
        self.children_visible = False

        self._create_widgets()
        self._create_database()  # Initialize database
        self.update_processes()  # Start process updates in a thread
        self.check_removable_drive()  # Start removable drive check

    def _create_database(self):
        """Create a database connection and table."""
        try:
            self.conn = sqlite3.connect('errors.db')
            self.cursor = self.conn.cursor()
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS errors (
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    level TEXT,
                    message TEXT
                )
            ''')
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database error: {e}")

    def log_error_to_db(self, level, message):
        """Log errors to the database."""
        try:
            self.cursor.execute("INSERT INTO errors (level, message) VALUES (?, ?)", (level, message))
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database logging error: {e}")

    def center_window(self, window):
        """Centers the tkinter window on the screen."""
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        window.geometry('{}x{}+{}+{}'.format(width, height, x, y))

    def _get_system_locale(self):
        """Detects the system language."""
        try:
            return locale.getdefaultlocale()[0][:2]
        except:
            return "en"

    def load_locale(self):
        """Loads translations for the current language."""
        try:
            module_name = f"locale_{self.current_locale}"
            self.locale = importlib.import_module(module_name).LOCALE
        except ModuleNotFoundError:
            logging.warning(f"Translation for {self.current_locale} not found. Using English.")
            self.locale = importlib.import_module("locale_en").LOCALE
        except Exception as e:
            logging.error(f"Error loading locale: {e}")
            self.log_error_to_db("ERROR", f"Error loading locale: {e}")
            self.locale = importlib.import_module("locale_en").LOCALE

    def translate(self, key, **kwargs):
        """Returns the translated string."""
        try:
            text = self.locale[key]
            return text.format(**kwargs)
        except KeyError:
            logging.error(f"Translation key '{key}' not found.")
            self.log_error_to_db("ERROR", f"Translation key '{key}' not found.")
            return key

    def cycle_language(self):
        """Cycles through languages."""
        self.current_language_index = (self.current_language_index + 1) % len(self.languages)
        self.current_locale = self.languages[self.current_language_index]
        self.load_locale()
        self.master.after(0, self._update_widgets_text)  # Schedules UI update
        self.master.title(self.translate("app_title"))  # Update window title
        self.language_button.config(text=self.current_locale.upper())  # Update button text

    def _create_widgets(self):
        """Creates widgets."""
        # Main layout: PanedWindow
        self.paned_window = ttk.PanedWindow(self.master, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill="both", expand=True)

        # Left sidebar frame
        self.sidebar_frame = tk.Frame(self.paned_window, width=100, relief=tk.SUNKEN, borderwidth=1)
        self.paned_window.add(self.sidebar_frame, weight=0)
        self.sidebar_frame.configure(bg=self.dark_blue)

        # Main content frame
        self.main_content_frame = tk.Frame(self.paned_window)
        self.paned_window.add(self.main_content_frame, weight=1)
        self.main_content_frame.configure(bg=self.dark_blue)

        # Removable Drive Label
        self.removable_drive_label = tk.Label(self.sidebar_frame,
                                               text=self.translate("removable_drive_status", status="Not detected"))
        self.removable_drive_label.pack(pady=5)
        self.removable_drive_label.configure(bg=self.dark_blue, fg=self.light_text)

        # Settings Button in the sidebar
        self.settings_button = tk.Button(self.sidebar_frame, text=self.translate("settings_button"),
                                         command=self.open_settings)
        self.settings_button.pack(pady=5)
        self.settings_button.configure(bg=self.dark_blue, fg=self.light_text)

        self.notebook = ttk.Notebook(self.main_content_frame)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self._setup_processes_tab()
        self._setup_performance_tab()

        self.toggle_children_button = tk.Button(self.main_content_frame,
                                                text=self.translate("toggle_children_button_show"),
                                                command=self.toggle_children)
        self.toggle_children_button.pack(pady=5)
        self.toggle_children_button.configure(bg=self.dark_blue, fg=self.light_text)

    def open_settings(self):
        """Opens the settings window."""
        self.settings_window = tk.Toplevel(self.master)
        self.settings_window.title(self.translate("settings_window_title"))
        self.settings_window.configure(bg=self.dark_blue)
        self.center_window(self.settings_window)  # Center the settings window

        # Language selection button in settings
        self.language_button = tk.Button(self.settings_window, text=self.current_locale.upper(),
                                         command=self.cycle_language)
        self.language_button.pack(pady=10, padx=10)
        self.language_button.configure(bg=self.dark_blue, fg=self.light_text)

    def _setup_processes_tab(self):
        """Sets up the processes tab."""
        self.processes_tab = tk.Frame(self.notebook)
        self.notebook.add(self.processes_tab, text=self.translate("processes_tab"))
        self.processes_tab.configure(bg=self.dark_blue)

        # Search Bar
        self.search_frame = tk.Frame(self.processes_tab)
        self.search_frame.pack(pady=5)
        self.search_frame.configure(bg=self.dark_blue)

        self.search_label = tk.Label(self.search_frame, text=self.translate("search_label"))
        self.search_label.pack(side="left", padx=5)
        self.search_label.configure(bg=self.dark_blue, fg=self.light_text)

        self.search_entry = tk.Entry(self.search_frame)
        self.search_entry.pack(side="left", padx=5)
        self.search_entry.bind("<KeyRelease>", self.search_processes)
        self.search_entry.configure(bg=self.dark_blue, fg=self.light_text, insertbackground=self.light_text)

        # Treeview and Scrollbar
        self.tree_frame = tk.Frame(self.processes_tab)
        self.tree_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree_frame.configure(bg=self.dark_blue)

        self.tree_scroll = ttk.Scrollbar(self.tree_frame, orient="vertical")
        self.tree_scroll.pack(side="right", fill="y")

        # ***Styling Treeview***
        self.style = ttk.Style()
        self.style.configure("Custom.Treeview",
                             background=self.dark_blue,
                             foreground=self.light_text,
                             fieldbackground=self.dark_blue,
                             bordercolor=self.dark_blue)  # Optional, but good for consistency

        self.tree = ttk.Treeview(self.tree_frame,
                                 columns=("pid", "имя", "статус", "ЦП (%)", "Память (МБ)", "родительский PID"),
                                 show="headings", yscrollcommand=self.tree_scroll.set,
                                 style="Custom.Treeview")  # Apply the style
        self.tree.heading("pid", text=self.translate("pid_column"))
        self.tree.heading("имя", text=self.translate("name_column"))
        self.tree.heading("статус", text=self.translate("status_column"))
        self.tree.heading("ЦП (%)", text=self.translate("cpu_column"))
        self.tree.heading("Память (МБ)", text=self.translate("memory_column"))
        self.tree.heading("родительский PID", text=self.translate("ppid_column"))

        self.tree.column("pid", width=50)
        self.tree.column("имя", width=200)
        self.tree.column("статус", width=70)
        self.tree.column("ЦП (%)", width=70)
        self.tree.column("Память (МБ)", width=70)
        self.tree.column("родительский PID", width=70)
        self.tree.pack(fill="both", expand=True)

        self.tree_scroll.config(command=self.tree.yview)
        self.tree.tag_configure('oddrow', background='#282838',
                                foreground=self.light_text)  # Darker blue
        self.tree.tag_configure('evenrow', background=self.dark_blue,
                                 foreground=self.light_text)  # Original blue

        # Context menu (right-click menu)
        self.context_menu = tk.Menu(self.master, tearoff=0, bg=self.dark_blue, fg=self.light_text)
        self.context_menu.add_command(label=self.translate("kill_process_menu"),
                                      command=self.kill_selected_process, background=self.dark_blue,
                                      foreground=self.light_text)
        self.context_menu.add_command(label=self.translate("suspend_process_menu"),
                                      command=self.suspend_selected_process, background=self.dark_blue,
                                      foreground=self.light_text)
        self.context_menu.add_command(label=self.translate("resume_process_menu"),
                                      command=self.resume_selected_process, background=self.dark_blue,
                                      foreground=self.light_text)
        self.context_menu.add_command(label=self.translate("open_file_location_menu"),
                                      command=self.open_file_location, background=self.dark_blue,
                                      foreground=self.light_text)

        # Bind right-click to the tree
        self.tree.bind("<Button-3>", self.show_context_menu)

        # Buttons for processes
        self.button_frame = tk.Frame(self.processes_tab)
        self.button_frame.pack(pady=5)
        self.button_frame.configure(bg=self.dark_blue)

        self.refresh_button = tk.Button(self.button_frame, text=self.translate("refresh_button"),
                                         command=self.refresh_processes)
        self.refresh_button.pack(side="left", padx=5)
        self.refresh_button.configure(bg=self.dark_blue, fg=self.light_text)

    def _setup_performance_tab(self):
        """Sets up the performance tab."""
        self.performance_tab = tk.Frame(self.notebook)
        self.notebook.add(self.performance_tab, text=self.translate("performance_tab"))
        self.performance_tab.configure(bg=self.dark_blue)

        # System status informer
        self.system_info_frame = tk.Frame(self.performance_tab)
        self.system_info_frame.pack(padx=10, pady=5, fill="x")
        self.system_info_frame.configure(bg=self.dark_blue)

        self.cpu_label = tk.Label(self.system_info_frame, text=self.translate("cpu_label", cpu_percent=0))
        self.cpu_label.pack(side="left", padx=10)
        self.cpu_label.configure(bg=self.dark_blue, fg=self.light_text)

        self.memory_label = tk.Label(self.system_info_frame,
                                     text=self.translate("memory_label", memory_percent=0, memory_used_gb=0,
                                                         memory_total_gb=0))
        self.memory_label.pack(side="left", padx=10)
        self.memory_label.configure(bg=self.dark_blue, fg=self.light_text)

        # Add disk labels
        self.disk_label = tk.Label(self.system_info_frame,
                                   text=self.translate("disk_label", disk_percent=0, disk_used_gb=0,
                                                       disk_total_gb=0))
        self.disk_label.pack(side="left", padx=10)
        self.disk_label.configure(bg=self.dark_blue, fg=self.light_text)

        self.update_system_info()

    def _update_widgets_text(self):
        """Updates the text of all widgets."""
        self.notebook.tab(self.processes_tab, text=self.translate("processes_tab"))
        self.notebook.tab(self.performance_tab, text=self.translate("performance_tab"))

        self.search_label.config(text=self.translate("search_label"))
        self.refresh_button.config(text=self.translate("refresh_button"))
        self.toggle_children_button.config(text=self.translate("toggle_children_button_show"))
        self.settings_button.config(text=self.translate("settings_button"))  # Settings Button

        self.tree.heading("pid", text=self.translate("pid_column"))
        self.tree.heading("имя", text=self.translate("name_column"))
        self.tree.heading("статус", text=self.translate("status_column"))
        self.tree.heading("ЦП (%)", text=self.translate("cpu_column"))
        self.tree.heading("Память (МБ)", text=self.translate("memory_column"))
        self.tree.heading("родительский PID", text=self.translate("ppid_column"))

        self.cpu_label.config(text=self.translate("cpu_label", cpu_percent=psutil.cpu_percent(interval=1)))
        memory = psutil.virtual_memory()
        self.memory_label.config(
            text=self.translate("memory_label", memory_percent=memory.percent, memory_used_gb=round(memory.used / (1024.0 ** 3), 1),
                               memory_total_gb=round(memory.total / (1024.0 ** 3), 1)))
        disk = psutil.disk_usage('/')
        self.disk_label.config(
            text=self.translate("disk_label", disk_percent=disk.percent, disk_used_gb=round(disk.used / (1024.0 ** 3), 1),
                               disk_total_gb=round(disk.total / (1024.0 ** 3), 1)))
        self.removable_drive_label.config(
            text=self.translate("removable_drive_status", status=self.removable_drive_label.cget('text').split(':')[-1]))

        if hasattr(self, 'settings_window') and self.settings_window.winfo_exists():  # if settings window exists
            self.settings_window.title(self.translate("settings_window_title"))
            self.language_button.config(text=self.current_locale.upper())

    def update_system_info(self):
        """Updates system information."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_total_gb = round(memory.total / (1024.0 ** 3), 1)
            memory_used_gb = round(memory.used / (1024.0 ** 3), 1)

            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            disk_total_gb = round(disk.total / (1024.0 ** 3), 1)
            disk_used_gb = round(disk.used / (1024.0 ** 3), 1)

            self.master.after(0, lambda: self.cpu_label.config(text=self.translate("cpu_label", cpu_percent=cpu_percent)))
            self.master.after(0,
                               lambda: self.memory_label.config(
                                   text=self.translate("memory_label", memory_percent=memory_percent,
                                                       memory_used_gb=memory_used_gb,
                                                       memory_total_gb=memory_total_gb)))
            self.master.after(0,
                               lambda: self.disk_label.config(
                                   text=self.translate("disk_label", disk_percent=disk_percent, disk_used_gb=disk_used_gb,
                                                       disk_total_gb=disk_total_gb)))

            self.master.after(1000, self.update_system_info)
        except Exception as e:
            logging.error(f"Error updating system info: {e}")
            self.log_error_to_db("ERROR", f"Error updating system info: {e}")

    def update_processes(self):
        """Updates process information."""
        threading.Thread(target=self._update_processes_thread, daemon=True).start()

    def _update_processes_thread(self):
        """Gets process information in a separate thread."""
        try:
            start_time = time.time()
            processes = []
            for process in psutil.process_iter(
                    ['pid', 'name', 'status', 'cpu_percent', 'memory_info', 'ppid']):  # Added 'cpu_percent'
                try:
                    processes.append(process.as_dict(
                        ['pid', 'name', 'status', 'cpu_percent', 'memory_info', 'ppid']))  # Added 'cpu_percent'
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                    logging.warning(f"Failed to get process {e}")
                    self.log_error_to_db("WARNING", f"Failed to get process {e}")

            end_time = time.time()
            logging.debug(f"Getting process data took: {end_time - start_time:.4f} seconds")

            self.master.after(0, lambda: self.process_data_update(processes))
            self.master.after(2000, self.update_processes)  # Re-schedules itself

        except Exception as e:
            logging.error(f"Error getting process list: {e}")
            self.log_error_to_db("ERROR", f"Error getting process list: {e}")

    def process_data_update(self, processes):
        """Updates the process data cache and interface."""
        start_time = time.time()
        new_process_data = {}
        for process in processes:
            try:
                pid = process['pid']
                new_process_data[pid] = {
                    'name': process['name'],
                    'status': process['status'],
                    'cpu_percent': process['cpu_percent'],  # Store CPU usage
                    'memory_mb': process['memory_info'].rss / (1024 * 1024),
                    'ppid': process['ppid'],
                    'process_obj': psutil.Process(pid)
                }
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                logging.warning(f"Failed to get data about process with PID {process['pid']}: {e}")
                self.log_error_to_db("WARNING", f"Failed to get data about process with PID {process['pid']}: {e}")
                continue
            except Exception as e:
                logging.error(f"Error processing process with PID {process['pid']}: {e}")
                self.log_error_to_db("ERROR", f"Error processing process with PID {process['pid']}: {e}")
                continue

        self.process_data = new_process_data
        end_time = time.time()
        logging.debug(f"Processing process data took: {end_time - start_time:.4f} seconds")
        self.master.after(0, self.refresh_processes)

    def refresh_processes(self):
        """Refreshes the process display in Treeview."""
        start_time = time.time()
        self.search_processes()
        end_time = time.time()
        logging.debug(f"Refreshing Treeview took: {end_time - start_time:.4f} seconds")

    def search_processes(self, event=None):
        """Performs process search."""
        search_term = self.search_entry.get().lower()

        # Clear Treeview and reset ID dictionary
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_items = {}

        for pid, process_info in self.process_data.items():
            if search_term in process_info['name'].lower():
                self._insert_process_to_treeview(pid, process_info)

    def _insert_process_to_treeview(self, pid, process_info):
        """Adds a process to Treeview."""
        try:
            ppid = process_info['ppid']
            values = (pid, process_info['name'], process_info['status'],
                      f"{process_info['cpu_percent']:.1f}",  # Display CPU usage
                      f"{process_info['memory_mb']:.1f}", ppid)

            if ppid == 0 or ppid not in self.process_data:
                item_id = self.tree.insert("", "end", values=values)
                self.tree_items[pid] = item_id
            else:
                if self.children_visible:
                    parent_id = ppid
                    if parent_id in self.tree_items:
                        self.tree.insert(self.tree_items[parent_id], "end", values=values)
                    else:
                        item_id = self.tree.insert("", "end", values=values)
                        self.tree_items[pid] = item_id

        except Exception as e:
            logging.error(f"Error adding process with PID {pid} to Treeview: {e}")
            self.log_error_to_db("ERROR", f"Error adding process with PID {pid} to Treeview: {e}")

    def kill_selected_process(self):
        """Kills the selected process."""
        try:
            selected_item = self.tree.selection()[0]
            pid = int(self.tree.item(selected_item, "values")[0])

            if pid in self.process_data:
                process = self.process_data[pid]['process_obj']
                process.kill()
                logging.info(f"Process with PID {pid} killed.")
                self.refresh_processes()
            else:
                logging.warning(f"Process with PID {pid} not found.")
                self.log_error_to_db("WARNING", f"Process with PID {pid} not found.")
                self.refresh_processes()
        except IndexError:
            logging.warning(self.translate("no_process_selected"))
            self.log_error_to_db("WARNING", self.translate("no_process_selected"))
        except psutil.NoSuchProcess:
            logging.warning(self.translate("process_not_found", pid=pid))
            self.log_error_to_db("WARNING", self.translate("process_not_found", pid=pid))
            self.refresh_processes()
        except psutil.AccessDenied:
            logging.warning(self.translate("access_denied", pid=pid))
            self.log_error_to_db("WARNING", self.translate("access_denied", pid=pid))
        except Exception as e:
            logging.error(self.translate("error_killing_process", error=e))
            self.log_error_to_db("ERROR", self.translate("error_killing_process", error=e))

    def suspend_selected_process(self):
        """Suspends the selected process."""
        try:
            selected_item = self.tree.selection()[0]
            pid = int(self.tree.item(selected_item, "values")[0])

            if pid in self.process_data:
                process = self.process_data[pid]['process_obj']
                process.suspend()
                logging.info(f"Process with PID {pid} suspended.")
                self.refresh_processes()
            else:
                logging.warning(f"Process with PID {pid} not found.")
                self.log_error_to_db("WARNING", f"Process with PID {pid} not found.")
                self.refresh_processes()
        except IndexError:
            logging.warning(self.translate("no_process_selected"))
            self.log_error_to_db("WARNING", self.translate("no_process_selected"))
        except psutil.NoSuchProcess:
            logging.warning(self.translate("process_not_found", pid=pid))
            self.log_error_to_db("WARNING", self.translate("process_not_found", pid=pid))
            self.refresh_processes()
        except psutil.AccessDenied:
            logging.warning(self.translate("access_denied", pid=pid))
            self.log_error_to_db("WARNING", self.translate("access_denied", pid=pid))
        except Exception as e:
            logging.error(self.translate("error_suspending_process", error=e))
            self.log_error_to_db("ERROR", self.translate("error_suspending_process", error=e))

    def resume_selected_process(self):
        """Resumes the selected process."""
        try:
            selected_item = self.tree.selection()[0]
            pid = int(self.tree.item(selected_item, "values")[0])

            if pid in self.process_data:
                process = self.process_data[pid]['process_obj']
                process.resume()
                logging.info(f"Process with PID {pid} resumed.")
                self.refresh_processes()
            else:
                logging.warning(f"Process with PID {pid} not found.")
                self.log_error_to_db("WARNING", f"Process with PID {pid} not found.")
                self.refresh_processes()
        except IndexError:
            logging.warning(self.translate("no_process_selected"))
            self.log_error_to_db("WARNING", self.translate("no_process_selected"))
        except psutil.NoSuchProcess:
            logging.warning(self.translate("process_not_found", pid=pid))
            self.log_error_to_db("WARNING", self.translate("process_not_found", pid=pid))
            self.refresh_processes()
        except psutil.AccessDenied:
            logging.warning(self.translate("access_denied", pid=pid))
            self.log_error_to_db("WARNING", self.translate("access_denied", pid=pid))
        except Exception as e:
            logging.error(self.translate("error_resuming_process", error=e))
            self.log_error_to_db("ERROR", self.translate("error_resuming_process", error=e))

    def open_file_location(self):
        """Opens the folder containing the process executable."""
        try:
            selected_item = self.tree.selection()[0]
            pid = int(self.tree.item(selected_item, "values")[0])

            if pid in self.process_data:
                try:
                    process = self.process_data[pid]['process_obj']
                    exe_path = process.exe()

                    if platform.system() == "Windows":
                        os.startfile(os.path.dirname(exe_path))  # Open folder in Windows
                    elif platform.system() == "Linux" or platform.system() == "Darwin":  # macOS is Darwin
                        subprocess.run(["xdg-open", os.path.dirname(exe_path)])  # Open folder in Linux/macOS
                    else:
                        logging.warning("Opening folder not supported on this OS.")
                        self.log_error_to_db("WARNING", "Opening folder not supported on this OS.")
                except psutil.AccessDenied:
                    logging.warning(self.translate("access_denied_location", pid=pid))
                    self.log_error_to_db("WARNING", self.translate("access_denied_location", pid=pid))
                except FileNotFoundError:
                    logging.warning(self.translate("file_not_found", pid=pid))
                    self.log_error_to_db("WARNING", self.translate("file_not_found", pid=pid))
                except Exception as e:
                    logging.error(self.translate("error_opening_location", error=e))
                    self.log_error_to_db("ERROR", self.translate("error_opening_location", error=e))
            else:
                logging.warning(f"Process with PID {pid} not found.")
                self.log_error_to_db("WARNING", f"Process with PID {pid} not found.")
                self.refresh_processes()
        except IndexError:
            logging.warning(self.translate("no_process_selected"))
            self.log_error_to_db("WARNING", self.translate("no_process_selected"))
        except Exception as e:
            logging.error(self.translate("general_error", error=e))
            self.log_error_to_db("ERROR", self.translate("general_error", error=e))

    def show_context_menu(self, event):
        """Shows the context menu on a right-click."""
        try:
            self.tree.selection_set(self.tree.identify_row(event.y))  # Select the clicked row
            # Get PID of the selected process
            selected_item = self.tree.selection()[0]
            pid = int(self.tree.item(selected_item, "values")[0])
            # Update context menu depending on process status
            self.context_menu.delete(0, tk.END)  # Clear existing items
            self.context_menu.add_command(label=self.translate("kill_process_menu"),
                                          command=self.kill_selected_process, background=self.dark_blue,
                                          foreground=self.light_text)
            if pid in self.process_data:
                process = self.process_data[pid]['process_obj']
                if process.status() == psutil.STATUS_RUNNING:
                    self.context_menu.add_command(label=self.translate("suspend_process_menu"),
                                                  command=self.suspend_selected_process, background=self.dark_blue,
                                                  foreground=self.light_text)
                elif process.status() == psutil.STATUS_STOPPED:
                    self.context_menu.add_command(label=self.translate("resume_process_menu"),
                                                  command=self.resume_selected_process, background=self.dark_blue,
                                                  foreground=self.light_text)
            self.context_menu.add_command(label=self.translate("open_file_location_menu"),
                                          command=self.open_file_location, background=self.dark_blue,
                                          foreground=self.light_text)
            self.context_menu.post(event.x_root, event.y_root)  # Show menu

        except IndexError:
            pass  # Clicked outside a row
        except Exception as e:
            logging.error(f"Error showing context menu: {e}")
            self.log_error_to_db("ERROR", f"Error showing context menu: {e}")

    def toggle_children(self):
        """Toggles the visibility of child processes."""
        self.children_visible = not self.children_visible
        if self.children_visible:
            self.toggle_children_button.config(text=self.translate("toggle_children_button_hide"))
        else:
            self.toggle_children_button.config(text=self.translate("toggle_children_button_show"))
        self.refresh_processes()

    def check_removable_drive(self):
        """Checks for the presence of a removable drive (USB drive)."""
        threading.Thread(target=self._check_removable_drive_thread, daemon=True).start()

    def _check_removable_drive_thread(self):
        """Executes the removable drive check in a separate thread."""
        try:
            removable_drive = self._find_removable_drive()
            if removable_drive:
                self.master.after(0, lambda: self.removable_drive_label.config(
                    text=self.translate("removable_drive_status", status=f"Detected: {removable_drive}")))
            else:
                self.master.after(0, lambda: self.removable_drive_label.config(
                    text=self.translate("removable_drive_status", status="Not detected")))
        except Exception as e:
            logging.error(f"Error checking removable drive: {e}")
            self.log_error_to_db("ERROR", f"Error checking removable drive: {e}")
            self.master.after(0, lambda: self.removable_drive_label.config(
                text=self.translate("removable_drive_status", status="Error")))

        self.master.after(5000, self.check_removable_drive)  # Check every 5 seconds

    def _find_removable_drive(self):
        """Finds a mounted removable disk."""
        for partition in psutil.disk_partitions():
            if 'removable' in partition.opts:
                return partition.mountpoint
        return None

    def _create_dark_blue_pattern(self):
        """Creates a dark blue pattern as an image."""
        # Create a pattern image (can be replaced with a more complex one)
        pattern_image = tk.PhotoImage(width=2, height=2)
        pattern_image.put("#222233", to=(0, 0, 1, 1))  # Darker shade
        pattern_image.put("#1E1E2E", to=(0, 1, 1, 0))  # Original dark blue

        return pattern_image

    def __del__(self):
        """Close database connection when the object is destroyed."""
        try:
            if hasattr(self, 'conn'):  # Check if the connection exists
                self.conn.close()
        except Exception as e:
            logging.error(f"Error closing database connection: {e}")
            self.log_error_to_db("ERROR", f"Error closing database connection: {e}")

root = tk.Tk()
app = TaskManagerApp(root)
root.mainloop()