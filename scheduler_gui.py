import contextlib
from copy import error
import io
import shutil
import subprocess
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext
from datetime import datetime

import app


PROJECT_ROOT = Path(__file__).parent
RIDE_TIMES_FOLDER = PROJECT_ROOT / "ride_times"
CLASS_SCHEDULES_FOLDER = PROJECT_ROOT / "class_schedules"
OUTPUT_FOLDER = PROJECT_ROOT / "output"
RIDERS_FILE = PROJECT_ROOT / "riders.txt"
ARCHIVE_FOLDER = PROJECT_ROOT / "archive"


class HorseShowSchedulerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Horse Show Scheduler")
        self.root.geometry("1000x850")

        self.ride_time_pdf = tk.StringVar()
        self.ride_time_url = tk.StringVar()
        self.class_schedule_pdf = tk.StringVar()
        self.class_schedule_url = tk.StringVar()
        self.skip_arena_source = tk.BooleanVar(value=False)
        self.show_name = tk.StringVar()
        self.show_platform = tk.StringVar(value="HorseShowOffice")
        self.rider_search = tk.StringVar()

        self.class_map = {}
        self.ride_time_class_map = {}
        self.class_schedule_class_map = {}
        self.filtered_class_codes = []
        self.used_class_codes = set()
        self.missing_class_codes = []
        self.class_search = tk.StringVar()
        self.selected_class_code = tk.StringVar()
        self.selected_class_name = tk.StringVar()

        self.schedule_generated = False
        self.ride_time_source = "pdf"
        self.pdf_fallback_visible = False
        self.available_riders = []
        self.filtered_available_riders = []
        self.ride_time_lines = []
        self.hso_rider_links = {}
        self.hso_selected_rides = []
        self.rider_ride_counts = {}
        self.trackpad_scroll_delta = 0
        self.widget_scroll_deltas = {}
        self.trackpad_scroll_threshold = 8
        self.global_scroll_bindings_installed = False

        self.show_name.trace_add("write", lambda *args: self.update_checklist())
        self.show_platform.trace_add("write", lambda *args: self.on_platform_changed())
        self.ride_time_pdf.trace_add("write", lambda *args: self.on_ride_pdf_changed())
        self.ride_time_url.trace_add("write", lambda *args: self.on_ride_url_changed())
        self.class_schedule_pdf.trace_add("write", lambda *args: self.on_class_pdf_changed())
        self.class_schedule_url.trace_add("write", lambda *args: self.on_class_url_changed())
        self.skip_arena_source.trace_add("write", lambda *args: self.update_checklist())
        self.rider_search.trace_add("write", lambda *args: self.filter_available_riders())
        self.class_search.trace_add("write", lambda *args: self.filter_class_map())

        self.build_interface()
        self.load_existing_riders()
        self.update_checklist()

    def selected_platform_key(self):
        platform = self.show_platform.get()

        if platform == "Equestrian Hub":
            return "equestrianhub"

        if platform == "FoxVillage":
            return "foxvillage"

        return "horseshowoffice"

    def selected_platform_name(self):
        platform_names = {
            "equestrianhub": "Equestrian Hub",
            "foxvillage": "FoxVillage",
            "horseshowoffice": "HorseShowOffice",
        }
        return platform_names.get(self.selected_platform_key(), "HorseShowOffice")

    def platform_requires_arena_source(self):
        return self.selected_platform_key() == "horseshowoffice"

    def ride_url_help_text(self):
        platform = self.selected_platform_key()

        if platform == "equestrianhub":
            return (
                "Use the Equestrian Hub show page URL.\n"
                "Example: https://equestrian-hub.com/show/274044"
            )

        if platform == "foxvillage":
            return (
                "Use the FoxVillage show page URL.\n"
                "Example: https://www.foxvillage.com/show?id=11741"
            )

        return (
            "Use the HorseShowOffice Ride Times Lookup URL.\n"
            "Example: https://www.horseshowoffice.com/hso/ridetimes.asp?s=5298&o=50"
        )

    def update_ride_url_guidance(self):
        if hasattr(self, "ride_url_label"):
            if self.selected_platform_key() == "equestrianhub":
                self.ride_url_label.config(text="Equestrian Hub URL:")
            elif self.selected_platform_key() == "foxvillage":
                self.ride_url_label.config(text="FoxVillage Show URL:")
            else:
                self.ride_url_label.config(text="Ride Times Lookup URL:")

        if hasattr(self, "ride_url_help_label"):
            self.ride_url_help_label.config(text=self.ride_url_help_text())

    def on_platform_changed(self):
        self.update_ride_url_guidance()
        self.ride_time_url.set("")
        self.class_schedule_url.set("")
        self.class_schedule_pdf.set("")
        self.clear_ride_time_data()
        self.clear_class_data()
        self.update_checklist()

    def on_ride_pdf_changed(self):
        if not self.ride_time_pdf.get().strip() and self.ride_time_source == "pdf":
            self.clear_ride_time_data()

        self.update_checklist()

    def on_ride_url_changed(self):
        if not self.ride_time_url.get().strip() and self.ride_time_source == "url":
            self.clear_ride_time_data()

        self.update_checklist()

    def on_class_pdf_changed(self):
        if not self.class_schedule_pdf.get().strip():
            self.clear_class_data()

        self.update_checklist()

    def on_class_url_changed(self):
        if self.class_schedule_url.get().strip():
            if self.class_schedule_pdf.get().strip():
                self.class_schedule_pdf.set("")
            self.clear_class_data()
        else:
            self.clear_class_data()

        self.update_checklist()

    def create_scrollable_container(self):
        container = tk.Frame(self.root)
        container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(container, takefocus=1)
        canvas = self.canvas

        scrollbar = tk.Scrollbar(
            container,
            orient="vertical",
            command=canvas.yview
        )

        self.main_frame = tk.Frame(canvas)

        canvas_window = canvas.create_window(
            (0, 0),
            window=self.main_frame,
            anchor="nw"
        )

        def update_scroll_region(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_main_frame(event):
            canvas.itemconfig(canvas_window, width=event.width)

        self.main_frame.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", resize_main_frame)

        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.root.bind("<FocusIn>", self.focus_scroll_area, add="+")
        self.root.bind("<Enter>", self.focus_scroll_area, add="+")
        container.bind("<Enter>", self.focus_scroll_area, add="+")
        self.main_frame.bind("<Enter>", self.focus_scroll_area, add="+")
        canvas.bind("<Enter>", self.focus_scroll_area, add="+")

    def should_preserve_widget_focus(self, widget):
        return isinstance(widget, (tk.Entry, tk.Listbox, tk.Text))

    def focus_scroll_area(self, event=None):
        if event is not None and self.should_preserve_widget_focus(event.widget):
            return

        focused_widget = self.root.focus_get()

        if focused_widget is not None and self.should_preserve_widget_focus(focused_widget):
            return

        if hasattr(self, "canvas"):
            self.canvas.focus_force()

    def scroll_main_canvas(self, event):
        delta = getattr(event, "delta", 0)

        if not delta:
            return None

        if abs(delta) >= 120:
            scroll_units = -int(delta / 120)
        else:
            self.trackpad_scroll_delta += delta

            if abs(self.trackpad_scroll_delta) < self.trackpad_scroll_threshold:
                return "break"

            threshold_steps = int(
                self.trackpad_scroll_delta / self.trackpad_scroll_threshold
            )
            self.trackpad_scroll_delta -= (
                threshold_steps * self.trackpad_scroll_threshold
            )
            scroll_units = -threshold_steps

        self.canvas.yview_scroll(scroll_units, "units")
        return "break"

    def scroll_main_canvas_up(self, event):
        self.canvas.yview_scroll(-1, "units")
        return "break"

    def scroll_main_canvas_down(self, event):
        self.canvas.yview_scroll(1, "units")
        return "break"

    def scroll_widget(self, event, widget):
        delta = getattr(event, "delta", 0)

        if not delta:
            return None

        if abs(delta) >= 120:
            scroll_units = -int(delta / 120)
        else:
            widget_key = str(widget)
            current_delta = self.widget_scroll_deltas.get(widget_key, 0) + delta

            if abs(current_delta) < self.trackpad_scroll_threshold:
                self.widget_scroll_deltas[widget_key] = current_delta
                return "break"

            threshold_steps = int(current_delta / self.trackpad_scroll_threshold)
            self.widget_scroll_deltas[widget_key] = (
                current_delta - (threshold_steps * self.trackpad_scroll_threshold)
            )
            scroll_units = -threshold_steps

        widget.yview_scroll(scroll_units, "units")
        return "break"

    def scroll_widget_up(self, event, widget):
        widget.yview_scroll(-1, "units")
        return "break"

    def scroll_widget_down(self, event, widget):
        widget.yview_scroll(1, "units")
        return "break"

    def scroll_target_from_event(self, event):
        target = getattr(event, "widget", None)

        try:
            containing = event.widget.winfo_containing(event.x_root, event.y_root)
            if containing is not None:
                target = containing
        except tk.TclError:
            pass

        while target is not None:
            if isinstance(target, (tk.Listbox, tk.Text)):
                return target

            if target in (self.canvas, self.main_frame):
                break

            target = getattr(target, "master", None)

        return self.canvas

    def dispatch_scroll_event(self, event):
        target = self.scroll_target_from_event(event)

        if target == self.canvas:
            return self.scroll_main_canvas(event)

        return self.scroll_widget(event, target)

    def dispatch_scroll_up(self, event):
        target = self.scroll_target_from_event(event)

        if target == self.canvas:
            return self.scroll_main_canvas_up(event)

        return self.scroll_widget_up(event, target)

    def dispatch_scroll_down(self, event):
        target = self.scroll_target_from_event(event)

        if target == self.canvas:
            return self.scroll_main_canvas_down(event)

        return self.scroll_widget_down(event, target)

    def scroll_main_canvas_key(self, event):
        key_scroll_units = {
            "Up": -3,
            "Down": 3,
            "Prior": -10,
            "Next": 10,
        }

        scroll_units = key_scroll_units.get(event.keysym)

        if scroll_units is None:
            return None

        self.canvas.yview_scroll(scroll_units, "units")
        return "break"

    def install_scroll_bindings(self, widget):
        wheel_events = (
            "<MouseWheel>",
            "<Shift-MouseWheel>",
            "<Option-MouseWheel>",
            "<Command-MouseWheel>",
            "<Control-MouseWheel>",
        )

        for wheel_event in wheel_events:
            widget.bind(wheel_event, self.dispatch_scroll_event, add="+")

        if isinstance(widget, (tk.Listbox, tk.Text)):
            widget.bind(
                "<Enter>",
                lambda event, target=widget: target.focus_set(),
                add="+"
            )
            widget.bind("<Button-4>", self.dispatch_scroll_up, add="+")
            widget.bind("<Button-5>", self.dispatch_scroll_down, add="+")
        elif isinstance(widget, tk.Entry):
            widget.bind("<Button-4>", self.dispatch_scroll_up, add="+")
            widget.bind("<Button-5>", self.dispatch_scroll_down, add="+")
        else:
            widget.bind("<Button-4>", self.dispatch_scroll_up, add="+")
            widget.bind("<Button-5>", self.dispatch_scroll_down, add="+")
            widget.bind("<Enter>", self.focus_scroll_area, add="+")
            widget.bind("<Up>", self.scroll_main_canvas_key, add="+")
            widget.bind("<Down>", self.scroll_main_canvas_key, add="+")
            widget.bind("<Prior>", self.scroll_main_canvas_key, add="+")
            widget.bind("<Next>", self.scroll_main_canvas_key, add="+")

        if not self.global_scroll_bindings_installed:
            for wheel_event in wheel_events:
                self.root.bind_class(
                    "all",
                    wheel_event,
                    self.dispatch_scroll_event,
                    add="+"
                )

            self.root.bind_class("all", "<Button-4>", self.dispatch_scroll_up, add="+")
            self.root.bind_class("all", "<Button-5>", self.dispatch_scroll_down, add="+")
            self.root.bind_class("all", "<Up>", self.scroll_main_canvas_key, add="+")
            self.root.bind_class("all", "<Down>", self.scroll_main_canvas_key, add="+")
            self.root.bind_class("all", "<Prior>", self.scroll_main_canvas_key, add="+")
            self.root.bind_class("all", "<Next>", self.scroll_main_canvas_key, add="+")
            self.global_scroll_bindings_installed = True

        for child in widget.winfo_children():
            self.install_scroll_bindings(child)

    def set_status_icon(self, label, is_complete, complete_text="✅", incomplete_text="⬜"):
        if is_complete:
            label.config(text=complete_text, fg="green")
        else:
            label.config(text=incomplete_text, fg="gray")

    def create_prompt_entry(self, parent, textvariable, prompt, **entry_options):
        entry = tk.Entry(parent, **entry_options)
        normal_fg = entry.cget("fg")
        prompt_fg = "gray"
        state = {
            "showing_prompt": False,
            "syncing": False,
        }

        def show_prompt():
            if textvariable.get():
                return

            state["showing_prompt"] = True
            entry.config(fg=prompt_fg)
            entry.delete(0, tk.END)
            entry.insert(0, prompt)

        def hide_prompt():
            if not state["showing_prompt"]:
                return

            state["showing_prompt"] = False
            entry.config(fg=normal_fg)
            entry.delete(0, tk.END)

        def sync_from_variable(*args):
            if state["syncing"]:
                return

            value = textvariable.get()

            if not value:
                if entry.focus_get() == entry:
                    hide_prompt()
                else:
                    show_prompt()
                return

            state["showing_prompt"] = False
            entry.config(fg=normal_fg)
            entry.delete(0, tk.END)
            entry.insert(0, value)

        def sync_to_variable(event=None):
            if state["showing_prompt"]:
                return

            state["syncing"] = True
            textvariable.set(entry.get())
            state["syncing"] = False

        def on_focus_in(event):
            hide_prompt()

        def on_focus_out(event):
            sync_to_variable()

            if not textvariable.get():
                show_prompt()

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        entry.bind("<KeyRelease>", sync_to_variable)
        textvariable.trace_add("write", sync_from_variable)
        show_prompt()

        return entry

    def toggle_pdf_fallbacks(self):
        self.pdf_fallback_visible = not self.pdf_fallback_visible
        self.update_pdf_fallback_visibility()

    def update_pdf_fallback_visibility(self):
        if not hasattr(self, "ride_frame") or not hasattr(self, "class_frame"):
            return

        self.ride_frame.pack_forget()
        self.class_frame.pack_forget()

        if self.pdf_fallback_visible:
            self.ride_frame.pack(fill="x", padx=20, pady=(0, 5), before=self.rider_search_frame)
            self.class_frame.pack(fill="x", padx=20, pady=(0, 8), before=self.checklist_label.master)
            self.pdf_fallback_button.config(text="Hide PDF Fallbacks")
        else:
            self.pdf_fallback_button.config(text="URL Unavailable?")

    def build_interface(self):
        self.create_scrollable_container()

        title = tk.Label(
            self.main_frame,
            text="Horse Show Scheduler",
            font=("Arial", 20, "bold")
        )
        title.pack(pady=10)
        
        checklist_frame = tk.LabelFrame(
            self.main_frame,
            text="Show Setup Checklist",
            padx=10,
            pady=8
        )
        checklist_frame.pack(fill="x", padx=20, pady=5)

        self.checklist_label = tk.Label(
            checklist_frame,
            text="",
            justify="left",
            anchor="w"
        )
        self.checklist_label.pack(fill="x")

        show_frame = tk.Frame(self.main_frame)
        show_frame.pack(fill="x", padx=20, pady=5)

        tk.Label(show_frame, text="Show Name:", width=18, anchor="w").pack(side="left")
        self.create_prompt_entry(
            show_frame,
            self.show_name,
            "Enter show name for output files"
        ).pack(side="left", fill="x", expand=True)

        self.show_name_status = tk.Label(show_frame, text="⬜", width=4)
        self.show_name_status.pack(side="left", padx=5)

        platform_frame = tk.Frame(self.main_frame)
        platform_frame.pack(fill="x", padx=20, pady=5)

        tk.Label(platform_frame, text="Show Platform:", width=18, anchor="w").pack(side="left")
        tk.OptionMenu(
            platform_frame,
            self.show_platform,
            "HorseShowOffice",
            "FoxVillage",
            "Equestrian Hub"
        ).pack(side="left")

        classes_header_frame = tk.Frame(self.main_frame)
        classes_header_frame.pack(fill="x", padx=20, pady=(15, 3))

        tk.Label(
            classes_header_frame,
            text="Classes:",
            anchor="w",
            font=("Arial", 12, "bold")
        ).pack(side="left")

        self.class_defs_status = tk.Label(
            classes_header_frame,
            text="⬜ No class definitions loaded",
            anchor="w",
            fg="gray"
        )
        self.class_defs_status.pack(side="left", padx=10)

        tk.Button(
            classes_header_frame,
            text="Load Classes for Selected Riders",
            command=self.load_classes_for_selected_riders
        ).pack(side="right")

        class_url_frame = tk.Frame(self.main_frame)
        class_url_frame.pack(fill="x", padx=20, pady=5)

        tk.Label(class_url_frame, text="Arena / Ring URL:", width=18, anchor="w").pack(side="left")
        self.create_prompt_entry(
            class_url_frame,
            self.class_schedule_url,
            "Paste Ride Schedule PDF URL so arenas/rings can populate"
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            class_url_frame,
            text="Load",
            command=self.load_classes_from_url
        ).pack(side="left", padx=5)

        self.class_url_status = tk.Label(class_url_frame, text="⬜", width=4)
        self.class_url_status.pack(side="left", padx=5)

        tk.Checkbutton(
            class_url_frame,
            text="One ring / skip arena URL",
            variable=self.skip_arena_source
        ).pack(side="left", padx=5)

        class_frame = tk.Frame(self.main_frame)
        class_frame.pack(fill="x", padx=20, pady=5)
        self.class_frame = class_frame

        tk.Label(class_frame, text="PDF Fallback:", width=18, anchor="w").pack(side="left")
        self.create_prompt_entry(
            class_frame,
            self.class_schedule_pdf,
            "Choose Ride Schedule PDF if URL import is unavailable"
        ).pack(side="left", fill="x", expand=True)
        tk.Button(class_frame, text="Choose", command=self.choose_class_schedule_pdf).pack(side="left", padx=5)

        self.class_pdf_status = tk.Label(class_frame, text="⬜", width=4)
        self.class_pdf_status.pack(side="left", padx=5)
        
        class_defs_frame = tk.LabelFrame(
            self.main_frame,
            text="Class Definitions",
            padx=10,
            pady=8
        )
        class_defs_frame.pack(fill="both", padx=20, pady=8)

        class_search_frame = tk.Frame(class_defs_frame)
        class_search_frame.pack(fill="x", pady=3)

        tk.Label(class_search_frame, text="Search Class # or Name:").pack(side="left")
        self.create_prompt_entry(
            class_search_frame,
            self.class_search,
            "Type class number or class name"
        ).pack(side="left", fill="x", expand=True, padx=5)

        class_body_frame = tk.Frame(class_defs_frame)
        class_body_frame.pack(fill="both", expand=True)

        self.class_listbox = tk.Listbox(
            class_body_frame,
            height=7,
            selectmode=tk.SINGLE
        )
        self.class_listbox.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.class_listbox.bind(
            "<<ListboxSelect>>",
            self.on_class_selected
        )

        class_edit_frame = tk.Frame(class_body_frame)
        class_edit_frame.pack(side="left", fill="both", expand=True)

        tk.Label(class_edit_frame, text="Class #:").pack(anchor="w")
        self.create_prompt_entry(
            class_edit_frame,
            self.selected_class_code,
            "Class number/code"
        ).pack(fill="x", pady=(0, 5))

        tk.Label(class_edit_frame, text="Class Name:").pack(anchor="w")
        self.create_prompt_entry(
            class_edit_frame,
            self.selected_class_name,
            "Class name to save"
        ).pack(fill="x", pady=(0, 5))

        class_button_frame = tk.Frame(class_edit_frame)
        class_button_frame.pack(fill="x", pady=5)

        tk.Button(
            class_button_frame,
            text="Add / Update Class",
            command=self.add_or_update_class
        ).pack(side="left", padx=3)

        tk.Button(
            class_button_frame,
            text="Remove Selected Class",
            command=self.remove_selected_class
        ).pack(side="left", padx=3)

        riders_header_frame = tk.Frame(self.main_frame)
        riders_header_frame.pack(fill="x", padx=20, pady=(15, 3))

        tk.Label(
            riders_header_frame,
            text="Riders:",
            anchor="w",
            font=("Arial", 12, "bold")
        ).pack(side="left")

        self.riders_status = tk.Label(
            riders_header_frame,
            text="⬜ No riders selected",
            anchor="w",
            fg="gray"
        )
        self.riders_status.pack(side="left", padx=10)

        self.pdf_fallback_button = tk.Button(
            riders_header_frame,
            text="URL Unavailable?",
            command=self.toggle_pdf_fallbacks
        )
        self.pdf_fallback_button.pack(side="right")

        ride_url_frame = tk.Frame(self.main_frame)
        ride_url_frame.pack(fill="x", padx=20, pady=5)

        self.ride_url_label = tk.Label(
            ride_url_frame,
            text="Ride Times Lookup URL:",
            width=18,
            anchor="w"
        )
        self.ride_url_label.pack(side="left")
        self.create_prompt_entry(
            ride_url_frame,
            self.ride_time_url,
            "Paste the selected platform's show or ride-time URL"
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            ride_url_frame,
            text="Load Riders",
            command=self.load_riders_from_url
        ).pack(side="left", padx=5)

        self.ride_url_status = tk.Label(ride_url_frame, text="⬜", width=4)
        self.ride_url_status.pack(side="left", padx=5)

        self.ride_url_help_label = tk.Label(
            self.main_frame,
            text=self.ride_url_help_text(),
            anchor="w",
            justify="left",
            fg="gray",
            wraplength=750
        )
        self.ride_url_help_label.pack(fill="x", padx=205, pady=(0, 5))

        ride_frame = tk.Frame(self.main_frame)
        ride_frame.pack(fill="x", padx=20, pady=5)
        self.ride_frame = ride_frame

        tk.Label(ride_frame, text="PDF Fallback:", width=18, anchor="w").pack(side="left")
        self.create_prompt_entry(
            ride_frame,
            self.ride_time_pdf,
            "Choose ride-time PDF if URL import is unavailable"
        ).pack(side="left", fill="x", expand=True)
        tk.Button(ride_frame, text="Choose", command=self.choose_ride_time_pdf).pack(side="left", padx=5)

        self.ride_pdf_status = tk.Label(ride_frame, text="⬜", width=4)
        self.ride_pdf_status.pack(side="left", padx=5)

        rider_search_frame = tk.Frame(self.main_frame)
        rider_search_frame.pack(fill="x", padx=20, pady=5)
        self.rider_search_frame = rider_search_frame

        tk.Label(
            rider_search_frame,
            text="Search Possible Riders:"
        ).pack(side="left", padx=(0, 5))

        self.create_prompt_entry(
            rider_search_frame,
            self.rider_search,
            "Type rider name to filter"
        ).pack(side="left", fill="x", expand=True)

        rider_lists_frame = tk.Frame(self.main_frame)
        rider_lists_frame.pack(fill="both", expand=False, padx=20, pady=5)

        available_frame = tk.LabelFrame(
            rider_lists_frame,
            text="Possible Riders"
        )
        available_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.available_riders_listbox = tk.Listbox(
            available_frame,
            height=9,
            selectmode=tk.EXTENDED
        )
        self.available_riders_listbox.pack(fill="both", expand=True, padx=5, pady=5)

        self.available_riders_listbox.bind(
            "<Double-Button-1>",
            self.add_double_clicked_rider
        )

        rider_button_frame = tk.Frame(rider_lists_frame)
        rider_button_frame.pack(side="left", fill="y", padx=4)

        tk.Button(
            rider_button_frame,
            text="Add →",
            command=self.add_selected_available_riders
        ).pack(fill="x", pady=(28, 5))

        tk.Button(
            rider_button_frame,
            text="← Remove",
            command=self.remove_selected_riders
        ).pack(fill="x", pady=5)

        tk.Button(
            rider_button_frame,
            text="Clear",
            command=self.clear_all_riders
        ).pack(fill="x", pady=5)

        selected_frame = tk.LabelFrame(
            rider_lists_frame,
            text="Selected Riders for Schedule (Ride Counts)"
        )
        selected_frame.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.riders_listbox = tk.Listbox(
            selected_frame,
            height=9,
            selectmode=tk.EXTENDED
        )
        self.riders_listbox.pack(fill="both", expand=True, padx=5, pady=5)

        self.riders_listbox.bind(
            "<Double-Button-1>",
            self.remove_double_clicked_rider
        )

        for class_section in (
            checklist_frame,
            classes_header_frame,
            class_url_frame,
            class_frame,
            class_defs_frame,
        ):
            class_section.pack_forget()

        classes_header_frame.pack(fill="x", padx=20, pady=(15, 3))
        class_defs_frame.pack(fill="both", padx=20, pady=8)
        class_url_frame.pack(fill="x", padx=20, pady=(0, 5))
        checklist_frame.pack(fill="x", padx=20, pady=5)
        self.update_pdf_fallback_visibility()

        button_frame = tk.Frame(self.main_frame)
        button_frame.pack(fill="x", padx=20, pady=10)

        self.generate_button = tk.Button(
            button_frame,
            text="Generate Schedule",
            command=self.generate_schedule,
            height=2,
            bg="#d9ead3",
            disabledforeground="#4a4a4a"
        )
        self.generate_button.pack(side="left", padx=5)

        self.open_output_button = tk.Button(
            button_frame,
            text="Open Output Folder",
            command=self.open_output_folder,
            height=2,
            disabledforeground="#4a4a4a"
        )
        self.open_output_button.pack(side="left", padx=5)

        self.clear_archive_button = tk.Button(
            button_frame,
            text="Clear Ride Source",
            command=self.clear_or_archive_current_show,
            height=2,
            disabledforeground="#4a4a4a"
        )
        self.clear_archive_button.pack(side="left", padx=5)

        output_label = tk.Label(
            self.main_frame,
            text="Status / Validation Output:",
            anchor="w"
        )
        output_label.pack(fill="x", padx=20, pady=(10, 3))

        self.output_text = scrolledtext.ScrolledText(self.main_frame, height=18)
        self.output_text.pack(fill="both", expand=True, padx=20, pady=5)

        self.install_scroll_bindings(self.root)
        self.root.after(100, self.focus_scroll_area)

    def load_classes_from_pdf(self):
        class_pdf = Path(self.class_schedule_pdf.get())

        if not class_pdf.exists():
            messagebox.showerror(
                "Missing Ride Schedule PDF",
                "Please choose a valid ride schedule PDF first. "
                "This is usually the PDF named Ride Schedule on the show website."
            )
            return

        try:
            # Clear the class_schedules folder and copy selected PDF there.
            self.clear_folder_files(CLASS_SCHEDULES_FOLDER)
            shutil.copy2(class_pdf, CLASS_SCHEDULES_FOLDER / class_pdf.name)

            self.class_schedule_class_map = app.build_class_map()
            self.rebuild_class_map()
            self.update_class_review_state()

            self.refresh_class_listbox()

            messagebox.showinfo(
                "Classes Loaded",
                f"Loaded {len(self.class_map)} class definitions from the ride schedule PDF."
            )

            self.update_checklist()

        except Exception as error:
            messagebox.showerror(
                "Could Not Read Classes",
                f"The app could not read class definitions from the selected PDF.\n\n{error}"
            )

    def load_classes_from_url(self):
        class_url = self.class_schedule_url.get().strip()

        if not class_url:
            messagebox.showerror(
                "Missing Ride Schedule URL",
                "Paste the Ride Schedule PDF URL first."
            )
            return

        try:
            download_path = (
                Path(tempfile.gettempdir())
                / "horse_show_scheduler_ride_schedule.pdf"
            )
            app.download_url_to_file(class_url, download_path)

            self.clear_folder_files(CLASS_SCHEDULES_FOLDER)
            shutil.copy2(download_path, CLASS_SCHEDULES_FOLDER / download_path.name)

            self.class_schedule_pdf.set(str(download_path))
            self.class_schedule_class_map = app.build_class_map()
            self.rebuild_class_map()
            self.update_class_review_state()
            self.refresh_class_listbox()

            messagebox.showinfo(
                "Ride Schedule Loaded",
                f"Loaded {len(self.class_schedule_class_map)} class definition(s) "
                "from the Ride Schedule URL for arena/ring details."
            )

            self.update_checklist()

        except Exception as error:
            messagebox.showerror(
                "Could Not Load Ride Schedule",
                f"The app could not load the Ride Schedule PDF from the URL.\n\n{error}"
            )

    def infer_class_map_from_ride_time_lines(self, lines):
        riders = app.extract_riders_from_lines(lines)
        rides = app.parse_rides(lines, riders, {})
        class_names_by_code = {}

        for ride in rides:
            class_code = ride.get("class", "")
            class_name = ride.get("class_name", "")

            if not class_code or not class_name:
                continue

            names = class_names_by_code.setdefault(class_code, {})
            names[class_name] = names.get(class_name, 0) + 1

        inferred_class_map = {}

        for class_code, names in class_names_by_code.items():
            inferred_class_map[class_code] = sorted(
                names.items(),
                key=lambda item: (-item[1], len(item[0]), item[0].lower())
            )[0][0]

        return inferred_class_map

    def rebuild_class_map(self):
        self.class_map = {
            **self.ride_time_class_map,
            **self.class_schedule_class_map,
        }
        self.filtered_class_codes = sorted(self.class_map.keys())

    def refresh_class_listbox(self):
        if not hasattr(self, "class_listbox"):
            return

        self.update_class_review_state()
        self.class_listbox.delete(0, tk.END)

        missing_codes = [
            code for code in self.missing_class_codes
            if self.class_matches_search(code, "")
        ]

        for code in missing_codes:
            list_index = self.class_listbox.size()
            self.class_listbox.insert(
                tk.END,
                f"⚠ {code} — Missing class definition"
            )
            self.class_listbox.itemconfig(list_index, bg="#fff2cc")

        loaded_codes = [
            code for code in sorted(self.class_map.keys())
            if code not in self.missing_class_codes
            and self.class_matches_search(code, self.class_map.get(code, ""))
        ]

        for code in loaded_codes:
            class_name = self.class_map.get(code, "")
            self.class_listbox.insert(tk.END, f"{code} — {class_name}")

    def class_matches_search(self, code, class_name):
        search_text = self.class_search.get().strip().lower()
        class_name = class_name or ""

        if not search_text:
            return True

        return (
            search_text in code.lower()
            or search_text in class_name.lower()
            or (
                code in self.missing_class_codes
                and search_text in "missing class definition"
            )
        )

    def filter_class_map(self):
        if not hasattr(self, "class_listbox"):
            return

        self.refresh_class_listbox()

    def update_class_review_state(self):
        riders = self.get_rider_lines()

        if self.ride_time_source == "url":
            if not riders or not self.hso_selected_rides:
                self.used_class_codes = set()
                self.missing_class_codes = []
                self.update_class_defs_status()
                return

            selected_riders = set(riders)
            rides = [
                ride for ride in self.hso_selected_rides
                if ride.get("rider") in selected_riders
            ]
        elif not self.ride_time_lines or not riders:
            self.used_class_codes = set()
            self.missing_class_codes = []
            self.update_class_defs_status()
            return
        else:
            rides = app.parse_rides(
                self.ride_time_lines,
                riders,
                self.class_map
            )

        self.used_class_codes = {
            ride["class"]
            for ride in rides
            if ride.get("class")
        }
        self.missing_class_codes = sorted(
            code for code in self.used_class_codes
            if not self.class_map.get(code)
        )
        self.update_class_defs_status()

    def update_class_defs_status(self):
        if not hasattr(self, "class_defs_status"):
            return

        class_count = len(self.class_map)
        used_count = len(self.used_class_codes)
        missing_count = len(self.missing_class_codes)
        inferred_count = len(self.ride_time_class_map)
        schedule_count = len(self.class_schedule_class_map)
        ride_source_label = (
            "from URL"
            if self.ride_time_source == "url"
            else "from ride times"
        )

        if missing_count:
            self.class_defs_status.config(
                text=(
                    f"⚠ {missing_count} class definition(s) need review "
                    f"({class_count} loaded, {used_count} used by selected riders)"
                ),
                fg="#b45f06"
            )
        elif used_count:
            self.class_defs_status.config(
                text=(
                    f"✅ All selected-rider classes found "
                    f"({class_count} loaded, {used_count} used)"
                ),
                fg="green"
            )
        elif class_count:
            self.class_defs_status.config(
                text=(
                    f"✅ {class_count} class definition(s) loaded "
                    f"({inferred_count} {ride_source_label}"
                    f"{', ' + str(schedule_count) + ' from class schedule' if schedule_count else ''})"
                ),
                fg="green"
            )
        else:
            self.class_defs_status.config(
                text="⬜ No class definitions loaded",
                fg="gray"
            )

    def on_class_selected(self, event=None):
        selected_indices = list(self.class_listbox.curselection())

        if not selected_indices:
            return

        selected_text = self.class_listbox.get(selected_indices[0])

        if " — " not in selected_text:
            return

        code, class_name = selected_text.split(" — ", 1)
        code = code.replace("⚠", "").strip()

        if class_name == "Missing class definition":
            class_name = ""

        self.selected_class_code.set(code)
        self.selected_class_name.set(class_name)

    def add_or_update_class(self):
        code = self.selected_class_code.get().strip()
        class_name = self.selected_class_name.get().strip()

        if not code:
            messagebox.showinfo(
                "Missing Class #",
                "Enter a class number/code first."
            )
            return

        if not class_name:
            messagebox.showinfo(
                "Missing Class Name",
                "Enter a class name first."
            )
            return

        self.class_map[code] = class_name
        self.update_class_review_state()
        self.filter_class_map()

    def remove_selected_class(self):
        code = self.selected_class_code.get().strip()

        if not code:
            messagebox.showinfo(
                "No Class Selected",
                "Select a class first."
            )
            return

        if code not in self.class_map:
            messagebox.showinfo(
                "Class Not Found",
                f"{code} is not currently in the class list."
            )
            return

        confirm = messagebox.askyesno(
            "Remove Class",
            f"Remove this class definition?\n\n{code} — {self.class_map[code]}"
        )

        if not confirm:
            return

        del self.class_map[code]
        self.selected_class_code.set("")
        self.selected_class_name.set("")
        self.update_class_review_state()
        self.filter_class_map()

    def load_existing_riders(self):
        if RIDERS_FILE.exists():
            riders = [
                line.strip()
                for line in RIDERS_FILE.read_text().splitlines()
                if line.strip()
            ]

            self.set_rider_lines(riders)

    def load_riders_from_pdf(self):
        ride_pdf = Path(self.ride_time_pdf.get())

        if not ride_pdf.exists():
            messagebox.showerror(
                "Missing Ride-Time PDF",
                "Please choose a valid ride-time PDF first."
            )
            return

        try:
            # Temporarily read directly from the selected PDF.
            lines = []

            with app.pdfplumber.open(ride_pdf) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        lines.extend(text.split("\n"))

            self.ride_time_lines = lines
            self.available_riders = app.extract_riders_from_lines(lines)
            self.rider_ride_counts = self.count_rides_by_rider(lines)
            self.ride_time_class_map = self.infer_class_map_from_ride_time_lines(lines)
            self.ride_time_source = "pdf"
            self.hso_rider_links = {}
            self.ride_time_url.set("")
            self.rebuild_class_map()
            self.filtered_available_riders = self.available_riders[:]

            self.refresh_available_riders_listbox()
            self.refresh_selected_riders_listbox()
            self.refresh_class_listbox()

            messagebox.showinfo(
                "Riders Loaded",
                f"Found {len(self.available_riders)} possible riders in the ride-time PDF."
            )

            self.update_checklist()

        except Exception as error:
            messagebox.showerror(
                "Could Not Read Riders",
                f"The app could not read riders from the selected PDF.\n\n{error}"
            )

    def load_riders_from_url(self):
        ride_url = self.ride_time_url.get().strip()

        if not ride_url:
            messagebox.showerror(
                "Missing Show URL",
                f"Paste the URL for the selected show platform first.\n\n{self.ride_url_help_text()}"
            )
            return

        try:
            selected_platform = self.selected_platform_key()
            actual_platform = app.source_type_from_url(ride_url)

            if actual_platform != selected_platform:
                raise ValueError(
                    f"The selected platform is {self.selected_platform_name()}, "
                    f"but that URL looks like {actual_platform}."
                )

            self.hso_rider_links = app.fetch_rider_links_from_url(
                ride_url,
                selected_platform
            )

            if not self.hso_rider_links:
                raise ValueError(f"No riders were found at that {self.selected_platform_name()} URL.")

            self.available_riders = list(self.hso_rider_links.keys())
            self.filtered_available_riders = self.available_riders[:]
            self.rider_ride_counts = {}
            self.ride_time_lines = []
            self.hso_selected_rides = []
            self.ride_time_class_map = {}
            self.ride_time_source = "url"
            self.ride_time_pdf.set("")
            self.rebuild_class_map()

            self.refresh_available_riders_listbox()
            self.load_counts_for_selected_url_riders()
            self.refresh_selected_riders_listbox()
            self.refresh_class_listbox()

            messagebox.showinfo(
                "Riders Loaded",
                f"Found {len(self.available_riders)} possible riders from "
                f"{self.selected_platform_name()}."
            )

            self.update_checklist()

        except Exception as error:
            messagebox.showerror(
                "Could Not Load Riders",
                f"The app could not load riders from the URL.\n\n{error}"
            )

    def refresh_available_riders_listbox(self):
        self.available_riders_listbox.delete(0, tk.END)

        for rider in self.filtered_available_riders:
            self.available_riders_listbox.insert(
                tk.END,
                self.format_rider_with_count(rider)
            )

    def filter_available_riders(self):
        if not hasattr(self, "available_riders_listbox"):
            return

        search_text = self.rider_search.get().strip().lower()

        if not search_text:
            self.filtered_available_riders = self.available_riders[:]
        else:
            self.filtered_available_riders = [
                rider for rider in self.available_riders
                if search_text in rider.lower()
            ]

        self.refresh_available_riders_listbox()

    def count_rides_by_rider(self, lines):
        counts = {}
        current_rider = None

        for line in lines:
            line = line.strip()

            if app.rider_pattern.match(line):
                current_rider = line
                counts.setdefault(current_rider, 0)
                continue

            if current_rider and app.ride_pattern.match(line):
                counts[current_rider] = counts.get(current_rider, 0) + 1

        return counts

    def count_web_rides_by_rider(self, rides):
        counts = {}

        for ride in rides:
            rider = ride.get("rider")

            if rider:
                counts[rider] = counts.get(rider, 0) + 1

        return counts

    def apply_skipped_arena_source(self, rides):
        if not self.skip_arena_source.get():
            return rides

        for ride in rides:
            if not ride.get("arena_name"):
                ride["arena"] = "One Ring"
                ride["arena_number"] = "1"
                ride["arena_name"] = "One Ring"

        return rides

    def merge_hso_selected_rides(self, rides):
        existing_keys = {
            (
                ride.get("rider"),
                ride.get("day"),
                ride.get("time"),
                ride.get("class"),
                ride.get("horse"),
            )
            for ride in self.hso_selected_rides
        }

        for ride in rides:
            key = (
                ride.get("rider"),
                ride.get("day"),
                ride.get("time"),
                ride.get("class"),
                ride.get("horse"),
            )

            if key not in existing_keys:
                self.hso_selected_rides.append(ride)
                existing_keys.add(key)

    def load_counts_for_selected_url_riders(self):
        if self.ride_time_source != "url" or not self.hso_rider_links:
            return

        selected_riders = self.get_rider_lines()
        riders_missing_counts = [
            rider for rider in selected_riders
            if rider not in self.rider_ride_counts
        ]

        if not riders_missing_counts:
            return

        rides = app.fetch_rides_for_riders(
            self.hso_rider_links,
            riders_missing_counts
        )
        self.merge_hso_selected_rides(rides)
        for rider in riders_missing_counts:
            self.rider_ride_counts[rider] = 0
        self.rider_ride_counts.update(self.count_web_rides_by_rider(rides))
        self.refresh_selected_riders_listbox()

    def load_classes_for_selected_riders(self):
        riders = self.get_rider_lines()

        if not riders:
            messagebox.showinfo(
                "No Riders Selected",
                "Select riders before loading classes."
            )
            return

        if self.ride_time_source == "url":
            if not self.hso_rider_links:
                messagebox.showerror(
                    "Missing Show URL",
                    f"Load riders from a {self.selected_platform_name()} URL first."
                )
                return

            try:
                self.hso_selected_rides = app.fetch_rides_for_riders(
                    self.hso_rider_links,
                    riders
                )
                self.ride_time_class_map = app.class_map_from_rides(
                    self.hso_selected_rides
                )
                self.rider_ride_counts = {rider: 0 for rider in riders}
                self.rider_ride_counts.update(
                    self.count_web_rides_by_rider(self.hso_selected_rides)
                )
                self.rebuild_class_map()
                self.refresh_selected_riders_listbox()
                self.refresh_class_listbox()

                messagebox.showinfo(
                    "Classes Loaded",
                    f"Loaded {len(self.ride_time_class_map)} class definition(s) "
                    f"for {len(riders)} selected rider(s)."
                )

                self.update_checklist()

            except Exception as error:
                messagebox.showerror(
                    "Could Not Load Classes",
                    f"The app could not load classes for the selected riders.\n\n{error}"
                )

            return

        if self.ride_time_lines:
            self.ride_time_class_map = self.infer_class_map_from_ride_time_lines(
                self.ride_time_lines
            )
            self.rebuild_class_map()
            self.refresh_class_listbox()
            self.update_checklist()

    def format_rider_with_count(self, rider):
        count = self.rider_ride_counts.get(rider)

        if count is None:
            return rider

        if count == 0:
            return f"{rider} (no rides found)"

        ride_word = "ride" if count == 1 else "rides"
        return f"{rider} ({count} {ride_word})"

    def format_selected_rider(self, rider):
        return self.format_rider_with_count(rider)

    def clean_rider_text(self, rider_text):
        rider_text = rider_text.strip()

        if " (" not in rider_text or not rider_text.endswith(")"):
            return rider_text

        name, suffix = rider_text.rsplit(" (", 1)

        if (
            suffix.endswith(" ride)")
            or suffix.endswith(" rides)")
            or suffix == "no rides found)"
        ):
            return name.strip()

        return rider_text

    def clean_selected_rider_text(self, rider_text):
        return self.clean_rider_text(rider_text)

    def refresh_selected_riders_listbox(self):
        if not hasattr(self, "riders_listbox"):
            return

        selected_riders = self.get_rider_lines()

        self.riders_listbox.delete(0, tk.END)

        for rider in selected_riders:
            self.riders_listbox.insert(tk.END, self.format_selected_rider(rider))

    def clear_url_selected_class_data(self):
        if self.ride_time_source != "url":
            return

        self.ride_time_class_map = {}
        self.rebuild_class_map()

    def add_selected_available_riders(self):
        selected_indices = list(self.available_riders_listbox.curselection())

        if not selected_indices:
            messagebox.showinfo(
                "No Riders Selected",
                "Select one or more riders from the possible rider list first."
            )
            return

        selected_riders = [
            self.clean_rider_text(self.available_riders_listbox.get(index))
            for index in selected_indices
        ]

        current_riders = self.get_rider_lines()

        added_count = 0

        for rider in selected_riders:
            if rider not in current_riders:
                current_riders.append(rider)
                added_count += 1

        if added_count:
            self.clear_url_selected_class_data()

        self.set_rider_lines(current_riders)
        self.load_counts_for_selected_url_riders()
        self.refresh_class_listbox()
        self.update_checklist()

    def add_double_clicked_rider(self, event):
        selected_index = self.available_riders_listbox.nearest(event.y)

        if selected_index is None:
            return

        rider = self.clean_rider_text(
            self.available_riders_listbox.get(selected_index)
        )

        if not rider:
            return

        current_riders = self.get_rider_lines()

        if rider not in current_riders:
            current_riders.append(rider)
            self.clear_url_selected_class_data()
            self.set_rider_lines(current_riders)
            self.load_counts_for_selected_url_riders()
            self.refresh_class_listbox()
            self.update_checklist()

    def remove_double_clicked_rider(self, event):
        selected_index = self.riders_listbox.nearest(event.y)

        if selected_index is None:
            return

        if selected_index < 0 or selected_index >= self.riders_listbox.size():
            return

        self.riders_listbox.delete(selected_index)
        self.clear_url_selected_class_data()
        self.refresh_class_listbox()
        self.update_checklist()

    def update_checklist(self):
        show_name = self.show_name.get().strip()
        ride_pdf = self.ride_time_pdf.get().strip()
        ride_url = self.ride_time_url.get().strip()
        ride_source_loaded = self.ride_source_is_loaded()
        class_pdf = self.class_schedule_pdf.get().strip()
        class_url = self.class_schedule_url.get().strip()
        arena_source_loaded = bool(class_pdf)
        arena_source_skipped = self.skip_arena_source.get()
        arena_source_required = self.platform_requires_arena_source()
        rider_count = len(self.get_rider_lines())

        if hasattr(self, "show_name_status"):
            self.set_status_icon(self.show_name_status, bool(show_name))

        if hasattr(self, "ride_pdf_status"):
            self.set_status_icon(self.ride_pdf_status, bool(ride_pdf))

        if hasattr(self, "ride_url_status"):
            self.set_status_icon(
                self.ride_url_status,
                bool(ride_url and self.hso_rider_links)
            )

        if hasattr(self, "class_pdf_status"):
            self.set_status_icon(self.class_pdf_status, bool(class_pdf))

        if hasattr(self, "class_url_status"):
            self.set_status_icon(
                self.class_url_status,
                bool(class_url and class_pdf)
            )

        self.update_class_review_state()
        class_count = len(self.class_map)
        missing_class_count = len(self.missing_class_codes)

        if hasattr(self, "riders_status"):
            if rider_count > 0:
                self.riders_status.config(
                    text=f"✅ {rider_count} rider(s) selected",
                    fg="green"
                )
            else:
                self.riders_status.config(
                    text="⬜ No riders selected",
                    fg="gray"
                )

        lines = []

        lines.append(f"✅ Platform: {self.selected_platform_name()}")

        if show_name:
            lines.append("✅ Show name entered")
        else:
            lines.append("⬜ Enter show name")

        if self.ride_time_source == "url" and self.hso_rider_links:
            lines.append(f"✅ {self.selected_platform_name()} URL loaded")
        elif ride_pdf:
            lines.append("✅ Ride-time PDF selected")
        else:
            lines.append("⬜ Load show URL or select PDF fallback")

        if (
            self.ride_time_source == "url"
            and self.hso_rider_links
            and not arena_source_required
        ):
            lines.append(f"✅ {self.selected_platform_name()} includes arena/ring details")
        elif arena_source_loaded:
            if class_url:
                lines.append("✅ Ride Schedule URL loaded for arena/ring details")
            else:
                lines.append("✅ Ride schedule PDF added for arena/ring details")
        elif arena_source_skipped:
            lines.append("✅ Arena/ring source skipped for one-ring show")
        elif self.ride_time_source == "url":
            lines.append("⬜ Add Ride Schedule URL or PDF to populate arenas/rings")
        else:
            lines.append("⬜ Ride schedule PDF optional unless arena/ring review is needed")

        if missing_class_count > 0:
            lines.append(f"⚠ Review {missing_class_count} class definition(s)")
        elif class_count > 0:
            lines.append(f"✅ {class_count} class definition(s) loaded")
        elif self.ride_time_source == "url" and rider_count > 0:
            lines.append("⬜ Load classes for selected riders")
        else:
            lines.append("⬜ Load class definitions")        

        if rider_count > 0:
            lines.append(f"✅ {rider_count} rider(s) selected")
        else:
            lines.append("⬜ Add riders")

        arena_details_loaded = (
            self.ride_time_source != "url"
            or not arena_source_required
            or arena_source_loaded
            or arena_source_skipped
        )

        can_generate = self.can_generate_schedule(
            show_name,
            ride_source_loaded,
            class_count,
            rider_count,
            missing_class_count,
            arena_details_loaded
        )

        if self.schedule_generated:
            lines.append("✅ Schedule generated")
        elif can_generate:
            lines.append("✅ Ready to generate schedule")
        else:
            lines.append("⬜ Generate schedule")

        self.checklist_label.config(text="\n".join(lines))
        self.update_generate_button_state(can_generate)
        self.update_output_button_state()
        self.update_clear_archive_button_state()

    def can_generate_schedule(
        self,
        show_name,
        ride_source_loaded,
        class_count,
        rider_count,
        missing_class_count,
        arena_details_loaded
    ):
        return all([
            bool(show_name),
            ride_source_loaded,
            class_count > 0,
            rider_count > 0,
            missing_class_count == 0,
            arena_details_loaded,
        ])

    def ride_source_is_loaded(self):
        if self.ride_time_source == "url":
            return bool(self.ride_time_url.get().strip() and self.hso_rider_links)

        return bool(self.ride_time_pdf.get().strip())

    def update_generate_button_state(self, can_generate):
        if not hasattr(self, "generate_button"):
            return

        if can_generate:
            self.generate_button.config(
                state=tk.NORMAL,
                bg="#d9ead3",
                fg="black"
            )
        else:
            self.generate_button.config(
                state=tk.DISABLED,
                bg="#eeeeee",
                disabledforeground="#4a4a4a"
            )

    def update_output_button_state(self):
        if not hasattr(self, "open_output_button"):
            return

        if self.schedule_generated:
            self.open_output_button.config(
                state=tk.NORMAL,
                fg="black"
            )
        else:
            self.open_output_button.config(
                state=tk.DISABLED,
                disabledforeground="#4a4a4a"
            )

    def update_clear_archive_button_state(self):
        if not hasattr(self, "clear_archive_button"):
            return

        if self.schedule_generated:
            self.clear_archive_button.config(
                text="Archive Current Show",
                state=tk.NORMAL,
                bg="#fce5cd",
                fg="black"
            )
        else:
            has_selected_pdf = bool(
                self.ride_time_pdf.get().strip()
                or self.ride_time_url.get().strip()
                or self.class_schedule_pdf.get().strip()
                or self.class_schedule_url.get().strip()
            )
            button_state = tk.NORMAL if has_selected_pdf else tk.DISABLED

            self.clear_archive_button.config(
                text="Clear Ride Source",
                state=button_state,
                bg="#eeeeee" if not has_selected_pdf else self.root.cget("bg"),
                fg="black",
                disabledforeground="#4a4a4a"
            )

    def get_rider_lines(self):
        if not hasattr(self, "riders_listbox"):
            return []

        riders = list(self.riders_listbox.get(0, tk.END))
        return [
            self.clean_selected_rider_text(rider)
            for rider in riders
            if self.clean_selected_rider_text(rider)
        ]

    def set_rider_lines(self, riders):
        if not hasattr(self, "riders_listbox"):
            return

        self.riders_listbox.delete(0, tk.END)

        sorted_riders = sorted(
            riders,
            key=lambda name: name.lower()
        )

        for rider in sorted_riders:
            self.riders_listbox.insert(tk.END, self.format_selected_rider(rider))
        self.refresh_class_listbox()
        self.update_checklist()

    def add_rider(self):
        rider = self.new_rider_name.get().strip()

        if not rider:
            messagebox.showinfo(
                "Missing Rider Name",
                "Enter a rider name before clicking Add Rider."
            )
            return

        riders = self.get_rider_lines()

        if rider in riders:
            messagebox.showinfo(
                "Duplicate Rider",
                f"{rider} is already in the rider list."
            )
            return

        riders.append(rider)
        self.set_rider_lines(riders)
        self.new_rider_name.set("")

    def remove_selected_riders(self):
        selected_indices = list(self.riders_listbox.curselection())

        if not selected_indices:
            messagebox.showinfo(
                "No Riders Selected",
                "Select one or more riders to remove first."
            )
            return

        # Delete from bottom to top so indexes do not shift.
        for index in reversed(selected_indices):
            self.riders_listbox.delete(index)

        self.clear_url_selected_class_data()
        self.refresh_class_listbox()
        self.update_checklist()

    def clear_all_riders(self):
        confirm = messagebox.askyesno(
            "Clear All Riders",
            "This will clear the entire rider list.\n\nContinue?"
        )

        if confirm:
            self.riders_listbox.delete(0, tk.END)
            self.clear_url_selected_class_data()
            self.refresh_class_listbox()
            self.update_checklist()

    def choose_ride_time_pdf(self):
        file_path = filedialog.askopenfilename(
            title="Choose Ride Time PDF",
            filetypes=[("PDF files", "*.pdf")]
        )

        if file_path:
            self.ride_time_pdf.set(file_path)
            self.load_riders_from_pdf()  # Automatically load riders when a new PDF is selected

    def choose_class_schedule_pdf(self):
        file_path = filedialog.askopenfilename(
            title="Choose Ride Schedule PDF",
            filetypes=[("PDF files", "*.pdf")]
        )

        if file_path:
            self.class_schedule_pdf.set(file_path)
            self.class_schedule_url.set("")
            self.load_classes_from_pdf()

    def clear_selected_pdfs(self):
        self.ride_time_pdf.set("")
        self.ride_time_url.set("")
        self.class_schedule_pdf.set("")
        self.class_schedule_url.set("")
        self.clear_ride_time_data()
        self.clear_class_data()
        self.schedule_generated = False
        self.update_checklist()

    def clear_ride_time_data(self):
        self.ride_time_lines = []
        self.available_riders = []
        self.filtered_available_riders = []
        self.hso_rider_links = {}
        self.rider_ride_counts = {}
        self.ride_time_class_map = {}
        self.ride_time_source = "pdf"
        self.rebuild_class_map()

        if hasattr(self, "available_riders_listbox"):
            self.available_riders_listbox.delete(0, tk.END)

        self.refresh_selected_riders_listbox()
        self.refresh_class_listbox()

    def clear_class_data(self):
        self.class_schedule_class_map = {}
        self.rebuild_class_map()
        self.update_class_review_state()
        self.selected_class_code.set("")
        self.selected_class_name.set("")
        self.refresh_class_listbox()

    def clear_or_archive_current_show(self):
        if self.schedule_generated:
            self.archive_current_show()
        else:
            self.clear_selected_pdfs()

    def save_riders(self):
        riders = self.get_rider_lines()

        if not riders:
            raise ValueError("Please add at least one rider.")

        riders = sorted(
            riders,
            key=lambda name: name.lower()
        )

        self.set_rider_lines(riders)

        RIDERS_FILE.write_text("\n".join(riders) + "\n")

    def clear_folder_files(self, folder):
        folder.mkdir(exist_ok=True)

        for item in folder.iterdir():
            if item.is_file():
                item.unlink()

    def clear_folder_contents(self, folder):
        folder.mkdir(exist_ok=True)

        for item in folder.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            elif item.is_file():
                item.unlink()

    def folder_has_files(self, folder):
        if not folder.exists():
            return False

        return any(item.is_file() for item in folder.rglob("*"))

    def archive_folder_contents(self, source_folder, archive_show_folder):
        source_folder.mkdir(exist_ok=True)

        files = [
            item for item in source_folder.rglob("*")
            if item.is_file()
        ]

        if not files:
            return 0

        destination_folder = archive_show_folder / source_folder.name
        destination_folder.mkdir(parents=True, exist_ok=True)

        for file in files:
            destination_file = destination_folder / file.relative_to(source_folder)
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(file), str(destination_file))

        for folder in sorted(
            [item for item in source_folder.rglob("*") if item.is_dir()],
            key=lambda path: len(path.parts),
            reverse=True
        ):
            if not any(folder.iterdir()):
                folder.rmdir()

        return len(files)

    def archive_current_show(self):
        show_name = self.show_name.get().strip()

        if not show_name:
            messagebox.showerror(
                "Missing Show Name",
                "Please enter a show name before archiving."
            )
            return

        has_any_files = (
            self.folder_has_files(RIDE_TIMES_FOLDER)
            or self.folder_has_files(CLASS_SCHEDULES_FOLDER)
            or self.folder_has_files(OUTPUT_FOLDER)
        )

        if not has_any_files:
            messagebox.showinfo(
                "Nothing to Archive",
                "There are no current show files to archive."
            )
            return

        confirm = messagebox.askyesno(
            "Archive Current Show",
            "This will archive the current PDFs and output files, then clear the working folders.\n\n"
            "Continue?"
        )

        if not confirm:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        show_slug = app.slugify_filename(show_name)
        archive_show_folder = ARCHIVE_FOLDER / f"{show_slug}_{timestamp}"

        archive_show_folder.mkdir(parents=True, exist_ok=True)

        ride_count = self.archive_folder_contents(
            RIDE_TIMES_FOLDER,
            archive_show_folder
        )

        class_count = self.archive_folder_contents(
            CLASS_SCHEDULES_FOLDER,
            archive_show_folder
        )

        output_count = self.archive_folder_contents(
            OUTPUT_FOLDER,
            archive_show_folder
        )

        if RIDERS_FILE.exists():
            shutil.copy2(
                RIDERS_FILE,
                archive_show_folder / "riders.txt"
            )

        self.output_text.insert(
            tk.END,
            "\n===== ARCHIVE COMPLETE =====\n"
            f"Archive folder:\n{archive_show_folder}\n\n"
            f"Ride-time PDFs archived: {ride_count}\n"
            f"Class schedule PDFs archived: {class_count}\n"
            f"Output files archived: {output_count}\n"
            "Rider list snapshot saved.\n"
            "Working folders are now clear for the next show.\n"
            "============================\n"
        )

                # Clear GUI fields for the next show
        self.show_name.set("")
        self.ride_time_pdf.set("")
        self.ride_time_url.set("")
        self.class_schedule_pdf.set("")
        self.class_schedule_url.set("")

        messagebox.showinfo(
            "Archive Complete",
            "Current show files were archived successfully.\n\n"
            "The show name and selected PDFs have been cleared.\n\n"
            "You can now set up the next show."
        )


    def prepare_input_folders(self):
        ride_pdf = Path(self.ride_time_pdf.get())
        class_pdf = Path(self.class_schedule_pdf.get())

        if self.ride_time_source == "pdf" and not ride_pdf.exists():
            raise FileNotFoundError("Please choose a valid ride-time PDF.")

        self.clear_folder_files(RIDE_TIMES_FOLDER)
        self.clear_folder_files(CLASS_SCHEDULES_FOLDER)
        self.clear_folder_contents(OUTPUT_FOLDER)

        if self.ride_time_source == "pdf":
            shutil.copy2(ride_pdf, RIDE_TIMES_FOLDER / ride_pdf.name)

        if self.class_schedule_pdf.get().strip():
            if not class_pdf.exists():
                raise FileNotFoundError(
                    "Please choose a valid ride schedule PDF. "
                    "This is usually the PDF named Ride Schedule on the show website."
                )

            shutil.copy2(class_pdf, CLASS_SCHEDULES_FOLDER / class_pdf.name)
    

    def build_friendly_summary(self, result_text):
        summary_lines = []

        if "Filtered rides:" in result_text:
            for line in result_text.splitlines():
                if "Filtered rides:" in line:
                    summary_lines.append(f"✅ {line.strip()}")
                    break

        if "Loaded" in result_text and "class definitions" in result_text:
            for line in result_text.splitlines():
                if "Loaded" in line and "class definitions" in line:
                    summary_lines.append(f"✅ {line.strip()}")
                    break

        if "No missing class definitions found." in result_text:
            summary_lines.append("✅ No missing class definitions found.")
        elif "Missing class definitions:" in result_text:
            summary_lines.append("⚠️ Missing class definitions found. Review the validation output.")

        if "No rides missing horse names." in result_text:
            summary_lines.append("✅ No rides missing horse names.")
        elif "Rides missing horse name:" in result_text:
            summary_lines.append("⚠️ Some rides are missing horse names.")

        if "No rides missing arena info." in result_text:
            summary_lines.append("✅ No rides missing arena info.")
        elif "Rides missing arena:" in result_text:
            summary_lines.append("⚠️ Some rides are missing arena information.")

        if "Formatted Excel schedule exported to:" in result_text:
            summary_lines.append("✅ Excel schedule exported.")

        if "Schedule exported to:" in result_text or "AppSheet schedule exported to:" in result_text:
            summary_lines.append("✅ Supporting files saved in the supporting_files folder.")

        if not summary_lines:
            summary_lines.append("Schedule generation completed. Review the output below.")

        return "\n".join(summary_lines)

    def generate_schedule(self):
        self.output_text.delete("1.0", tk.END)

        try:
            self.save_riders()
            self.prepare_input_folders()

            captured_output = io.StringIO()

            show_name = self.show_name.get().strip()

            if not show_name:
                raise ValueError("Please enter a show name.")

            app.SHOW_NAME = show_name

            with contextlib.redirect_stdout(captured_output):
                if self.ride_time_source == "url":
                    riders = self.get_rider_lines()
                    selected_riders = set(riders)
                    rides = [
                        ride.copy()
                        for ride in self.hso_selected_rides
                        if ride.get("rider") in selected_riders
                    ]

                    if not rides:
                        rides = app.fetch_rides_for_riders(
                            self.hso_rider_links,
                            riders
                        )

                    schedule_lookup = app.build_class_schedule_ride_lookup()
                    app.enrich_rides_from_class_schedule(rides, schedule_lookup)
                    self.apply_skipped_arena_source(rides)
                    self.rider_ride_counts = self.count_web_rides_by_rider(rides)
                    app.export_rides(rides, self.class_map)
                else:
                    app.main(class_map_override=self.class_map)

            self.refresh_selected_riders_listbox()
            result_text = captured_output.getvalue()
            friendly_summary = self.build_friendly_summary(result_text)

            self.output_text.insert(tk.END, "===== SUMMARY =====\n")
            self.output_text.insert(tk.END, friendly_summary)
            self.output_text.insert(tk.END, "\n\n===== DETAILS =====\n")
            self.output_text.insert(tk.END, result_text)

            self.schedule_generated = True
            self.update_checklist()

            if "⚠️" in friendly_summary:
                messagebox.showwarning(
                    "Schedule Generated with Warnings",
                    "Schedule files were generated, but some items need review.\n\n"
                    "Check the summary and validation output."
                )
            else:
                messagebox.showinfo(
                    "Schedule Generated",
                    "Schedule files were generated successfully.\n\nCheck the output folder."
                )

        except Exception as error:
            error_message = f"ERROR:\n{error}"
            self.output_text.insert(tk.END, error_message)
            messagebox.showerror("Error", str(error))

    def open_output_folder(self):
        OUTPUT_FOLDER.mkdir(exist_ok=True)
        subprocess.run(["open", str(OUTPUT_FOLDER)])

    def folder_has_files(self, folder):
        if not folder.exists():
            return False

        return any(item.is_file() for item in folder.iterdir())

    def archive_folder_contents(self, source_folder, archive_show_folder):
        source_folder.mkdir(exist_ok=True)

        files = [
            item for item in source_folder.iterdir()
            if item.is_file()
        ]

        if not files:
            return 0

        destination_folder = archive_show_folder / source_folder.name
        destination_folder.mkdir(parents=True, exist_ok=True)

        for file in files:
            shutil.move(str(file), str(destination_folder / file.name))

        return len(files)

    def archive_current_show(self):
        show_name = self.show_name.get().strip()

        if not show_name:
            messagebox.showerror(
                "Missing Show Name",
                "Please enter a show name before archiving."
            )
            return

        has_any_files = (
            self.folder_has_files(RIDE_TIMES_FOLDER)
            or self.folder_has_files(CLASS_SCHEDULES_FOLDER)
            or self.folder_has_files(OUTPUT_FOLDER)
        )

        if not has_any_files:
            messagebox.showinfo(
                "Nothing to Archive",
                "There are no current show files to archive."
            )
            return

        confirm = messagebox.askyesno(
            "Archive Current Show",
            "This will archive the current PDFs and output files, then clear the working folders.\n\n"
            "Continue?"
        )

        if not confirm:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        show_slug = app.slugify_filename(show_name)
        archive_show_folder = ARCHIVE_FOLDER / f"{show_slug}_{timestamp}"

        archive_show_folder.mkdir(parents=True, exist_ok=True)

        ride_count = self.archive_folder_contents(
            RIDE_TIMES_FOLDER,
            archive_show_folder
        )

        class_count = self.archive_folder_contents(
            CLASS_SCHEDULES_FOLDER,
            archive_show_folder
        )

        output_count = self.archive_folder_contents(
            OUTPUT_FOLDER,
            archive_show_folder
        )

        if RIDERS_FILE.exists():
            shutil.copy2(
                RIDERS_FILE,
                archive_show_folder / "riders.txt"
            )

            self.output_text.insert(
            tk.END,
            "\n===== ARCHIVE COMPLETE =====\n"
            f"Archive folder:\n{archive_show_folder}\n\n"
            f"Ride-time PDFs archived: {ride_count}\n"
            f"Class schedule PDFs archived: {class_count}\n"
            f"Output files archived: {output_count}\n"
            "Rider list snapshot saved.\n"
            "Working folders are now clear for the next show.\n"
            "============================\n"
        )

        # Clear GUI fields for the next show
        self.show_name.set("")
        self.ride_time_pdf.set("")
        self.class_schedule_pdf.set("")

        self.schedule_generated = False
        self.update_checklist()

        # Force the interface to refresh immediately
        self.root.update_idletasks()

        messagebox.showinfo(
            "Archive Complete",
            "Current show files were archived successfully.\n\n"
            "The show name and selected PDFs have been cleared.\n\n"
            "You can now set up the next show."
        )


def main():
    root = tk.Tk()
    app_gui = HorseShowSchedulerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
