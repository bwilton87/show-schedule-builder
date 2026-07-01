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
        self.root.geometry("850x700")

        self.ride_time_pdf = tk.StringVar()
        self.class_schedule_pdf = tk.StringVar()
        self.show_name = tk.StringVar()

        self.build_interface()
        self.load_existing_riders()

    def build_interface(self):
        title = tk.Label(
            self.root,
            text="Horse Show Scheduler",
            font=("Arial", 20, "bold")
        )
        title.pack(pady=10)

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

        riders_label = tk.Label(
            self.root,
            text="Riders to include, one per line, exactly as shown in the PDF:",
            anchor="w"
        )
        riders_label.pack(fill="x", padx=20, pady=(15, 3))

        self.riders_text = scrolledtext.ScrolledText(self.root, height=9)
        self.riders_text.pack(fill="both", padx=20, pady=5)

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

    def load_existing_riders(self):
        if RIDERS_FILE.exists():
            riders = RIDERS_FILE.read_text()
            self.riders_text.delete("1.0", tk.END)
            self.riders_text.insert(tk.END, riders)

    def choose_ride_time_pdf(self):
        file_path = filedialog.askopenfilename(
            title="Choose Ride Time PDF",
            filetypes=[("PDF files", "*.pdf")]
        )

        if file_path:
            self.ride_time_pdf.set(file_path)

    def choose_class_schedule_pdf(self):
        file_path = filedialog.askopenfilename(
            title="Choose Class Schedule PDF",
            filetypes=[("PDF files", "*.pdf")]
        )

        if file_path:
            self.class_schedule_pdf.set(file_path)

    def clear_selected_pdfs(self):
        self.ride_time_pdf.set("")
        self.class_schedule_pdf.set("")

    def save_riders(self):
        riders = self.riders_text.get("1.0", tk.END).strip()

        if not riders:
            raise ValueError("Please enter at least one rider.")

        RIDERS_FILE.write_text(riders + "\n")

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

        messagebox.showinfo(
            "Archive Complete",
            "Current show files were archived successfully.\n\n"
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
                app.main()


            result_text = captured_output.getvalue()

            self.output_text.insert(tk.END, result_text)

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

        messagebox.showinfo(
            "Archive Complete",
            "Current show files were archived successfully.\n\n"
            "You can now set up the next show."
        )


def main():
    root = tk.Tk()
    app_gui = HorseShowSchedulerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()