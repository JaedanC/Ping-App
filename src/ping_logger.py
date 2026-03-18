import os
from typing import List

from .ping_cmd import Ping
from .helper import resource_path


class PingLogger:
    def __init__(
            self,
            logging_directory="logging"
        ):
        self.abs_logging_directory = resource_path(logging_directory)
        self.last_synced = 0

    def get_logging_directory(self) -> str:
        return self.abs_logging_directory

    def log_replies_single_file(self, path: List[str], replies: List[Ping.Reply]):
        found: List[Ping.Reply] = []
        for reply in reversed(replies):
            if reply.end_time > self.last_synced:
                found.append(reply)
            else:
                break

        abs_log_file_path = os.path.join(self.abs_logging_directory, *path)
        try:
            if not os.path.exists(abs_log_file_path):
                os.makedirs(os.path.dirname(abs_log_file_path), exist_ok=True)
                with open(abs_log_file_path, "w", encoding="utf-8") as f:
                    f.write(Ping.Reply.csv_headers() + "\n")

            with open(abs_log_file_path, "a", encoding="utf-8") as f:
                for reply in reversed(found):
                    f.write(reply.as_csv() + "\n")
        except PermissionError as e:
            print(e)


    def set_last_time_synced(self, time_synced: int):
        self.last_synced = time_synced
