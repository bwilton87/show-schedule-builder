import pdfplumber
import os
import re
from datetime import datetime
import csv

PDF_FOLDER = "ride_times"

RIDERS_FILE = "riders.txt"


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

arena_pattern = re.compile(r"\s(?P<arena_num>\d+):\s")


def extract_lines():
    lines = []

    for file in os.listdir(PDF_FOLDER):
        if not file.endswith(".pdf"):
            continue

        path = os.path.join(PDF_FOLDER, file)

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()

                if text:
                    lines.extend(text.split("\n"))

    return lines


def extract_horse_and_arena(line):
    arena_match = arena_pattern.search(line)

    if not arena_match:
        return "", ""

    before_arena = line[:arena_match.start()].strip()
    arena = line[arena_match.start():].strip()

    parts = before_arena.split()

    if len(parts) < 5:
        return "", arena

    remaining = " ".join(parts[4:]).strip()

    if remaining.startswith("Q "):
        remaining = remaining[2:].strip()

    class_patterns = [
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
        r"Dressage Seat Equitation.*?",
        r"IBC - .*?",
    ]

    horse = remaining

    for pattern in class_patterns:
        match = re.match(pattern, remaining)
        if match:
            horse = remaining[match.end():].strip()
            break

    return horse, arena


def parse_rides(lines, my_riders):
    rides = []
    current_rider = None

    rider_pattern = re.compile(r"^[A-Z][a-z]+,\s+[A-Z]")
    ride_pattern = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d")

    for line in lines:
        line = line.strip()

        if rider_pattern.match(line):
            current_rider = line
            continue

        if current_rider not in my_riders:
            continue

        if ride_pattern.match(line):
            parts = line.split()

            day = parts[0]
            time = parts[1] + " " + parts[2]
            class_code = parts[3]

            horse, arena = extract_horse_and_arena(line)

            rides.append({
                "rider": current_rider,
                "day": day,
                "time": time,
                "class": class_code,
                "horse": horse,
                "arena": arena,
                "raw": line
            })

    return rides

def export_schedule_csv(rides):
    os.makedirs("output", exist_ok=True)

    output_file = os.path.join("output", "barn_schedule.csv")

    with open(output_file, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "Day",
            "Ride Time",
            "Ready By / On Horse By",
            "Rider",
            "Horse",
            "Class",
            "Arena",
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
                r["arena"],
                ""
            ])

    print(f"\nSchedule exported to: {output_file}")

def main():
    from datetime import datetime

DAY_ORDER = {
    "Mon": 1,
    "Tue": 2,
    "Wed": 3,
    "Thu": 4,
    "Fri": 5,
    "Sat": 6,
    "Sun": 7,
}


def ride_sort_key(ride):
    ride_time = datetime.strptime(ride["time"], "%I:%M %p").time()
    return (DAY_ORDER.get(ride["day"], 99), ride_time)


def main():
    my_riders = load_riders()

    if not my_riders:
        print("No riders found. Add riders to riders.txt")
        return

    lines = extract_lines()
    rides = parse_rides(lines, my_riders)
    
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
            f"{r['arena']}"
        )

    export_schedule_csv(rides)

if __name__ == "__main__":
    main()