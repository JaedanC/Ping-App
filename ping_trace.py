from __future__ import annotations
from typing import List
import random
import pygui

from ping_cmd import Ping

class PingTrace:
    def __init__(self, pings: List[Ping]):
        self.pings = pings
        self.ping_colour = pygui.Vec4(
            random.randint(0, 255) / 255,
            random.randint(0, 255) / 255,
            random.randint(0, 255) / 255,
            1,
        )

    def tick(self):
        for ping in self.pings:
            if len(ping.get_replies()) == 0:
                ping.tick()

    def trace_complete(self) -> bool:
        return all(map(lambda p: len(p.get_replies()) > 0, self.pings))

    def __eq__(self, other: PingTrace):
        if not self.trace_complete() or not other.trace_complete():
            return False

        if len(self) != len(other):
            return False
        
        for a, b in zip(self.get_hops(), other.get_hops()):
            if a != b:
                return False
        
        return True

    def get_hops(self) -> List[str]:
        assert self.trace_complete(), "Can only ask for the hops once the trace is complete"

        hops = []
        for i in range(len(self.pings)):
            hops.append(self.get_hop(i + 1))
        return hops

    def get_hop(self, hop: int) -> str:
        assert self.trace_complete(), "Can only ask for a hop once the trace is complete"

        ping = self.pings[hop - 1]
        if ping.get_replies()[0].reply_type is Ping.ReplyType.Success:
            return ping.get_found_ip()

        if ping.get_replies()[0].reply_type is Ping.ReplyType.TimeToLiveExpired:
            return ping.get_ttl_expired_ip()

        return ""

    def merge(self, other: PingTrace):
        if len(self) != len(other):
            return False
        
        if not self.trace_complete() or not other.trace_complete():
            return False

        for a, b in zip(self.get_hops(), other.get_hops()):
            if a == "" or b == "":
                continue
            
            if a != b:
                return False

        for i, (a, b) in enumerate(zip(self.get_hops(), other.get_hops())):
            if a == "" and b != "":
                self.pings[i] = other.pings[i]
                continue

            if b == "" and a != "":
                other.pings[i] = self.pings[i]
                continue
        
        return True
            

    def __len__(self):
        return len(self.pings)
