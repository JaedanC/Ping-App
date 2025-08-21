from __future__ import annotations
import datetime
import math
import os
import re
import socket
import threading
import time
from enum import Enum, auto
from typing import List, Optional
from io import StringIO


import ping3
ping3.EXCEPTIONS = True


def time_to_excel(query_time: float) -> str:
    # d/mm/yyyy h:mm:ss
    time_struct = datetime.datetime.fromtimestamp(query_time)
    return time_struct.strftime("%d/%m/%Y %H:%M:%S")


class Ping:
    class ReplyType(Enum):
        Success = auto()
        TimeToLiveExpired = auto()
        DestinationHostUnreachable = auto()
        AddressUnreachable = auto()
        PortUnreachable = auto()
        DestinationUnreachable = auto()
        HostUnknown = auto()
        Timeout = auto()
        PingError = auto()


    class Reply:
        def __init__(
                self,
                destination: str,
                reply_type: Ping.ReplyType,
                start_time: float,
                end_time: float,
                more_detail_text: str,
                response_time: Optional[int] = None,
                response_ip: Optional[str] = None,
            ):
            self.destination = destination
            self.reply_type = reply_type
            self.start_time = start_time
            self.end_time = end_time
            self.more_detail_text = more_detail_text
            self.response_time = response_time
            self.response_ip = response_ip

        def __repr__(self):
            return self.more_detail_text

        def as_csv(self):
            return ",".join([
                time_to_excel(self.start_time),
                self.reply_type.name,
                str(self.destination or self.response_ip or ""),
                "" if self.response_time is None else str(self.response_time),
            ])

        @staticmethod
        def csv_headers():
            return "Timestamp,Reply,IP,Response Time (ms)"

    def __init__(self, destination: str):
        # This is what we supply to the ping command.
        self._destination: str = destination
        # If the supplied IP is fqdn, then this will be updated to include the
        # fqdn and the IP Address as one stringAddress
        self._found_destination_text: str = destination
        # If the supplied IP is fqdn, then this will be the IP Address that is
        # under the fqdn. If the IP Address is not pingable, then this will be
        # None.
        self._found_ip: Optional[str] = None
        self._replies: List[Ping.Reply] = []
        self._is_running = False
        self._thread_done = False
        # For linting
        self._t = None
        self._i = 0

    def __len__(self) -> int:
        return len(self._replies)

    def __getitem__(self, key: int):
        return self._replies.__getitem__(key)

    def __iter__(self):
        self._i = 0
        return self

    def __next__(self):
        if len(self._replies) == self._i:
            raise StopIteration
        found = self._replies[self._i]
        self._i += 1
        return found

    def _thread_ping(self):
        reply_type = None
        response_time = None

        # Returns:
        #     float | None | False: The delay in seconds/milliseconds, False on error and None on timeout.
        #
        # Raises:
        #     PingError: Any PingError will raise again if `ping3.EXCEPTIONS` is True.
        #
        start_time = time.time()
        error = None
        try:
            response_time = ping3.ping(self._destination, unit="ms") # in milliseconds
            reply_type = Ping.ReplyType.Success
        except ping3.errors.TimeToLiveExpired as e:
            error = e
            reply_type = Ping.ReplyType.TimeToLiveExpired
        except ping3.errors.DestinationHostUnreachable as e:
            error = e
            reply_type = Ping.ReplyType.DestinationHostUnreachable
        except ping3.errors.AddressUnreachable as e:
            error = e
            reply_type = Ping.ReplyType.AddressUnreachable
        except ping3.errors.PortUnreachable as e:
            error = e
            reply_type = Ping.ReplyType.PortUnreachable
        except ping3.errors.DestinationUnreachable as e:
            error = e
            reply_type = Ping.ReplyType.DestinationUnreachable
        except ping3.errors.HostUnknown as e:
            error = e
            reply_type = Ping.ReplyType.HostUnknown
        except ping3.errors.Timeout as e:
            error = e
            reply_type = Ping.ReplyType.Timeout
        except (ping3.errors.PingError, OSError) as e:
            error = e
            reply_type = Ping.ReplyType.PingError
        finally:
            end_time = time.time()

        # The start_time and end_time determine how wide to draw the box, but
        # not when to draw the box on the timeline. This value is an absolute
        # time. i.e. Should be a similar value to time.time()
        end_time = start_time + math.ceil(end_time - start_time)

        # $ ping quake.com
        #
        #     Pinging quake.com [104.18.21.2] with 32 bytes of data:
        #     Reply from 104.18.21.2: bytes=32 time=14ms TTL=53
        #     Reply from 104.18.21.2: bytes=32 time=30ms TTL=53
        #     Reply from 104.18.21.2: bytes=32 time=9ms TTL=53
        #     Reply from 104.18.21.2: bytes=32 time=26ms TTL=53
        #
        #     Ping statistics for 104.18.21.2:
        #         Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),
        #     Approximate round trip times in milli-seconds:
        #         Minimum = 9ms, Maximum = 30ms, Average = 19ms
        #
        # $ ping 8.8.8.7
        #
        #     Pinging 8.8.8.7 with 32 bytes of data:
        #     Request timed out.
        #
        #     Ping statistics for 8.8.8.7:
        #         Packets: Sent = 1, Received = 0, Lost = 1 (100% loss)
        try:
            self._found_ip = socket.gethostbyname(self._destination)  # Domain name will translated into IP address, and IP address leaves unchanged.
            if self._found_ip != self._destination:
                self._found_destination_text = f"{self._destination} [{self._found_ip}]"
        except socket.gaierror:
            pass

        if error is None:
            line_text = "Ping to {}: {:.5f}ms".format(self._found_destination_text or self._found_ip, response_time)
        else:
            line_text = "Ping to {}: {}".format(self._found_destination_text or self._found_ip, error)

        if reply_type is not None:
            self._replies.append(Ping.Reply(
                self._destination,
                reply_type,
                start_time,
                end_time,
                line_text,
                response_time,
                self._found_destination_text
            ))

        self._thread_done = True

    def tick(self):
        if self._thread_done:
            assert self._t is not None
            self._is_running = False
            self._thread_done = False
            self._t.join()

        if self._is_running:
            return

        self._is_running = True
        self._t = threading.Thread(target=self._thread_ping)
        self._t.start()

    def clear(self):
        self._replies.clear()

    def clear_before(self, pings_before_to_delete: int):
        to_pop = 0
        for reply in self._replies:
            if reply.end_time < pings_before_to_delete:
                to_pop += 1
            else:
                break

        while to_pop > 0:
            self._replies.pop(0)
            to_pop -= 1

    def get_found_ip(self) -> str:
        return self._found_ip or self._destination

    def get_found_destination(self) -> str:
        return self._found_destination_text or self._destination

    def get_destination(self) -> str:
        return self._destination

    def get_successes(self) -> List[Ping.Reply]:
        return [r for r in self._replies if r.reply_type is Ping.ReplyType.Success]

    def get_stats(self) -> str:
        packets = len(self._replies)
        output = StringIO()
        output.write(f"Ping statistics for {self.get_found_destination()}:\n")
        successes = self.get_successes()
        n_successes = len(successes)
        success_times = [s.response_time for s in successes if s.response_time is not None]

        if packets == 0:
            return output.getvalue()

        output.write("    Packets: Sent = {}, Received = {}, Lost = {} ({:.0f}%% loss),\n".format(
            packets,
            n_successes,
            packets - n_successes,
            100 - (n_successes/packets) * 100
        ))
        if n_successes > 0:
            output.write("Approximate round trip times in milli-seconds:\n")
            output.write("    Minimum = {:.0f}ms, Maximum = {:.0f}ms, Average = {:.0f}ms\n".format(
                min(success_times),
                max(success_times),
                sum(success_times)/len(success_times)
            ))
        return output.getvalue()

    def get_running_bool(self) -> bool:
        return self._is_running

    def get_replies(self) -> List[Ping.Reply]:
        return self._replies#
