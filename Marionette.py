import sys
import json
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from pynput import mouse, keyboard
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, KeyCode, Controller as KeyboardController, GlobalHotKeys, HotKey


class MacroRecorder:
    def __init__(self):
        self.events = []         
        self.recording = False
        self.playing = False
        self.start_time = None

        self.mouse_listener = None
        self.keyboard_listener = None

        self.mouse_ctrl = MouseController()
        self.keyboard_ctrl = KeyboardController()
        self._last_move_time = 0
        self._move_interval = 0.05
        self._drag_move_interval = 0.008  
        self._buttons_held = set()

    def start_recording(self):
        self.events = []
        self.recording = True
        self.start_time = time.time()
        self._buttons_held = set()

        start_x, start_y = self.mouse_ctrl.position
        self.events.append({
            "type": "move",
            "t": self._timestamp(),
            "x": start_x, "y": start_y
        })
        self._last_move_time = time.time()

        self.mouse_listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self.mouse_listener.start()
        self.keyboard_listener.start()

    def stop_recording(self):
        self.recording = False
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()

    def _timestamp(self):
        return round(time.time() - self.start_time, 4)

    def _on_move(self, x, y):
        if not self.recording:
            return
        now = time.time()
        interval = self._drag_move_interval if self._buttons_held else self._move_interval
        if now - self._last_move_time < interval:
            return
        self._last_move_time = now
        self.events.append({
            "type": "move",
            "t": self._timestamp(),
            "x": x, "y": y,
            "drag": bool(self._buttons_held)
        })

    def _on_click(self, x, y, button, pressed):
        if not self.recording:
            return
        if pressed:
            self._buttons_held.add(button)
            self._last_move_time = 0
        else:
            self._buttons_held.discard(button)
        self.events.append({
            "type": "click",
            "t": self._timestamp(),
            "x": x, "y": y,
            "button": button.name,
            "pressed": pressed
        })

    def _on_scroll(self, x, y, dx, dy):
        if not self.recording:
            return
        self.events.append({
            "type": "scroll",
            "t": self._timestamp(),
            "x": x, "y": y,
            "dx": dx, "dy": dy
        })

    def _key_to_str(self, key):
        if isinstance(key, KeyCode):
            return {"char": key.char}
        else:
            return {"name": key.name}

    def _on_press(self, key):
        if not self.recording:
            return
        self.events.append({
            "type": "key_press",
            "t": self._timestamp(),
            "key": self._key_to_str(key)
        })

    def _on_release(self, key):
        if not self.recording:
            return
        self.events.append({
            "type": "key_release",
            "t": self._timestamp(),
            "key": self._key_to_str(key)
        })

        if key == Key.esc:
            self.recording = False
            if self.mouse_listener:
                self.mouse_listener.stop()
            return False

    def play(self, repeat=1, speed=1.0, stop_flag=lambda: False):
        if not self.events:
            return

        self.playing = True
        for _ in range(repeat):
            if stop_flag():
                break
            last_t = 0.0
            for ev in self.events:
                if stop_flag():
                    break
                delay = (ev["t"] - last_t) / max(speed, 0.0001)
                if delay > 0:
                    time.sleep(delay)
                last_t = ev["t"]
                self._replay_event(ev)
        self.playing = False

    def _replay_event(self, ev):
        etype = ev["type"]
        if etype == "move":
            self.mouse_ctrl.position = (ev["x"], ev["y"])
        elif etype == "click":
            self.mouse_ctrl.position = (ev["x"], ev["y"])
            btn = getattr(Button, ev["button"])
            if ev["pressed"]:
                self.mouse_ctrl.press(btn)
            else:
                self.mouse_ctrl.release(btn)
        elif etype == "scroll":
            self.mouse_ctrl.position = (ev["x"], ev["y"])
            self.mouse_ctrl.scroll(ev["dx"], ev["dy"])
        elif etype in ("key_press", "key_release"):
            key = self._str_to_key(ev["key"])
            if key is None:
                return
            if etype == "key_press":
                self.keyboard_ctrl.press(key)
            else:
                self.keyboard_ctrl.release(key)

    def _str_to_key(self, key_dict):
        if "char" in key_dict and key_dict["char"] is not None:
            return KeyCode.from_char(key_dict["char"])
        elif "name" in key_dict:
            return getattr(Key, key_dict["name"], None)
        return None


    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.events, f, indent=2)

    def load(self, path):
        with open(path, "r") as f:
            self.events = json.load(f)


class MacroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Marionette")
        self._center_window(420, 560)
        self.root.resizable(False, False)

        self.recorder = MacroRecorder()
        self._play_stop_flag = False
        self._play_thread = None

        # Recording mini mode
        self.mini_mode = False
        self.mini_win = None
        self.mini_status_label = None
        self.mini_record_hint_label = None

        # Playback mini mode
        self.mini_play_win = None
        self.mini_play_status_label = None

        # Global hotkeys
        self.hotkey_listener = None
        self.record_hotkey_var = tk.StringVar(value="<f9>")
        self.play_hotkey_var = tk.StringVar(value="<f10>")

        self._build_ui()
        self._start_hotkey_listener()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _center_window(self, width, height):
        """Position the main window so it's centered on the screen."""
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _start_hotkey_listener(self):
        if self.hotkey_listener:
            self.hotkey_listener.stop()

        record_key = self.record_hotkey_var.get().strip()
        play_key = self.play_hotkey_var.get().strip()

        try:
            mapping = {
                record_key: lambda: self.root.after(0, self.toggle_recording),
                play_key: lambda: self.root.after(0, self.toggle_play),
            }
            self.hotkey_listener = GlobalHotKeys(mapping)
            self.hotkey_listener.start()
        except Exception as e:
            messagebox.showerror(
                "Invalid hotkey",
                f"Couldn't register hotkeys ({e}).\n"
                "Available hotkeys: <F keys>, <Combo> + <Keys>, <Number keys>"
            )

    def apply_hotkeys(self):
        self._start_hotkey_listener()
        self.hotkey_status_var.set(
            f"Active: Record={self.record_hotkey_var.get()}  Play={self.play_hotkey_var.get()}"
        )
        if self.mini_play_status_label is not None:
            self._refresh_mini_play_hint()
        if self.mini_record_hint_label is not None:
            self._refresh_mini_record_hint()

    def _on_close(self):
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        if self.recorder.recording:
            self.recorder.stop_recording()
        self.hide_mini_mode()
        self.hide_mini_mode_play()
        self.root.destroy()

    def _sync_main_window(self):
        try:
            if self.recorder.recording or self.recorder.playing:
                if self.root.state() != "withdrawn":
                    self.root.withdraw()
            elif self.root.state() == "withdrawn":
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
        except tk.TclError:
            pass

    def _make_draggable(self, win, widgets):
        offset = {"x": 0, "y": 0}

        def start_drag(event):
            offset["x"] = event.x_root - win.winfo_rootx()
            offset["y"] = event.y_root - win.winfo_rooty()

        def do_drag(event):
            x = event.x_root - offset["x"]
            y = event.y_root - offset["y"]
            win.geometry(f"+{x}+{y}")

        for widget in widgets:
            widget.bind("<ButtonPress-1>", start_drag)
            widget.bind("<B1-Motion>", do_drag)

    def _make_click_through(self, win):
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )
        except Exception:
            pass

    def _force_topmost(self, win):
        """Push a window above every other window, including other apps'
        always-on-top windows (fullscreen games, other utilities, etc).
        tkinter's own -topmost attribute only competes within its own
        toolkit's notion of layering, so on Windows we also go straight to
        the Win32 z-order API, which wins against other topmost windows
        because it's reasserted continuously."""
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass

        if sys.platform == "win32":
            try:
                hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
                HWND_TOPMOST = -1
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                ctypes.windll.user32.SetWindowPos(
                    hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
                )
            except Exception:
                pass
        else:
            try:
                win.lift()
            except tk.TclError:
                pass

    def _keep_topmost(self, win):
        """Reassert the topmost layer on a short timer for as long as the
        window is alive, so it stays above windows other apps raise later."""
        if win is None:
            return
        try:
            if not win.winfo_exists():
                return
        except tk.TclError:
            return
        self._force_topmost(win)
        win.after(250, lambda: self._keep_topmost(win))

    def _refresh_mini_record_hint(self):
        if self.mini_record_hint_label is None:
            return
        key_label = self.record_hotkey_var.get().strip()
        self.mini_record_hint_label.config(text=f"Press {key_label} to stop")

    def show_mini_mode(self):
        if self.mini_mode:
            return

        self.mini_mode = True
        self._sync_main_window()

        self.mini_win = tk.Toplevel(self.root)
        self.mini_win.overrideredirect(True)
        self.mini_win.attributes("-topmost", True)
        self.mini_win.wm_attributes("-topmost", True)
        try:
            self.mini_win.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        self.mini_win.configure(bg="#1e1e1e")

        bar = tk.Frame(self.mini_win, bg="#1e1e1e")
        bar.pack(fill="both", expand=True, padx=8, pady=6)

        self.mini_status_label = tk.Label(
            bar, text="Recording", fg="green", bg="#1e1e1e",
            font=("Segoe UI", 9, "bold"), anchor="w"
        )
        self.mini_status_label.pack(side="top", anchor="w")

        self.mini_record_hint_label = tk.Label(
            bar, text="", fg="#cccccc", bg="#1e1e1e",
            font=("Segoe UI", 8), anchor="w"
        )
        self.mini_record_hint_label.pack(side="top", anchor="w")
        self._refresh_mini_record_hint()

        self._make_draggable(self.mini_win, (self.mini_win, bar, self.mini_status_label, self.mini_record_hint_label))

        self.mini_win.update_idletasks()
        w = self.mini_win.winfo_reqwidth() + 12
        h = self.mini_win.winfo_reqheight() + 10

        self.mini_win.geometry(f"{w}x{h}+0+0")

        self.mini_win.protocol("WM_DELETE_WINDOW", self.toggle_recording)
        self._force_topmost(self.mini_win)
        self._keep_topmost(self.mini_win)

    def hide_mini_mode(self):
        self.mini_mode = False
        if self.mini_win is not None:
            try:
                self.mini_win.destroy()
            except tk.TclError:
                pass
        self.mini_win = None
        self.mini_status_label = None
        self.mini_record_hint_label = None
        self._sync_main_window()

    def show_mini_mode_play(self):
        if self.mini_play_win is not None:
            return

        try:
            if self.root.state() != "withdrawn":
                self.root.withdraw()
        except tk.TclError:
            pass

        self.mini_play_win = tk.Toplevel(self.root)
        self.mini_play_win.overrideredirect(True)
        self.mini_play_win.attributes("-topmost", True)
        self.mini_play_win.wm_attributes("-topmost", True)
        try:
            self.mini_play_win.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        self.mini_play_win.configure(bg="#1e1e1e")

        bar = tk.Frame(self.mini_play_win, bg="#1e1e1e")
        bar.pack(fill="both", expand=True, padx=8, pady=6)

        self.mini_play_status_label = tk.Label(
            bar, text="Playing", fg="#2ecc71", bg="#1e1e1e",
            font=("Segoe UI", 9, "bold"), anchor="w"
        )
        self.mini_play_status_label.pack(side="top", anchor="w")

        self.mini_play_hint_label = tk.Label(
            bar, text="", fg="#cccccc", bg="#1e1e1e",
            font=("Segoe UI", 8), anchor="w"
        )
        self.mini_play_hint_label.pack(side="top", anchor="w")
        self._refresh_mini_play_hint()
        self._make_click_through(self.mini_play_win)

        self.mini_play_win.update_idletasks()
        w = self.mini_play_win.winfo_reqwidth() + 12
        h = self.mini_play_win.winfo_reqheight() + 10
        self.mini_play_win.geometry(f"{w}x{h}+0+0")
        self._force_topmost(self.mini_play_win)
        self._keep_topmost(self.mini_play_win)

    def _refresh_mini_play_hint(self):
        if self.mini_play_status_label is None:
            return
        key_label = self.play_hotkey_var.get().strip()
        self.mini_play_hint_label.config(text=f"Press {key_label} to stop")

    def hide_mini_mode_play(self):
        if self.mini_play_win is not None:
            try:
                self.mini_play_win.destroy()
            except tk.TclError:
                pass
        self.mini_play_win = None
        self.mini_play_status_label = None
        self._sync_main_window()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        title = tk.Label(self.root, text="Marionette", font=("Courier", 16, "bold"))
        title.pack(pady=(15, 5))

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(**pad)

        self.record_btn = tk.Button(btn_frame, text="● Start Recording", width=18,
                                     command=self.toggle_recording, bg="#e74c3c", fg="white")
        self.record_btn.grid(row=0, column=0, padx=5, pady=5)

        self.play_btn = tk.Button(btn_frame, text="▶ Play", width=18,
                                   command=self.toggle_play, bg="#2ecc71", fg="white")
        self.play_btn.grid(row=0, column=1, padx=5, pady=5)

        self.save_btn = tk.Button(btn_frame, text="💾 Save Macro", width=18, command=self.save_macro)
        self.save_btn.grid(row=1, column=0, padx=5, pady=5)

        self.load_btn = tk.Button(btn_frame, text="📂 Load Macro", width=18, command=self.load_macro)
        self.load_btn.grid(row=1, column=1, padx=5, pady=5)

        # Options
        opt_frame = tk.LabelFrame(self.root, text="Playback Options", padx=10, pady=10)
        opt_frame.pack(fill="x", padx=15, pady=10)

        tk.Label(opt_frame, text="Repeat:").grid(row=0, column=0, sticky="w")
        self.repeat_var = tk.IntVar(value=1)
        tk.Spinbox(opt_frame, from_=1, to=999, width=6, textvariable=self.repeat_var).grid(row=0, column=1, sticky="w")

        tk.Label(opt_frame, text="Speed:").grid(row=1, column=0, sticky="w")
        self.speed_var = tk.DoubleVar(value=1.0)
        tk.Spinbox(opt_frame, from_=0.1, to=5.0, increment=0.1, width=6,
                   textvariable=self.speed_var).grid(row=1, column=1, sticky="w")

        self.event_count_var = tk.StringVar(value="Recorded events: 0")
        tk.Label(self.root, textvariable=self.event_count_var).pack(pady=(5, 0))

        self.cursor_pos_var = tk.StringVar(value="Cursor: (—, —)")
        tk.Label(self.root, textvariable=self.cursor_pos_var, fg="gray").pack(pady=(2, 0))
        self._poll_cursor_position()

        # Global hotkeys panel
        hk_frame = tk.LabelFrame(self.root, text="Assign Hotkeys", padx=10, pady=10)
        hk_frame.pack(fill="x", padx=15, pady=5)

        tk.Label(hk_frame, text="Start / Stop Recording:").grid(row=0, column=0, sticky="w")
        tk.Entry(hk_frame, width=14, textvariable=self.record_hotkey_var).grid(row=0, column=1, padx=5)

        tk.Label(hk_frame, text="Start / Stop Play:").grid(row=1, column=0, sticky="w")
        tk.Entry(hk_frame, width=14, textvariable=self.play_hotkey_var).grid(row=1, column=1, padx=5)

        tk.Button(hk_frame, text="Apply", command=self.apply_hotkeys).grid(row=0, column=2, rowspan=2, padx=8)

        self.hotkey_status_var = tk.StringVar(
            value=f"Active: Record={self.record_hotkey_var.get()}  Play={self.play_hotkey_var.get()}"
        )
        tk.Label(hk_frame, textvariable=self.hotkey_status_var, fg="gray",
                 font=("Segoe UI", 8)).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        info = tk.Label(self.root, fg="gray", wraplength=380, justify="left",
                         text=".")
        info.pack(padx=15, pady=10)

        copyright_label = tk.Label(self.root, text="© Mendukusai. All rights reserved.", fg="gray", font=("Segoe UI", 7))
        copyright_label.pack(pady=(0, 5))

    def _poll_cursor_position(self):
        try:
            x, y = self.recorder.mouse_ctrl.position
            self.cursor_pos_var.set(f"Cursor: ({x}, {y})")
        except Exception:
            pass
        self.root.after(100, self._poll_cursor_position)

    def toggle_recording(self):
        if self.recorder.playing:
            messagebox.showinfo("Busy", "Can't start recording while a macro is playing.")
            return

        if not self.recorder.recording:
            self.recorder.start_recording()
            self.record_btn.config(text="■ Stop Recording", bg="#c0392b")
            self.play_btn.config(state="disabled")
            self.save_btn.config(state="disabled")
            self.load_btn.config(state="disabled")
            self.show_mini_mode()
            self._poll_recording()
        else:
            self.recorder.stop_recording()
            self.hide_mini_mode()
            self._recording_finished()

    def _poll_recording(self):
        if self.recorder.recording:
            self.event_count_var.set(f"Recorded events: {len(self.recorder.events)}")
            self.root.after(150, self._poll_recording)
        else:
            self._recording_finished()

    def _recording_finished(self):
        self.record_btn.config(text="● Start Recording", bg="#e74c3c")
        self.play_btn.config(state="normal")
        if not self.recorder.playing:
            self.save_btn.config(state="normal")
            self.load_btn.config(state="normal")
        self.event_count_var.set(f"Recorded events: {len(self.recorder.events)}")

    def toggle_play(self):
        if self.recorder.playing:
            self._play_stop_flag = True
            return

        if self.recorder.recording:
            messagebox.showinfo("Busy", "Can't play a macro while recording is active.")
            return

        if not self.recorder.events:
            messagebox.showinfo("No macro", "Record or load a macro first.")
            return

        repeat = max(1, self.repeat_var.get())
        speed = max(0.1, self.speed_var.get())

        self._play_stop_flag = False
        self.play_btn.config(text="■ Stop", bg="#c0392b")
        self.record_btn.config(state="disabled")
        self.save_btn.config(state="disabled")
        self.load_btn.config(state="disabled")
        self.show_mini_mode_play()

        def run():
            self.recorder.play(repeat=repeat, speed=speed,
                                stop_flag=lambda: self._play_stop_flag)
            self.root.after(0, self._play_finished)

        self._play_thread = threading.Thread(target=run, daemon=True)
        self._play_thread.start()

    def _play_finished(self):
        self.play_btn.config(text="▶ Play", bg="#2ecc71")
        self.record_btn.config(state="normal")
        if not self.recorder.recording:
            self.save_btn.config(state="normal")
            self.load_btn.config(state="normal")
        self.hide_mini_mode_play()

    def save_macro(self):
        if not self.recorder.events:
            messagebox.showinfo("No macro", "Nothing to save yet.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                             filetypes=[("Macro JSON", "*.json")])
        if path:
            self.recorder.save(path)
            messagebox.showinfo("Saved", f"Macro saved to {path}")

    def load_macro(self):
        path = filedialog.askopenfilename(filetypes=[("Macro JSON", "*.json")])
        if path:
            try:
                self.recorder.load(path)
                self.event_count_var.set(f"Recorded events: {len(self.recorder.events)}")
                messagebox.showinfo("Loaded", f"Loaded {len(self.recorder.events)} events from {path}")
            except Exception as e:
                messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    icon_ico_path = app_dir / "icon.ico"

    if icon_ico_path.exists():
        try:
            root.iconbitmap(default=str(icon_ico_path))
        except Exception as e:
            print(f"Warning: could not set native icon bitmap from {icon_ico_path}: {e}")

    app = MacroApp(root)
    root.mainloop()
