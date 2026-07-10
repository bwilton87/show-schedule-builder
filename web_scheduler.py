import contextlib
import io
import json
import mimetypes
import os
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import app


PROJECT_ROOT = Path(__file__).parent
STATIC_ROOT = PROJECT_ROOT / "web_static"
HOST = "127.0.0.1"
DEFAULT_PORT = 5050


STATE = {
    "show_name": "",
    "source_type": "",
    "ride_url": "",
    "rider_links": {},
    "selected_riders": [],
    "selected_rides": [],
    "class_map": {},
    "ride_counts": {},
    "last_excel_path": "",
}


SOURCE_TYPES = {
    "equestrianhub": "equestrianhub",
    "foxvillage": "foxvillage",
    "horseshowoffice": "horseshowoffice",
}


def json_response(handler, payload, status=200):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler, message, status=400):
    json_response(handler, {"ok": False, "error": message}, status)


def read_json(handler):
    content_length = int(handler.headers.get("Content-Length", "0"))
    if content_length <= 0:
        return {}

    raw_body = handler.rfile.read(content_length).decode("utf-8")
    return json.loads(raw_body or "{}")


def count_rides_by_rider(rides):
    counts = {}

    for ride in rides:
        rider = ride.get("rider")
        if rider:
            counts[rider] = counts.get(rider, 0) + 1

    return counts


def apply_one_ring_fallback(rides):
    for ride in rides:
        if not ride.get("arena_name"):
            ride["arena"] = "One Ring"
            ride["arena_number"] = "1"
            ride["arena_name"] = "One Ring"

    return rides


def load_arena_source_from_url(ride_schedule_url):
    if not ride_schedule_url:
        return False

    class_schedule_folder = PROJECT_ROOT / app.CLASS_SCHEDULE_FOLDER
    class_schedule_folder.mkdir(exist_ok=True)
    download_path = class_schedule_folder / "horse_show_scheduler_ride_schedule.pdf"
    app.download_url_to_file(ride_schedule_url, download_path)
    return True


def reset_loaded_data(show_name, source_type, ride_url, rider_links):
    STATE.update({
        "show_name": show_name,
        "source_type": source_type,
        "ride_url": ride_url,
        "rider_links": rider_links,
        "selected_riders": [],
        "selected_rides": [],
        "class_map": {},
        "ride_counts": {},
        "last_excel_path": "",
    })


def load_riders(payload):
    show_name = payload.get("showName", "").strip()
    source_type = SOURCE_TYPES.get(payload.get("sourceType", "").strip())
    ride_url = payload.get("rideUrl", "").strip()

    if not show_name:
        raise ValueError("Enter a show name before loading riders.")

    if not source_type:
        raise ValueError("Choose a show platform.")

    if not ride_url:
        raise ValueError("Paste the show URL before loading riders.")

    rider_links = app.fetch_rider_links_from_url(ride_url, source_type)
    riders = sorted(rider_links.keys(), key=lambda rider: rider.lower())
    reset_loaded_data(show_name, source_type, ride_url, rider_links)

    return {
        "riders": riders,
        "riderCount": len(riders),
    }


def load_classes(payload):
    riders = payload.get("riders", [])

    if not STATE["rider_links"]:
        raise ValueError("Load riders from a show URL first.")

    if not riders:
        raise ValueError("Select at least one rider before loading classes.")

    selected_rides = app.fetch_rides_for_riders(STATE["rider_links"], riders)
    class_map = app.class_map_from_rides(selected_rides)
    ride_counts = {rider: 0 for rider in riders}
    ride_counts.update(count_rides_by_rider(selected_rides))

    STATE.update({
        "selected_riders": riders,
        "selected_rides": selected_rides,
        "class_map": class_map,
        "ride_counts": ride_counts,
        "last_excel_path": "",
    })

    return {
        "classMap": class_map,
        "classCount": len(class_map),
        "rideCounts": ride_counts,
        "rideCount": len(selected_rides),
    }


def generate_schedule(payload):
    show_name = payload.get("showName", STATE["show_name"]).strip()
    riders = payload.get("riders", STATE["selected_riders"])
    source_type = payload.get("sourceType", STATE["source_type"])
    ride_schedule_url = payload.get("rideScheduleUrl", "").strip()
    skip_arena_source = bool(payload.get("skipArenaSource"))

    if not show_name:
        raise ValueError("Enter a show name before generating the schedule.")

    if not riders:
        raise ValueError("Select at least one rider.")

    if not STATE["class_map"]:
        load_classes({"riders": riders})

    rides = [
        ride.copy()
        for ride in STATE["selected_rides"]
        if ride.get("rider") in set(riders)
    ]

    if not rides:
        rides = app.fetch_rides_for_riders(STATE["rider_links"], riders)

    if source_type == "horseshowoffice" and not skip_arena_source:
        if not ride_schedule_url:
            raise ValueError(
                "Paste the Ride Schedule URL for arena/ring details, "
                "or choose One-ring show."
            )
        load_arena_source_from_url(ride_schedule_url)

    schedule_lookup = app.build_class_schedule_ride_lookup()
    app.enrich_rides_from_class_schedule(rides, schedule_lookup)

    if skip_arena_source:
        apply_one_ring_fallback(rides)

    app.SHOW_NAME = show_name

    captured_output = io.StringIO()
    before_files = set(Path(app.OUTPUT_FOLDER).glob("*.xlsx"))

    with contextlib.redirect_stdout(captured_output):
        app.export_rides(rides, STATE["class_map"])

    after_files = set(Path(app.OUTPUT_FOLDER).glob("*.xlsx"))
    new_files = sorted(
        after_files - before_files,
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )
    excel_path = new_files[0] if new_files else max(
        after_files,
        key=lambda path: path.stat().st_mtime
    )

    STATE.update({
        "show_name": show_name,
        "selected_riders": riders,
        "selected_rides": rides,
        "ride_counts": count_rides_by_rider(rides),
        "last_excel_path": str(excel_path),
    })

    return {
        "rideCount": len(rides),
        "excelFilename": excel_path.name,
        "downloadUrl": "/download",
        "details": captured_output.getvalue(),
    }


class SchedulerRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/":
            return self.serve_static_file(STATIC_ROOT / "index.html")

        if parsed_url.path == "/download":
            return self.serve_download()

        requested_path = unquote(parsed_url.path).lstrip("/")
        return self.serve_static_file(STATIC_ROOT / requested_path)

    def do_POST(self):
        try:
            payload = read_json(self)

            if self.path == "/api/load-riders":
                return json_response(self, {"ok": True, **load_riders(payload)})

            if self.path == "/api/load-classes":
                return json_response(self, {"ok": True, **load_classes(payload)})

            if self.path == "/api/generate":
                return json_response(self, {"ok": True, **generate_schedule(payload)})

            return error_response(self, "Unknown API route.", 404)
        except Exception as error:
            return error_response(self, str(error), 500)

    def serve_static_file(self, path):
        resolved_path = path.resolve()

        if not str(resolved_path).startswith(str(STATIC_ROOT.resolve())):
            self.send_error(403)
            return

        if not resolved_path.exists() or not resolved_path.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(resolved_path.name)[0] or "text/plain"
        body = resolved_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_download(self):
        excel_path = Path(STATE.get("last_excel_path", ""))

        if not excel_path.exists() or not excel_path.is_file():
            self.send_error(404, "No generated Excel file is available yet.")
            return

        body = excel_path.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{excel_path.name}"'
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def find_available_port(start_port=DEFAULT_PORT):
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex((HOST, port)) != 0:
                return port

    raise RuntimeError("Could not find an available local port.")


def main():
    os.chdir(PROJECT_ROOT)
    port = find_available_port()
    server = ThreadingHTTPServer((HOST, port), SchedulerRequestHandler)
    url = f"http://{HOST}:{port}"

    if not os.environ.get("WEB_SCHEDULER_NO_BROWSER"):
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"Horse Show Scheduler web app is running at {url}")
    print("Press Control-C to stop the server.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
