from __future__ import annotations
from typing import List
import random
import pygui
import colorsys

from ping_cmd import Ping

class PingTrace:
    def __init__(self, pings: List[Ping]):
        self.pings = pings
        self.ping_colour = pygui.Vec4.zero().from_tuple(
            list(colorsys.hsv_to_rgb(
                random.randint(0, 100) / 100,
                random.randint(50, 100) / 100,
                1,
            )) + [1]
        )
        self.show = pygui.Bool(True)
        self._is_marked = True
        self._hits = 1

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

    def is_marked(self) -> bool:
        return self._is_marked

    def get_hops(self) -> List[str]:
        assert self.trace_complete(), "Can only ask for the hops once the trace is complete"

        return [self.get_hop(i) for i in range(len(self.pings))]

    def get_hop(self, hop: int) -> str:
        assert self.trace_complete(), "Can only ask for a hop once the trace is complete"

        ping = self.pings[hop]
        if ping.get_replies()[0].reply_type is Ping.ReplyType.Success:
            return ping.get_found_ip()

        if ping.get_replies()[0].reply_type is Ping.ReplyType.TimeToLiveExpired:
            return ping.get_ttl_expired_ip()

        return ""

    def get_ping(self, hop: int) -> str:
        assert self.trace_complete(), "Can only ask for a ping once the trace is complete"
        return self.pings[hop]

    def get_pings(self) -> List[Ping]:
        return self.pings

    def merge_and_mark(self, other: PingTrace):
        did_merge = self._merge(other)
        self._is_marked = did_merge
        if self._is_marked:
            self._hits += 1
        return did_merge

    def get_hits(self) -> int:
        return self._hits

    def clear_hits(self):
        self._hits = 1

    def _merge(self, other: PingTrace):
        if not self.trace_complete() or not other.trace_complete():
            return False

        for a, b in zip(self.get_hops(), other.get_hops()):
            if a == "" or b == "":
                continue
            
            if a != b:
                return False
        
        if len(self) < len(other):
            self.pings.extend(other.pings[len(self):])

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
