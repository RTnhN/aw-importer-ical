#!/usr/bin/env python3

import sys
from pathlib import Path
import logging
import csv
from time import sleep
from datetime import datetime, date, time, timedelta
from icalendar import Calendar
from dateutil.rrule import rrulestr


from aw_core import dirs
from aw_core.models import Event
from aw_client.client import ActivityWatchClient
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCHER_NAME = "aw-importer-ical"

logger = logging.getLogger(WATCHER_NAME)
DEFAULT_CONFIG = f"""
[{WATCHER_NAME}]
data_path = ""
"""


def coerce2datetime(d):
    if isinstance(d, datetime):
        return d
    elif isinstance(d, date):
        return datetime.combine(d, time())
    else:
        raise TypeError


def parse_recurrence(event, start, duration, uid, already_logged_events):
    recurrence_events = []
    recurrence_rule = event.get("RRULE")
    if recurrence_rule:

        recurrence = rrulestr(recurrence_rule.to_ical().decode("utf-8"), dtstart=start)

        # Generate each recurrence event
        for event_start in recurrence:
            event_end = event_start + duration
            event_uid = f"{uid}+{event_start.strftime('%Y%m%dT%H%M%S')}"
            if event_uid in already_logged_events:
                continue
            recurrence_events.append(
                Event(
                    timestamp=event_start,
                    duration=duration,
                    data={"title": None, "attendees": [], "uid": event_uid},
                )
            )
            now = datetime.now().replace(tzinfo=event_end.tzinfo)
            if event_end > now:
                break
    return recurrence_events


def parse_and_add_data(aw, bucket_name, path):

    already_logged_events = set(
        event["data"]["uid"] for event in aw.get_events(bucket_name)
    )
    batch_events = []

    with open(path, encoding="utf8") as f:
        data = f.read()
        gcal = Calendar.from_ical(data)

    calendar_name = gcal.decoded("X-WR-CALNAME").decode("utf8")
    batch_events = []
    for event in gcal.walk("VEVENT"):
        try:
            # Extract basic event details
            title = event.decoded("summary").decode("utf8")
            start = coerce2datetime(event.decoded("dtstart"))
            end = coerce2datetime(event.decoded("dtend"))
            duration = end - start
            uid = event.decoded("uid").decode("utf8")
            attendees = [str(attendee) for attendee in (event.get("attendee") or [])]

            # Handle recurrence if applicable
            if "RRULE" in event:
                recurring_events = parse_recurrence(
                    event, start, duration, uid, already_logged_events
                )
                for recurring_event in recurring_events:
                    recurring_event.data["title"] = title
                    recurring_event.data["attendees"] = attendees
                    recurring_event.data["calendar_name"] = calendar_name
                batch_events.extend(recurring_events)
            else:
                if uid in already_logged_events:
                    continue
                main_event = Event(
                    timestamp=start,
                    duration=duration,
                    data={
                        "title": title,
                        "attendees": attendees,
                        "uid": uid,
                        "calendar_name": calendar_name,
                    },
                )
                batch_events.append(main_event)
        except Exception as ex:
            print(f"Error processing event: {ex}")
            print(event)
            continue

        # Batch insert if supported
    if batch_events:
        aw.insert_events(bucket_name, batch_events)

    print_statusline(f"Added {len(batch_events)} item(s)")


def load_config():
    from aw_core.config import load_config_toml as _load_config

    return _load_config(WATCHER_NAME, DEFAULT_CONFIG)


def print_statusline(msg):
    last_msg_length = (
        len(print_statusline.last_msg) if hasattr(print_statusline, "last_msg") else 0
    )
    print(" " * last_msg_length, end="\r")
    print(msg, end="\r")
    print_statusline.last_msg = msg


class CSVFileHandler(FileSystemEventHandler):
    """Custom event handler for watchdog to process new or modified CSV files."""

    def __init__(self, aw, bucket_name, data_path):
        self.aw = aw
        self.bucket_name = bucket_name
        self.data_path = data_path

    def on_created(self, event):
        """Called when a new file or folder is created."""
        self.process(event)

    def process(self, event):
        """Process the file if it's a .ics that hasn't been imported yet."""
        if not event.is_directory and event.src_path.endswith(".ics"):
            file_path = Path(event.src_path)
            if not file_path.stem.endswith("_imported"):
                parse_and_add_data(self.aw, self.bucket_name, file_path)
                file_path.rename(
                    self.data_path
                    / Path(
                        file_path.stem
                        + "_"
                        + datetime.now().strftime("%Y%m%d%H%M%S")
                        + "_imported"
                        + file_path.suffix
                    )
                )


def main():
    logging.basicConfig(level=logging.INFO)

    config_dir = dirs.get_config_dir(WATCHER_NAME)
    config = load_config()
    data_path = config[WATCHER_NAME].get("data_path", "")

    if not data_path:
        logger.warning(
            """You need to specify the folder that has the data files.
                       You can find the config file here:: {}""".format(
                config_dir
            )
        )
        sys.exit(1)

    aw = ActivityWatchClient(WATCHER_NAME, testing=False)
    bucket_name = "{}_{}".format(aw.client_name, aw.client_hostname)
    if aw.get_buckets().get(bucket_name) == None:
        aw.create_bucket(bucket_name, event_type="calendar_data", queued=True)
    aw.connect()

    # Set up watchdog observer
    event_handler = CSVFileHandler(aw, bucket_name, Path(data_path))
    observer = Observer()
    observer.schedule(event_handler, data_path, recursive=True)
    observer.start()

    try:
        while True:
            sleep(1)  # Keep the script running
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
