from __future__ import annotations
import math
import random
import colorsys
from collections import defaultdict
from typing import List, Dict, Tuple, Optional
from enum import Enum, auto

from helper import clamp, lerp
from ping_cmd import Ping

import pygui


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

    def get_hops(self, up_to=None) -> List[str]:
        assert self.trace_complete(), "Can only ask for the hops once the trace is complete"

        max_pings = len(self.pings)
        return [self.get_hop(i) for i in range(0, min(up_to, max_pings) if up_to is not None else max_pings)]

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
    
    def merge_mark_and_recommend(self, other: PingTrace) -> Tuple[bool, Optional[int]]:
        did_merge = self.merge_and_mark(other)
        if did_merge:
            # Work out where on me, if so, I completed by pings, and recommend
            # the other to do the same
            for i, ping in enumerate(self.pings):
                if len(ping.get_successes()) > 0:
                    return did_merge, i + 1
        return did_merge, None

    def get_hits(self) -> int:
        return self._hits

    def clear_hits(self):
        self._hits = 0

    def normalise(self) -> bool:
        # Truncate any excess pings that go to the end location
        for success_cursor, ping in enumerate(self.pings):
            if len(ping.get_successes()) > 0:
                self.pings = self.pings[:success_cursor + 1]
                return

    def is_normalised(self) -> bool:
        return len(self.pings) > 0 and len(self.pings[-1].get_successes()) > 0

    def _merge(self, other: PingTrace):
        if not self.trace_complete() or not other.trace_complete():
            return False
        
        for a, b in zip(self.get_hops(), other.get_hops()):
            if a == "" or b == "":
                continue
            
            if a != b:
                return False
        
        if len(self) < len(other) and not self.is_normalised():
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


class LiveRouting:
    class DrawLocation(Enum):
        Before = auto()
        After = auto()

    def __init__(self, destination):
        self._destination = destination
        self._go = pygui.Bool(False)
        self._hops = pygui.Int(20)
        self._next_run_recommended_hops = self._hops.value
        self._show_timeouts = pygui.Bool(True)
        self._show_line_between_timeout = pygui.Bool(False)
        self._ping_timeout = pygui.Int(2)
        self._wait_reset_seconds = pygui.Int(6)
        self._wait_timer_ticks = self._wait_reset_seconds.value * 60
        self._current_trace: Optional[PingTrace] = None
        self._unique_paths: List[PingTrace] = []
        self._has_current_trace_been_processed = False
        self._draw_locations = {}
        self._draw_location_counts = {}
    
    
    def _create_trace(self):
        # This is a bit of an art. Let's for now assume that the number of hops
        # is only going to be what we have configured above
        trace_pings = []
        for i in range(self._next_run_recommended_hops):
            trace_pings.append(Ping(
                self._destination,
                i + 1,
                do_reverse_dns_on_found_destination=True,
                timeout=self._ping_timeout.value,
            ))
        self._current_trace = PingTrace(trace_pings)
        self._has_current_trace_been_processed = False      

    def tick(self):
        if pygui.checkbox("Start", self._go) and self._go:
            self._create_trace()
        
        pygui.push_item_width(100)
        pygui.input_int("Hops", self._hops)
        pygui.same_line()
        pygui.text_disabled("Currently: {}".format(self._next_run_recommended_hops))
        pygui.input_int("Timeout wait", self._ping_timeout)
        pygui.input_int("Ping frequency", self._wait_reset_seconds)
        pygui.checkbox("Show timeouts", self._show_timeouts)
        pygui.pop_item_width()
        self._hops.value = clamp(self._hops.value, 1, 255)
        self._ping_timeout.value = clamp(self._ping_timeout.value, 1, 4)
        self._wait_reset_seconds.value = clamp(self._wait_reset_seconds.value, 1, 6)

        if pygui.button(f"Clear### Live Rouing {self._destination}"):
            self._unique_paths.clear()
        
        if not self._go:
            return
        
        # The refresh timer
        pygui.same_line()
        cx, cy = pygui.get_cursor_screen_pos()
        dl = pygui.get_window_draw_list()
        dl.path_arc_to(
            (cx + 10, cy + pygui.get_text_line_height_with_spacing()/2),
            pygui.get_text_line_height() / 2,
            0,
            math.radians((1 - (self._wait_timer_ticks / (self._wait_reset_seconds.value * 60))) * -360)
        )
        dl.path_stroke(
            pygui.Vec4(0.5, 0.5, 0.5, 1).to_u32(),
            0,
            2
        )
        pygui.dummy((0, 0))
        
        self._current_trace.tick()

        # Only run this code on the frame the trace completes
        if self._current_trace.trace_complete() and not self._has_current_trace_been_processed:
            self._has_current_trace_been_processed = True

            self._current_trace.normalise()
            self._next_run_recommended_hops = self._hops.value
            did_merge = False
            for trace in self._unique_paths:
                merged, recommendation = trace.merge_mark_and_recommend(self._current_trace)
                if merged:
                    did_merge = True
                    self._next_run_recommended_hops = recommendation or self._hops.value
            
            # The trace must be unique
            if not did_merge:
                self._unique_paths.append(self._current_trace)
            
        # After waiting ticks amount of time, start a new trace
        if self._current_trace.trace_complete():
            self._wait_timer_ticks -= 1
            if self._wait_timer_ticks == 0:
                self._create_trace()
                self._wait_timer_ticks = self._wait_reset_seconds.value * 60

    def _get_unique_hops(self) -> Dict[int, Dict[str, List[Ping]]]:
        """
        Docstring for _get_unique_hops
        
        :rtype:
            Dict[hop,
                Dict[hop_ip_address,
                    Tuple[n_traces_that_share_this_hop, Ping]]]
        """
        ttl_lookup: Dict[int, Dict[str, List[Ping]]] = defaultdict(dict)
        for trace in self._unique_paths:
            if not trace.show:
                continue

            for i in range(self._hops.value):
                try:
                    hop_ip = trace.get_hop(i)
                    ping = trace.get_ping(i)
                except IndexError:
                    continue

                if hop_ip not in ttl_lookup[i]:
                    ttl_lookup[i][hop_ip] = []
                ttl_lookup[i][hop_ip].append(ping)
        return ttl_lookup

    def draw(self):
        for i, ping_trace in enumerate(self._unique_paths):
            pygui.checkbox(f"### Show {i} {self._destination}", ping_trace.show)
            pygui.same_line()
            pygui.color_edit3("Path {}".format(i + 1), ping_trace.ping_colour, pygui.COLOR_EDIT_FLAGS_NO_INPUTS)
            pygui.same_line()
            if pygui.button("Clear ### Live Routing Hop: {} {}".format(self._destination, i)):
                ping_trace.clear_hits()
            pygui.same_line()
            pygui.text("Hits: {}".format(ping_trace.get_hits()))
            if ping_trace.is_marked():
                pygui.same_line()
                pygui.text_disabled("Selected")

        # self._draw_locations.clear()
        if pygui.begin_child("Live Routing " + self._destination, child_flags=pygui.CHILD_FLAGS_BORDERS):
            unique_hops = self._get_unique_hops()
            for hop, unique_hop in unique_hops.items():
                if hop > 0:
                    pygui.same_line()
                pygui.begin_group()
                pygui.text("Hop {}".format(hop + 1).ljust(len("xxx.xxx.xxx.xxx  "), " "))
                for hop_ip, pings in unique_hop.items():
                    # Only use ping as a reference for DNS
                    self._draw_locations[(LiveRouting.DrawLocation.Before.value, hop, hop_ip)] = (
                        pygui.get_cursor_screen_pos()[0] - 2,
                        pygui.get_cursor_screen_pos()[1] + pygui.get_text_line_height() / 2 - 4,
                    )

                    
                    if hop_ip == "":
                        pygui.dummy((pygui.calc_text_size("xxx.xxx.xxx.xxx")[0], pygui.get_text_line_height()))
                    else:
                        pygui.text(hop_ip)
                        ping = pings[0]
                        has_named_destination = ping.get_found_ip() != ping.get_destination()
                        if len(pings[0].get_successes()) > 0 and has_named_destination:
                            pygui.same_line()
                            pygui.text_colored((0, 1, 0, 1), "({})".format(self._destination))
                    
                    pygui.same_line()
                    self._draw_locations[(LiveRouting.DrawLocation.After.value, hop, hop_ip)] = (
                        pygui.get_cursor_screen_pos()[0],
                        pygui.get_cursor_screen_pos()[1] + pygui.get_text_line_height() / 2 - 4,
                    )
                    pygui.dummy((0, 0))

                    if pings[0].get_replies()[0].reply_type != Ping.ReplyType.Timeout:
                        pygui.text(pings[0].get_reverse_dns_lookup() or "")
                    else:
                        pygui.dummy((pygui.calc_text_size("xxx.xxx.xxx.xxx")[0], pygui.get_text_line_height()))
                pygui.end_group()
            
            # Custom line drawing
            self._draw_location_counts = defaultdict(int)
            for trace in self._unique_paths:
                if not trace.show:
                    continue
            
                hop_ips = trace.get_hops(up_to=self._hops.value)

                for hop, (hop_ip_a, hop_ip_b) in enumerate(zip(hop_ips, hop_ips[1:])):
                    dl = pygui.get_window_draw_list()

                    if hop_ip_a == "":
                        point_a = self._draw_locations[(LiveRouting.DrawLocation.Before.value, hop, hop_ip_a)]
                        point_b = self._draw_locations[(LiveRouting.DrawLocation.After.value,  hop, hop_ip_a)]

                        offset = self._draw_location_counts[(hop, hop_ip_a)]

                        point_with_offset_a = (
                            point_a[0],
                            point_a[1] + 3 * offset
                        )
                        point_with_offset_b = (
                            point_b[0],
                            point_b[1] + 3 * offset
                        )

                        dl.add_line(
                            point_with_offset_a,
                            point_with_offset_b,
                            trace.ping_colour.to_u32(),
                            thickness=2
                        )


                    point_a = self._draw_locations[(LiveRouting.DrawLocation.After.value,  hop,     hop_ip_a)]
                    point_b = self._draw_locations[(LiveRouting.DrawLocation.Before.value, hop + 1, hop_ip_b)]

                    offset_a = self._draw_location_counts[(hop,     hop_ip_a)]
                    offset_b = self._draw_location_counts[(hop + 1, hop_ip_b)]
                    self._draw_location_counts[(hop, hop_ip_a)] += 1

                    point_with_offset_a = (
                        point_a[0],
                        point_a[1] + 3 * offset_a
                    )
                    point_with_offset_b = (
                        point_b[0],
                        point_b[1] + 3 * offset_b
                    )

                    dl.add_line(
                        point_with_offset_a,
                        point_with_offset_b,
                        trace.ping_colour.to_u32(),
                        thickness=2
                    )

                    if trace.is_marked():
                        lerp_point = lerp(point_with_offset_a, point_with_offset_b, (pygui.get_frame_count() % 120) / 120)
                        dl.add_circle_filled(lerp_point, 4, trace.ping_colour.to_u32())
                    
                    # Extra Case: First hops does not exist. Draw a line between start(a) end (a)
        pygui.end_child()
