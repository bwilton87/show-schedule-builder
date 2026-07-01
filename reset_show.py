import argparse
import shutil
from datetime import datetime
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).parent

FOLDERS_TO_ARCHIVE_AND_CLEAR = [
    "ride_times",
    "class_schedules",
    "output",
]

FILES_TO_COPY_TO_ARCHIVE = [
    "riders.txt",
]


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "show"


def folder_has_files(folder_path):
    if not folder_path.exists():
        return False

    return any(item.is_file() for item in folder_path.iterdir())


def archive_folder_contents(source_folder, destination_folder, dry_run=False):
    source_path = PROJECT_ROOT / source_folder
    destination_path = destination_folder / source_folder

    if not source_path.exists():
        print(f"Skipping missing folder: {source_folder}")
        return

    files = [item for item in source_path.iterdir() if item.is_file()]

    if not files:
        print(f"No files to archive in: {source_folder}")
        return

    if dry_run:
        print(f"[Dry run] Would archive {len(files)} file(s) from {source_folder}")
        for file in files:
            print(f"  - {file.name}")
        return

    destination_path.mkdir(parents=True, exist_ok=True)

    for file in files:
        shutil.move(str(file), str(destination_path / file.name))
        print(f"Archived: {source_folder}/{file.name}")


def copy_snapshot_files(destination_folder, dry_run=False):
    for file_name in FILES_TO_COPY_TO_ARCHIVE:
        source_path = PROJECT_ROOT / file_name

        if not source_path.exists():
            print(f"Skipping missing snapshot file: {file_name}")
            continue

        destination_path = destination_folder / file_name

        if dry_run:
            print(f"[Dry run] Would copy snapshot: {file_name}")
            continue

        shutil.copy2(source_path, destination_path)
        print(f"Copied snapshot: {file_name}")


def recreate_working_folders(dry_run=False):
    for folder in FOLDERS_TO_ARCHIVE_AND_CLEAR:
        folder_path = PROJECT_ROOT / folder

        if dry_run:
            print(f"[Dry run] Would ensure folder exists and is ready: {folder}")
            continue

        folder_path.mkdir(exist_ok=True)


def reset_show(show_name, dry_run=False):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    archive_name = f"{timestamp}_{slugify(show_name)}"
    archive_folder = PROJECT_ROOT / "archive" / archive_name

    print("\n===== SHOW RESET / ARCHIVE =====")
    print(f"Show name: {show_name}")
    print(f"Archive folder: {archive_folder}")

    if dry_run:
        print("\nRunning in dry-run mode. No files will be moved.\n")
    else:
        archive_folder.mkdir(parents=True, exist_ok=True)

    any_files_found = False

    for folder in FOLDERS_TO_ARCHIVE_AND_CLEAR:
        if folder_has_files(PROJECT_ROOT / folder):
            any_files_found = True

        archive_folder_contents(
            folder,
            archive_folder,
            dry_run=dry_run
        )

    copy_snapshot_files(
        archive_folder,
        dry_run=dry_run
    )

    recreate_working_folders(dry_run=dry_run)

    if not any_files_found:
        print("\nNo input/output files were found to archive.")

    if dry_run:
        print("\nDry run complete. Nothing was changed.")
    else:
        print("\nArchive complete.")
        print("Your working folders are ready for the next show:")
        print("- ride_times/")
        print("- class_schedules/")
        print("- output/")

    print("===============================\n")


def main():
    parser = argparse.ArgumentParser(
        description="Archive the current show files and reset folders for the next show."
    )

    parser.add_argument(
        "show_name",
        help="Name of the show being archived, wrapped in quotes."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would happen without moving files."
    )

    args = parser.parse_args()

    reset_show(
        show_name=args.show_name,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()