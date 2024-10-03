import os
from typing import List

from ping_cmd import Ping


class PingLogger:
    def __init__(
            self,
            logging_directory="logging"
        ):
        self.logging_directory = logging_directory
        self.last_synced = 0

    def get_logging_directory(self) -> str:
        return self.logging_directory

    def log_replies_single_file(self, path: List[str], replies: List[Ping.Reply]):
        found: List[Ping.Reply] = []
        for reply in reversed(replies):
            if reply.end_time > self.last_synced:
                found.append(reply)
            else:
                break

        log_file_path = os.path.join(self.logging_directory, *path)
        try:
            if not os.path.exists(log_file_path):
                os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
                with open(log_file_path, "w", encoding="utf-8") as f:
                    f.write(Ping.Reply.csv_headers() + "\n")

            with open(log_file_path, "a", encoding="utf-8") as f:
                for reply in reversed(found):
                    f.write(reply.as_csv() + "\n")
        except PermissionError as e:
            print(e)


    def set_last_time_synced(self, time_synced: int):
        self.last_synced = time_synced
