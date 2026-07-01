import csv
import os
import re
from datetime import datetime

import pdfplumber


PDF_FOLDER = "ride_times"
CLASS_SCHEDULE_FOLDER = "class_schedules"
RIDERS_FILE = "riders.txt"
OUTPUT_FOLDER = "output"


DAY_ORDER = {
    "Mon": 1,
    "Tue": 2,
    "Wed": 3,
    "Thu": 4,
    "Fri": 5,
    "Sat": 6,
    "Sun": 7,
}


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


def build_class_map():
    lines = extract_lines_from_folder(CLASS_SCHEDULE_FOLDER)
    class_map = {}

    for line in lines:
        line = line.strip()

        if not class_schedule_time_pattern.match(line):
            continue

        if "Break" in line or "Lunch" in line or "Arena Done" in line:
            continue

        # Remove the time from the front of the line.
        without_time = re.sub(r"^\d{1,2}:\d{2}\s+(AM|PM)\s+", "", line).strip()

        codes = class_code_pattern.findall(without_time)

        if not codes:
            continue

        # Usually the actual class code is the last code-like value in the line.
        class_code = codes[-1]

        # Remove the class code from the class name text.
        class_name = without_time.replace(class_code, " ").strip()
        class_name = clean_class_name(class_name)

        if class_code and class_name:
            class_map[class_code] = class_name

    return class_map


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

        if normalized_text.startswith(normalized_class_name):
            horse = text[len(class_name):].strip()
            return class_name, horse

    # Fallback patterns for cases where class schedule parsing is imperfect.
    fallback_patterns = [
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
            return found_class_name, horse

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


def ride_sort_key(ride):
    ride_time = datetime.strptime(ride["time"], "%I:%M %p").time()
    return (DAY_ORDER.get(ride["day"], 99), ride_time)


def export_schedule_csv(rides):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    output_file = os.path.join(OUTPUT_FOLDER, "barn_schedule.csv")

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


def main():
    my_riders = load_riders()

    if not my_riders:
        print("No riders found. Add riders to riders.txt")
        return

    class_map = build_class_map()

    print(f"Loaded {len(class_map)} class definitions from class schedule PDFs.")

    lines = extract_lines_from_folder(PDF_FOLDER)
    rides = parse_rides(lines, my_riders, class_map)

    rides.sort(key=ride_sort_key)

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


if __name__ == "__main__":
    main()