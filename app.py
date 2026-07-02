import csv
import os
import re
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

import pdfplumber


PDF_FOLDER = "ride_times"
CLASS_SCHEDULE_FOLDER = "class_schedules"
RIDERS_FILE = "riders.txt"
OUTPUT_FOLDER = "output"
LETTER_ONLY_CLASS_CODES = {
    "L",
    "DHGEF",
}


DAY_ORDER = {
    "Mon": 1,
    "Tue": 2,
    "Wed": 3,
    "Thu": 4,
    "Fri": 5,
    "Sat": 6,
    "Sun": 7,
}


SHOW_NAME = "Barn Schedule"


def slugify_filename(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "show"


def output_path(filename):
    show_slug = slugify_filename(SHOW_NAME)
    return os.path.join(OUTPUT_FOLDER, f"{show_slug}_{filename}")


arena_pattern = re.compile(r"\s(?P<arena_num>\d+):\s")
ride_pattern = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d")
rider_pattern = re.compile(r"^[A-Z][a-zA-Z'’\-]+,\s+[A-Z]")

# Finds lines in the class schedule that start with a time.
class_schedule_time_pattern = re.compile(r"^\d{1,2}:\d{2}\s+(AM|PM)\s+")

# Finds likely class codes such as H1PSG, 121, 1FFS, 2I1, OB29, PB45GS, DHPEF, US4EF.
class_code_pattern = re.compile(
    r"\b("
    r"[A-Z]*\d[A-Z0-9]*"
    r"|PB\d+[A-Z]*"
    r"|OB\d+[A-Z]*"
    r"|DH[A-Z]+EF"
    r"|US\dEF"
    r"|L"
    r")\b"
)


def load_riders():
    if not os.path.exists(RIDERS_FILE):
        print(f"Missing rider file: {RIDERS_FILE}")
        return []

    with open(RIDERS_FILE, "r") as file:
        riders = [
            line.strip()
            for line in file
            if line.strip()
        ]

    return riders


def extract_lines_from_folder(folder):
    lines = []

    if not os.path.exists(folder):
        return lines

    for file in os.listdir(folder):
        if not file.lower().endswith(".pdf"):
            continue

        path = os.path.join(folder, file)

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()

                if text:
                    lines.extend(text.split("\n"))

    return lines

def extract_riders_from_lines(lines):
    riders = []

    for line in lines:
        line = line.strip()

        if rider_pattern.match(line):
            if line not in riders:
                riders.append(line)

    return sorted(riders, key=lambda name: name.lower())

def clean_class_name(name):
    name = name.strip()

    # Remove schedule housekeeping words.
    name = name.replace("Continues", "").strip()

    # Remove common judge/location text that leaks into the class name.
    name = re.sub(r"\b[A-Z][a-zA-Z'’\-]+\s+[A-Z][a-zA-Z'’\-]+\s+at\s+[A-Z]\b", "", name)
    name = re.sub(r"\bat\s+[A-Z]\b", "", name)

    # Clean up repeated spaces.
    name = re.sub(r"\s+", " ", name).strip()

    return name


def group_words_into_rows(words, tolerance=3):
    rows = []

    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not rows:
            rows.append([word["top"], [word]])
            continue

        previous_top = rows[-1][0]

        if abs(word["top"] - previous_top) <= tolerance:
            rows[-1][1].append(word)
        else:
            rows.append([word["top"], [word]])

    return rows


def looks_like_class_code(text):
    text = text.strip()

    if text in {"AM", "PM"}:
        return False

    if text.startswith("-"):
        return False

    if text in LETTER_ONLY_CLASS_CODES:
        return True

    # Most class codes contain at least one number:
    # H1PSG, 121, 1FFS, 2I1, OB29, PB45GS, DHPEF, US4EF, etc.
    if re.match(r"^[A-Z]*\d[A-Z0-9]*$", text):
        return True

    return False


def build_class_map():
    class_map = {}

    if not os.path.exists(CLASS_SCHEDULE_FOLDER):
        return class_map

    for file in os.listdir(CLASS_SCHEDULE_FOLDER):
        if not file.lower().endswith(".pdf"):
            continue

        path = os.path.join(CLASS_SCHEDULE_FOLDER, file)

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                words = page.extract_words()
                rows = group_words_into_rows(words)

                for _, row_words in rows:
                    row_words = sorted(row_words, key=lambda w: w["x0"])

                    row_text = " ".join(w["text"] for w in row_words)

                    if "Break" in row_text or "Lunch" in row_text or "Arena Done" in row_text:
                        continue

                    # A class schedule row should begin with a time.
                    if len(row_words) < 4:
                        continue

                    if not re.match(r"^\d{1,2}:\d{2}$", row_words[0]["text"]):
                        continue

                    if row_words[1]["text"] not in {"AM", "PM"}:
                        continue

                    # In this PDF, the class code is usually the first code-like token
                    # after the time and AM/PM.
                    class_code = ""
                    class_code_index = None

                    for i, word in enumerate(row_words[2:], start=2):
                        if looks_like_class_code(word["text"]):
                            class_code = word["text"]
                            class_code_index = i
                            break

                    if not class_code:
                        continue

                    class_name_words = []

                    for word in row_words[class_code_index + 1:]:
                        text = word["text"]

                        # Judge/location text is usually far to the right.
                        # Stop before it.
                        if word["x0"] > 390:
                            break

                        if text == "Continues":
                            continue

                        class_name_words.append(text)

                    class_name = " ".join(class_name_words).strip()
                    class_name = clean_class_name(class_name)

                    if class_code and class_name:
                        existing = class_map.get(class_code)

                        # Prefer the shorter/base name over a messy duplicate.
                        if not existing or len(class_name) < len(existing):
                            class_map[class_code] = class_name

    return class_map

def export_class_map_csv(class_map):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    output_file = output_path("barn_schedule.csv")
    
    with open(output_file, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "Class #",
            "Class Name"
        ])

        for class_code in sorted(class_map.keys()):
            writer.writerow([
                class_code,
                class_map[class_code]
            ])

    print(f"Class map exported to: {output_file}")


def normalize_text(text):
    text = text.lower()
    text = text.replace(".", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_class_and_horse(text, class_code, class_map):
    if text.startswith("Q "):
        text = text[2:].strip()

    class_name = class_map.get(class_code, "")

    if class_name:
        normalized_text = normalize_text(text)
        normalized_class_name = normalize_text(class_name)

        # Try exact class-map match first.
        if normalized_text.startswith(normalized_class_name):
            horse = text[len(class_name):].strip()
            return class_name, horse

        # Try removing common qualifier phrases from the class-map name.
        simplified_class_name = class_name

        qualifier_phrases = [
            "Markel/USEF Qualifying",
            "USEF Qualifying",
            "Qualifying",
        ]

        for phrase in qualifier_phrases:
            simplified_class_name = simplified_class_name.replace(phrase, "").strip()

        simplified_class_name = re.sub(r"\s+", " ", simplified_class_name).strip()
        normalized_simplified = normalize_text(simplified_class_name)

        if normalized_simplified and normalized_text.startswith(normalized_simplified):
            horse = text[len(simplified_class_name):].strip()
            return class_name, horse

    # Fallback patterns for cases where class schedule parsing is imperfect.
    fallback_patterns = [
        r"USEF Developing Horse Grand Prix Test",
        r"USEF Developing Horse Prix St\.? George Test",
        r"USEF 4-Year-Old Test",
        r"FEI 5-Year-Old Test Preliminary",
        r"FEI 5-Year-Old Test Final",
        r"FEI Pony Team Test",
        r"FEI Pony Individual Test",
        r"FEI Prix\.? St\. Georges",
        r"FEI Intermediare I",
        r"FEI Intermediare II",
        r"FEI Grand Prix",
        r"FEI Freestyle Test of Choice",
        r"USDF Freestyle Test of Choice",
        r"Training Level Test \d",
        r"First Level Test \d",
        r"Second Level Test \d",
        r"Third Level Test \d",
        r"Fourth Level Test \d",
        r"USDF Introductory Test [ABC]",
        r"USEF Pony Test of Choice",
        r"Dressage Seat Equitation - Adult Am\.",
        r"Dressage Seat Equitation - U16",
        r"Dressage Seat Equitation - Open",
        r"Dressage Seat Equitation - 17-21",
        r"Dressage Seat Equitation",
        r"IBC - .*",
        r"Stars and Stripes Benefit TOC \(USEF\)",
        r"Stars and Stripes Benefit TOC \(FEI\)",
        r"Stars and Stripes Benefit TOC \(Intro\)",
        r"Materiale 4- & 5-Year Old Fillies",
        r"Materiale 4- & 5-Year Old Stallions/Geldings",
        r"Young Horse Test of Choice \(excl 7YO\)",
    ]

    for pattern in fallback_patterns:
        match = re.match(pattern, text)
        if match:
            found_class_name = match.group(0).strip()
            horse = text[match.end():].strip()
            return class_name or found_class_name, horse

    return class_name, text


def extract_horse_and_arena(line, class_code, class_map):
    arena_match = arena_pattern.search(line)

    if not arena_match:
        # Some PDFs may use arena 0 without a colon. We can improve this later.
        return "", "", ""

    before_arena = line[:arena_match.start()].strip()
    arena = line[arena_match.start():].strip()

    parts = before_arena.split()

    if len(parts) < 5:
        return "", "", arena

    remaining = " ".join(parts[4:]).strip()

    class_name, horse = split_class_and_horse(remaining, class_code, class_map)

    return class_name, horse, arena


def split_arena(arena):
    match = re.match(r"(?P<number>\d+):\s*(?P<name>.+)", arena)

    if match:
        return match.group("number"), match.group("name")

    if arena.strip() == "0":
        return "0", ""

    return "", arena


def parse_rides(lines, my_riders, class_map):
    rides = []
    current_rider = None

    for line in lines:
        line = line.strip()

        if rider_pattern.match(line):
            current_rider = line
            continue

        if current_rider not in my_riders:
            continue

        if ride_pattern.match(line):
            parts = line.split()

            if len(parts) < 4:
                continue

            day = parts[0]
            time = parts[1] + " " + parts[2]
            class_code = parts[3]

            class_name, horse, arena = extract_horse_and_arena(
                line,
                class_code,
                class_map
            )

            arena_number, arena_name = split_arena(arena)

            rides.append({
                "rider": current_rider,
                "day": day,
                "time": time,
                "class": class_code,
                "class_name": class_name,
                "horse": horse,
                "arena": arena,
                "arena_number": arena_number,
                "arena_name": arena_name,
                "raw": line
            })

    return rides


def print_validation_report(rides, class_map):
    missing_class_codes = sorted({
        r["class"]
        for r in rides
        if not r["class_name"]
    })

    print("\n===== VALIDATION REPORT =====")

    print(f"Class definitions loaded: {len(class_map)}")

    if missing_class_codes:
        print("\nMissing class definitions:")
        for code in missing_class_codes:
            print(f"- {code}")
    else:
        print("\nNo missing class definitions found.")

    rides_missing_horse = [
        r for r in rides
        if not r["horse"]
    ]

    if rides_missing_horse:
        print("\nRides missing horse name:")
        for r in rides_missing_horse:
            print(f"- {r['day']} {r['time']} {r['rider']} {r['class']}")
    else:
        print("No rides missing horse names.")

    rides_missing_arena = [
        r for r in rides
        if not r["arena_number"]
    ]

    if rides_missing_arena:
        print("\nRides missing arena:")
        for r in rides_missing_arena:
            print(f"- {r['day']} {r['time']} {r['rider']} {r['class']}")
    else:
        print("No rides missing arena info.")

    print("=============================\n")


def make_ride_id(ride):
    raw_id = (
        f"{ride['day']}_"
        f"{ride['time']}_"
        f"{ride['rider']}_"
        f"{ride['horse']}_"
        f"{ride['class']}"
    )

    # Keep only letters and numbers so AppSheet has a clean key
    clean_id = re.sub(r"[^A-Za-z0-9]+", "_", raw_id)
    clean_id = clean_id.strip("_")

    return clean_id


def export_missing_class_definitions(rides):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    output_file = os.path.join(OUTPUT_FOLDER, "missing_class_definitions.csv")

    missing = []

    for r in rides:
        if not r["class_name"]:
            missing.append(r)

    with open(output_file, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "Class #",
            "Day",
            "Ride Time",
            "Rider",
            "Horse",
            "Raw Line"
        ])

        for r in missing:
            writer.writerow([
                r["class"],
                r["day"],
                r["time"],
                r["rider"],
                r["horse"],
                r["raw"]
            ])

    if missing:
        print(f"Missing class definitions exported to: {output_file}")
    else:
        print("No missing class definitions file needed.")


def export_used_class_codes(rides, class_map):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    output_file = os.path.join(OUTPUT_FOLDER, "used_class_codes.csv")

    used_codes = sorted({
        r["class"]
        for r in rides
    })

    with open(output_file, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "Class #",
            "Found In Class Map?",
            "Class Name"
        ])

        for code in used_codes:
            writer.writerow([
                code,
                "Yes" if code in class_map else "No",
                class_map.get(code, "")
            ])

    print(f"Used class codes exported to: {output_file}")


def ride_sort_key(ride):
    ride_time = datetime.strptime(ride["time"], "%I:%M %p").time()
    return (DAY_ORDER.get(ride["day"], 99), ride_time)


def export_schedule_csv(rides):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    output_file = output_path("barn_schedule.csv")

    with open(output_file, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "Day",
            "Ride Time",
            "Ready By / On Horse By",
            "Rider",
            "Horse",
            "Class #",
            "Class Name",
            "Arena #",
            "Arena Name",
            "Notes"
        ])

        for r in rides:
            writer.writerow([
                r["day"],
                r["time"],
                "",
                r["rider"],
                r["horse"],
                r["class"],
                r["class_name"],
                r["arena_number"],
                r["arena_name"],
                ""
            ])

    print(f"\nSchedule exported to: {output_file}")

def setup_schedule_sheet(sheet, rides, title):
    headers = [
        "Day",
        "Ride Time",
        "Ready By / On Horse By",
        "Rider",
        "Horse",
        "Class #",
        "Class Name",
        "Arena #",
        "Arena Name",
        "Notes"
    ]

    # Title row
    sheet["A1"] = title
    sheet["A1"].font = Font(bold=True, size=16)
    sheet["A1"].alignment = Alignment(horizontal="left", vertical="center")

    # Merge title across the full table width
    sheet.merge_cells("A1:J1")

    # Blank spacer row
    sheet.append([])

    # Header row starts on row 3
    sheet.append(headers)

    for r in rides:
        sheet.append([
            r["day"],
            r["time"],
            "",
            r["rider"],
            r["horse"],
            r["class"],
            r["class_name"],
            r["arena_number"],
            r["arena_name"],
            ""
        ])

    # Header formatting
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    header_font = Font(bold=True)

    for cell in sheet[3]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Freeze title + spacer + header
    sheet.freeze_panes = "A4"

    # Auto-filter on table only
    sheet.auto_filter.ref = f"A3:J{sheet.max_row}"

    # Column widths
    column_widths = {
        "A": 10,
        "B": 12,
        "C": 22,
        "D": 24,
        "E": 24,
        "F": 12,
        "G": 38,
        "H": 10,
        "I": 34,
        "J": 30,
    }

    for column_letter, width in column_widths.items():
        sheet.column_dimensions[column_letter].width = width

    # Body formatting
    for row in sheet.iter_rows(min_row=4):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    # Highlight manual entry columns
    for row in range(4, sheet.max_row + 1):
        sheet[f"C{row}"].fill = PatternFill("solid", fgColor="FFF2CC")
        sheet[f"J{row}"].fill = PatternFill("solid", fgColor="FFF2CC")

    # Slightly taller title row
    sheet.row_dimensions[1].height = 24

    # Page setup for printing
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True

    # Repeat title/header area when printed
    sheet.print_title_rows = "1:3"


def export_appsheet_csv(rides):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    output_file = output_path("appsheet_schedule.csv")

    with open(output_file, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "Ride ID",
            "Show Name",
            "Day",
            "Ride Time",
            "Ready By / On Horse By",
            "Rider",
            "Horse",
            "Class #",
            "Class Name",
            "Arena #",
            "Arena Name",
            "Notes",
            "Status"
        ])

        for r in rides:
            writer.writerow([
                make_ride_id(r),
                "",                 # Show Name - fill in later if desired
                r["day"],
                r["time"],
                "",                 # Ready By / On Horse By - editable in AppSheet
                r["rider"],
                r["horse"],
                r["class"],
                r["class_name"],
                r["arena_number"],
                r["arena_name"],
                "",                 # Notes - editable in AppSheet
                "Scheduled"         # Status - editable in AppSheet
            ])

    print(f"AppSheet schedule exported to: {output_file}")


def export_schedule_xlsx(rides):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    output_file = output_path("barn_schedule.xlsx")

    workbook = Workbook()

    # Main all-rides sheet
    all_sheet = workbook.active
    all_sheet.title = "All Rides"
    setup_schedule_sheet(all_sheet, rides, f"{SHOW_NAME} - All Rides Barn Schedule")

    # Separate sheets by day
    day_titles = {
        "Mon": "Monday Barn Schedule",
        "Tue": "Tuesday Barn Schedule",
        "Wed": "Wednesday Barn Schedule",
        "Thu": "Thursday Barn Schedule",
        "Fri": "Friday Barn Schedule",
        "Sat": "Saturday Barn Schedule",
        "Sun": "Sunday Barn Schedule",
    }

    days = []
    for r in rides:
        if r["day"] not in days:
            days.append(r["day"])

    for day in days:
        day_rides = [
            r for r in rides
            if r["day"] == day
        ]

        day_sheet = workbook.create_sheet(title=day)
        setup_schedule_sheet(
            day_sheet,
            day_rides,
            f"{SHOW_NAME} - {day_titles.get(day, f'{day} Barn Schedule')}"
        )

    workbook.save(output_file)

    print(f"Formatted Excel schedule exported to: {output_file}")


def main():
    my_riders = load_riders()

    if not my_riders:
        print("No riders found. Add riders to riders.txt")
        return

    class_map = build_class_map()

    print(f"Loaded {len(class_map)} class definitions from class schedule PDFs.")
    export_class_map_csv(class_map)

    lines = extract_lines_from_folder(PDF_FOLDER)
    rides = parse_rides(lines, my_riders, class_map)

    rides.sort(key=ride_sort_key)

    print_validation_report(rides, class_map)
    export_missing_class_definitions(rides)
    export_used_class_codes(rides, class_map)

    print(f"\nFiltered rides: {len(rides)}\n")

    current_day = None

    for r in rides:
        if r["day"] != current_day:
            current_day = r["day"]
            print(f"\n===== {current_day.upper()} =====")

        print(
            f"{r['time']} — "
            f"{r['rider']} — "
            f"{r['horse']} — "
            f"{r['class']} — "
            f"{r['class_name']} — "
            f"Arena {r['arena_number']}: {r['arena_name']}"
        )

    export_schedule_csv(rides)
    export_schedule_xlsx(rides)
    export_appsheet_csv(rides)
    
if __name__ == "__main__":
    main()