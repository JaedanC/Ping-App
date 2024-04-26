from __future__ import annotations
import os
import re
import threading
from enum import Enum
from typing import List, Optional
from io import StringIO
import time


class Ping:
    class ReplyType(Enum):
        Success = 0
        RequestTimedOut = 1
        DestinationHostUnreachable = 2
        DestinationNetUnreachable = 3
        GeneralFailure = 4
    
    class Reply:
        def __init__(
                self,
                reply_type: Ping.ReplyType,
                start_time: float,
                end_time: float,
                line: str,
                response_time: Optional[int] = None,
                response_ip: Optional[str] = None,
            ):
            self.reply_type = reply_type
            self.start_time = start_time
            self.end_time = end_time
            self.line = line
            self.response_time = response_time
            self.response_ip = response_ip
        
        def __repr__(self):
            return self.line

    def __init__(self, destination: str):
        self._destination = destination
        self._replies: List[Ping.Reply] = []
        self._found_destination = destination
        self._found_ip = None
        self._is_running = False
        self._thread_done = False
    
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
        start_time = time.time()
        ping_result = os.popen(f"ping -n 1 {self._destination}").read()
        end_time = time.time()

        fd_regex = re.compile(r"Pinging (.*) with 32 bytes of data:")
        fip_regex = re.compile(r".* \[(.*)\]")

        s_regex =   re.compile(r"Reply from (.*?): .*time[=<](\d+)ms.*")
        rto_regex = re.compile(r"Request timed out\..*")
        dhu_regex = re.compile(r"Reply from (.*): Destination host unreachable\.")
        dnu_regex = re.compile(r".*Destination net unreachable\.")
        gf_regex =  re.compile(r"General failure\..*")
        
        for line in ping_result.split("\n"):
            fd_match = fd_regex.match(line)
            if fd_match is not None:
                self._found_destination = fd_match.group(1)
            
                fid_match = fip_regex.match(fd_match.group(0))
                if fid_match is not None:
                    self._found_ip = fid_match.group(1)
            
            reply_type = None
            response_ip = None
            response_time = None
            if s_match := s_regex.match(line):
                reply_type = Ping.ReplyType.Success
                response_ip = s_match.group(1)
                response_time = int(s_match.group(2))
            elif rto_regex.match(line):
                reply_type = Ping.ReplyType.RequestTimedOut
            elif dhu_match := dhu_regex.match(line):
                reply_type = Ping.ReplyType.DestinationHostUnreachable
                response_ip = dhu_match.group(1)
            elif dnu_regex.match(line):
                reply_type = Ping.ReplyType.DestinationNetUnreachable
            elif gf_regex.match(line):
                reply_type = Ping.ReplyType.GeneralFailure
            
            if reply_type is not None:
                self._replies.append(Ping.Reply(
                    reply_type,
                    start_time,
                    end_time,
                    line,
                    response_time,
                    response_ip
                ))
        
        self._thread_done = True

    def tick(self):
        if self._thread_done:
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

    def get_found_ip(self) -> str:
        return self._found_ip or self._destination
    
    def get_found_destination(self) -> str:
        return self._found_destination or self._destination

    def get_destination(self) -> str:
        return self._destination

    def get_successes(self) -> List[Ping.Reply]:
        return [r for r in self._replies if r.reply_type is Ping.ReplyType.Success]

    def get_stats(self) -> str:
        packets = len(self._replies)
        output = StringIO()
        output.write(f"Ping statistics for {self.get_found_ip()}:\n")
        successes = self.get_successes()
        n_successes = len(successes)
        success_times = [s.response_time for s in successes if s.response_time is not None]

        if packets == 0:
            return output.getvalue()

        output.write("    Packets: Sent = {}, Received = {}, Lost = {} ({:.0f} loss),\n".format(
            packets,
            n_successes,
            packets - n_successes,
            100 - (n_successes/packets) * 100
        ))
        if n_successes > 0:
            output.write(f"Approximate round trip times in milli-seconds:\n")
            output.write("    Minimum = {:.0f}ms, Maximum = {:.0f}ms, Average = {:.0f}ms\n".format(
                min(success_times),
                max(success_times),
                sum(success_times)/len(success_times)
            ))
        return output.getvalue()

    def is_running(self) -> bool:
        return self._is_running
