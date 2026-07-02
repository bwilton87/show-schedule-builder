import contextlib
from copy import error
import io
import shutil
import subprocess
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
        self.root.geometry("950x850")

        self.ride_time_pdf = tk.StringVar()
        self.class_schedule_pdf = tk.StringVar()
        self.show_name = tk.StringVar()
        self.rider_search = tk.StringVar()

        self.class_map = {}
        self.filtered_class_codes = []
        self.class_search = tk.StringVar()
        self.selected_class_code = tk.StringVar()
        self.selected_class_name = tk.StringVar()

        self.schedule_generated = False
        self.available_riders = []
        self.filtered_available_riders = []

        self.show_name.trace_add("write", lambda *args: self.update_checklist())
        self.ride_time_pdf.trace_add("write", lambda *args: self.update_checklist())
        self.class_schedule_pdf.trace_add("write", lambda *args: self.update_checklist())
        self.rider_search.trace_add("write", lambda *args: self.filter_available_riders())
        self.class_search.trace_add("write", lambda *args: self.filter_class_map())

        self.build_interface()
        self.load_existing_riders()
        self.update_checklist()

    def build_interface(self):
        title = tk.Label(
            self.root,
            text="Horse Show Scheduler",
            font=("Arial", 20, "bold")
        )
        title.pack(pady=10)
        
        checklist_frame = tk.LabelFrame(
            self.root,
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

        show_frame = tk.Frame(self.root)
        show_frame.pack(fill="x", padx=20, pady=5)

        tk.Label(show_frame, text="Show Name:", width=18, anchor="w").pack(side="left")
        tk.Entry(show_frame, textvariable=self.show_name).pack(side="left", fill="x", expand=True)

        ride_frame = tk.Frame(self.root)
        ride_frame.pack(fill="x", padx=20, pady=5)

        tk.Label(ride_frame, text="Ride Time PDF:", width=18, anchor="w").pack(side="left")
        tk.Entry(ride_frame, textvariable=self.ride_time_pdf).pack(side="left", fill="x", expand=True)
        tk.Button(ride_frame, text="Choose", command=self.choose_ride_time_pdf).pack(side="left", padx=5)

        class_frame = tk.Frame(self.root)
        class_frame.pack(fill="x", padx=20, pady=5)

        tk.Label(class_frame, text="Class Schedule PDF:", width=18, anchor="w").pack(side="left")
        tk.Entry(class_frame, textvariable=self.class_schedule_pdf).pack(side="left", fill="x", expand=True)
        tk.Button(class_frame, text="Choose", command=self.choose_class_schedule_pdf).pack(side="left", padx=5)
        tk.Button(class_frame, text="Load Classes", command=self.load_classes_from_pdf).pack(side="left", padx=5)

        class_defs_frame = tk.LabelFrame(
            self.root,
            text="Class Definitions",
            padx=10,
            pady=8
        )
        class_defs_frame.pack(fill="both", padx=20, pady=8)

        class_search_frame = tk.Frame(class_defs_frame)
        class_search_frame.pack(fill="x", pady=3)

        tk.Label(class_search_frame, text="Search Class #:").pack(side="left")
        tk.Entry(
            class_search_frame,
            textvariable=self.class_search
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
        tk.Entry(
            class_edit_frame,
            textvariable=self.selected_class_code
        ).pack(fill="x", pady=(0, 5))

        tk.Label(class_edit_frame, text="Class Name:").pack(anchor="w")
        tk.Entry(
            class_edit_frame,
            textvariable=self.selected_class_name
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

        riders_label = tk.Label(
            self.root,
            text="Riders:",
            anchor="w",
            font=("Arial", 12, "bold")
        )
        riders_label.pack(fill="x", padx=20, pady=(15, 3))

        rider_load_frame = tk.Frame(self.root)
        rider_load_frame.pack(fill="x", padx=20, pady=5)

        tk.Button(
            rider_load_frame,
            text="Load Riders from Ride-Time PDF",
            command=self.load_riders_from_pdf
        ).pack(side="left", padx=5)

        tk.Label(
            rider_load_frame,
            text="Search:"
        ).pack(side="left", padx=(20, 5))

        tk.Entry(
            rider_load_frame,
            textvariable=self.rider_search
        ).pack(side="left", fill="x", expand=True)

        rider_lists_frame = tk.Frame(self.root)
        rider_lists_frame.pack(fill="both", expand=False, padx=20, pady=5)

        available_frame = tk.LabelFrame(
            rider_lists_frame,
            text="Possible Riders from PDF"
        )
        available_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

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

        selected_frame = tk.LabelFrame(
            rider_lists_frame,
            text="Selected Riders for Schedule"
        )
        selected_frame.pack(side="left", fill="both", expand=True)

        self.riders_listbox = tk.Listbox(
            selected_frame,
            height=9,
            selectmode=tk.EXTENDED
        )
        self.riders_listbox.pack(fill="both", expand=True, padx=5, pady=5)

        rider_button_frame = tk.Frame(self.root)
        rider_button_frame.pack(fill="x", padx=20, pady=5)

        tk.Button(
            rider_button_frame,
            text="Add Selected Riders",
            command=self.add_selected_available_riders
        ).pack(side="left", padx=5)

        tk.Button(
            rider_button_frame,
            text="Remove Selected Riders",
            command=self.remove_selected_riders
        ).pack(side="left", padx=5)

        tk.Button(
            rider_button_frame,
            text="Sort Selected Riders A-Z",
            command=self.sort_riders
        ).pack(side="left", padx=5)

        tk.Button(
            rider_button_frame,
            text="Clear Selected Riders",
            command=self.clear_all_riders
        ).pack(side="left", padx=5)

        button_frame = tk.Frame(self.root)
        button_frame.pack(fill="x", padx=20, pady=10)

        tk.Button(
            button_frame,
            text="Generate Schedule",
            command=self.generate_schedule,
            height=2,
            bg="#d9ead3"
        ).pack(side="left", padx=5)

        tk.Button(
            button_frame,
            text="Open Output Folder",
            command=self.open_output_folder,
            height=2
        ).pack(side="left", padx=5)

        tk.Button(
            button_frame,
            text="Archive Current Show",
            command=self.archive_current_show,
            height=2,
            bg="#fce5cd"
        ).pack(side="left", padx=5)

        tk.Button(
            button_frame,
            text="Clear Selected PDFs",
            command=self.clear_selected_pdfs,
            height=2
        ).pack(side="left", padx=5)

        output_label = tk.Label(
            self.root,
            text="Status / Validation Output:",
            anchor="w"
        )
        output_label.pack(fill="x", padx=20, pady=(10, 3))

        self.output_text = scrolledtext.ScrolledText(self.root, height=18)
        self.output_text.pack(fill="both", expand=True, padx=20, pady=5)

    def load_classes_from_pdf(self):
        class_pdf = Path(self.class_schedule_pdf.get())

        if not class_pdf.exists():
            messagebox.showerror(
                "Missing Class Schedule PDF",
                "Please choose a valid class-schedule PDF first."
            )
            return

        try:
            # Clear the class_schedules folder and copy selected PDF there.
            self.clear_folder_files(CLASS_SCHEDULES_FOLDER)
            shutil.copy2(class_pdf, CLASS_SCHEDULES_FOLDER / class_pdf.name)

            self.class_map = app.build_class_map()
            self.filtered_class_codes = sorted(self.class_map.keys())

            self.refresh_class_listbox()

            messagebox.showinfo(
                "Classes Loaded",
                f"Loaded {len(self.class_map)} class definitions from the class schedule PDF."
            )

            self.update_checklist()

        except Exception as error:
            messagebox.showerror(
                "Could Not Read Classes",
                f"The app could not read class definitions from the selected PDF.\n\n{error}"
            )

    def refresh_class_listbox(self):
        if not hasattr(self, "class_listbox"):
            return

        self.class_listbox.delete(0, tk.END)

        for code in self.filtered_class_codes:
            class_name = self.class_map.get(code, "")
            self.class_listbox.insert(tk.END, f"{code} — {class_name}")

    def filter_class_map(self):
        if not hasattr(self, "class_listbox"):
            return

        search_text = self.class_search.get().strip().lower()

        codes = sorted(self.class_map.keys())

        if search_text:
            codes = [
                code for code in codes
                if search_text in code.lower()
                or search_text in self.class_map.get(code, "").lower()
            ]

        self.filtered_class_codes = codes
        self.refresh_class_listbox()

    def on_class_selected(self, event=None):
        selected_indices = list(self.class_listbox.curselection())

        if not selected_indices:
            return

        selected_text = self.class_listbox.get(selected_indices[0])

        if " — " not in selected_text:
            return

        code, class_name = selected_text.split(" — ", 1)

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
        self.filter_class_map()

        messagebox.showinfo(
            "Class Saved",
            f"{code} was added/updated."
        )

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

            self.available_riders = app.extract_riders_from_lines(lines)
            self.filtered_available_riders = self.available_riders[:]

            self.refresh_available_riders_listbox()

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

    def refresh_available_riders_listbox(self):
        self.available_riders_listbox.delete(0, tk.END)

        for rider in self.filtered_available_riders:
            self.available_riders_listbox.insert(tk.END, rider)

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

    def add_selected_available_riders(self):
        selected_indices = list(self.available_riders_listbox.curselection())

        if not selected_indices:
            messagebox.showinfo(
                "No Riders Selected",
                "Select one or more riders from the possible rider list first."
            )
            return

        selected_riders = [
            self.available_riders_listbox.get(index)
            for index in selected_indices
        ]

        current_riders = self.get_rider_lines()

        added_count = 0

        for rider in selected_riders:
            if rider not in current_riders:
                self.riders_listbox.insert(tk.END, rider)
                current_riders.append(rider)
                added_count += 1

        self.sort_riders()
        self.update_checklist()

        messagebox.showinfo(
            "Riders Added",
            f"Added {added_count} rider(s) to the selected rider list."
        )
    
    def add_double_clicked_rider(self, event):
        selected_index = self.available_riders_listbox.nearest(event.y)

        if selected_index is None:
            return

        rider = self.available_riders_listbox.get(selected_index)

        if not rider:
            return

        current_riders = self.get_rider_lines()

        if rider not in current_riders:
            self.riders_listbox.insert(tk.END, rider)
            self.sort_riders()
            self.update_checklist()
        else:
            messagebox.showinfo(
                "Duplicate Rider",
                f"{rider} is already in the selected rider list."
            )

    def update_checklist(self):
        show_name = self.show_name.get().strip()
        ride_pdf = self.ride_time_pdf.get().strip()
        class_pdf = self.class_schedule_pdf.get().strip()
        class_count = len(self.class_map)
        rider_count = len(self.get_rider_lines())

        lines = []

        if show_name:
            lines.append("✅ Show name entered")
        else:
            lines.append("⬜ Enter show name")

        if ride_pdf:
            lines.append("✅ Ride-time PDF selected")
        else:
            lines.append("⬜ Select ride-time PDF")

        if class_pdf:
            lines.append("✅ Class-schedule PDF selected")
        else:
            lines.append("⬜ Select class-schedule PDF")

        if class_count > 0:
            lines.append(f"✅ {class_count} class definition(s) loaded")
        else:
            lines.append("⬜ Load class definitions")        

        if rider_count > 0:
            lines.append(f"✅ {rider_count} rider(s) selected")
        else:
            lines.append("⬜ Add riders")

        if self.schedule_generated:
            lines.append("✅ Schedule generated")
        else:
            lines.append("⬜ Generate schedule")

        self.checklist_label.config(text="\n".join(lines))

    def get_rider_lines(self):
        if not hasattr(self, "riders_listbox"):
            return []

        riders = list(self.riders_listbox.get(0, tk.END))
        return [
            rider.strip()
            for rider in riders
            if rider.strip()
        ]

    def set_rider_lines(self, riders):
        if not hasattr(self, "riders_listbox"):
            return

        self.riders_listbox.delete(0, tk.END)

        for rider in riders:
            self.riders_listbox.insert(tk.END, rider)
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

        self.riders_listbox.insert(tk.END, rider)
        self.new_rider_name.set("")
        self.update_checklist()

    def sort_riders(self):
        riders = self.get_rider_lines()

        riders = sorted(
            riders,
            key=lambda name: name.lower()
        )

        self.set_rider_lines(riders)

    def remove_selected_riders(self):
        selected_indices = list(self.riders_listbox.curselection())

        if not selected_indices:
            messagebox.showinfo(
                "No Riders Selected",
                "Select one or more riders to remove first."
            )
            return

        selected_riders = [
            self.riders_listbox.get(index)
            for index in selected_indices
        ]

        confirm = messagebox.askyesno(
            "Remove Selected Riders",
            "Remove these riders?\n\n" + "\n".join(selected_riders)
        )

        if not confirm:
            return

        # Delete from bottom to top so indexes do not shift.
        for index in reversed(selected_indices):
            self.riders_listbox.delete(index)
            self.update_checklist()

    def clear_all_riders(self):
        confirm = messagebox.askyesno(
            "Clear All Riders",
            "This will clear the entire rider list.\n\nContinue?"
        )

        if confirm:
            self.riders_listbox.delete(0, tk.END)
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
            title="Choose Class Schedule PDF",
            filetypes=[("PDF files", "*.pdf")]
        )

        if file_path:
            self.class_schedule_pdf.set(file_path)
            self.load_classes_from_pdf()

    def clear_selected_pdfs(self):
        self.ride_time_pdf.set("")
        self.class_schedule_pdf.set("")

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

        messagebox.showinfo(
            "Archive Complete",
            "Current show files were archived successfully.\n\n"
            "The show name and selected PDFs have been cleared.\n\n"
            "You can now set up the next show."
        )


    def prepare_input_folders(self):
        ride_pdf = Path(self.ride_time_pdf.get())
        class_pdf = Path(self.class_schedule_pdf.get())

        if not ride_pdf.exists():
            raise FileNotFoundError("Please choose a valid ride-time PDF.")

        if not class_pdf.exists():
            raise FileNotFoundError("Please choose a valid class-schedule PDF.")

        self.clear_folder_files(RIDE_TIMES_FOLDER)
        self.clear_folder_files(CLASS_SCHEDULES_FOLDER)

        shutil.copy2(ride_pdf, RIDE_TIMES_FOLDER / ride_pdf.name)
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

        if "Schedule exported to:" in result_text:
            summary_lines.append("✅ CSV schedule exported.")

        if "Formatted Excel schedule exported to:" in result_text:
            summary_lines.append("✅ Excel schedule exported.")

        if "AppSheet schedule exported to:" in result_text:
            summary_lines.append("✅ AppSheet schedule exported.")

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

            if not self.class_map:
                self.load_classes_from_pdf()

            with contextlib.redirect_stdout(captured_output):
                app.main(class_map_override=self.class_map)

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