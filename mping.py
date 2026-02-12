from __future__ import annotations
from itertools import zip_longest
from typing import List, Dict, Optional, Tuple
import datetime
import ipaddress
import math
import os
import time

from ping_cmd import Ping
from ping_logger import PingLogger
from ping_trace import PingTrace
import pygui


def clamp(value, lower_bound, upper_bound):
    if value < lower_bound:
        return lower_bound
    if value > upper_bound:
        return upper_bound
    return value


def help_marker(desc: str):
    pygui.text_disabled("(?)")
    if pygui.is_item_hovered(pygui.HOVERED_FLAGS_DELAY_SHORT) and pygui.begin_tooltip():
        pygui.push_text_wrap_pos(pygui.get_font_size() * 35)
        pygui.text_unformatted(desc)
        pygui.pop_text_wrap_pos()
        pygui.end_tooltip()


class PyguiPing(Ping):
    def __init__(self, destination: str):
        super().__init__(destination)
        self._is_alive = pygui.Bool(True)
        self._do_tick = pygui.Bool(False)
        self._show_ping_window = pygui.Bool(False)
        self._follow_scroll = pygui.Bool(True)
        self._previous_frame_scroll = 0
        self._show_stats = pygui.Bool(False)

        self._tracert_go = False
        self._auto_tracert = pygui.Bool(True)
        self._tracert_hops = pygui.Int(20)
        self._tracert_pings: List[Ping] = [Ping(self._destination, ttl=i) for i in range(1, self._tracert_hops.value)]

        self._do_live_routing = pygui.Bool(False)
        self._live_routing_hops = pygui.Int(20)
        self._live_routing_auto_limit = pygui.Bool(True)
        self._live_routing_auto_truncate = pygui.Bool(True)
        self._live_routing_show_line_between_timeout = pygui.Bool(False)
        self._live_routing_ping_timeout = pygui.Int(2)
        self._live_routing_wait_reset = pygui.Int(6)
        self._live_routing_wait = self._live_routing_wait_reset.value * 60
        self._live_routing_current_trace = PingTrace([])
        self._live_routing_ping_history: List[PingTrace] = []
        self._live_routing_try_to_merge_done = False
        self._live_routing: Dict[int, Dict[Tuple[str, str], None]] = {}
        self._pygui_hop_positions_for_drawing_before = {}
        self._pygui_hop_positions_for_drawing_after = {}

    def draw(self, should_ping: bool, source_address_for_ping: str):
        # if pygui.get_frame_count() % 60 == 0 and self._do_tick and should_ping:
        if self._do_tick and should_ping:
            self.tick(source_address_for_ping)

        if not self._show_ping_window:
            return

        window_animation = "|/-\\"[int(pygui.get_time() / 0.5) % 3]
        window_title = "{} {}###{}".format(
            self.get_found_destination(),
            window_animation if self._do_tick else "",
            self.get_destination(),
        )

        pygui.set_next_window_size((600, 350), pygui.COND_FIRST_USE_EVER)
        if pygui.begin(window_title, self._show_ping_window):
            if pygui.begin_tab_bar("### " + window_title + " tabs"):
                if pygui.begin_tab_item("Pings"):
                    pygui.checkbox("Play", self._do_tick)
                    pygui.same_line()
                    if did_clear := pygui.button("Clear"):
                        self._follow_scroll.value = True
                        self._previous_frame_scroll = -1
                        self.clear()
                    pygui.same_line()
                    if self._follow_scroll:
                        pygui.text_disabled("Following")
                    else:
                        pygui.text_disabled("Scrolling")
                        pygui.same_line()
                        if pygui.button("Reset"):
                            self._follow_scroll.value = True
                    pygui.same_line()
                    pygui.checkbox("Show stats", self._show_stats)

                    if self._show_stats:
                        pygui.text(self.get_stats())
                    pygui.begin_child(self.get_found_ip(), (-1, -1), pygui.CHILD_FLAGS_BORDERS)

                    if pygui.get_scroll_y() < self._previous_frame_scroll:
                        self._follow_scroll.value = False
                    elif pygui.get_scroll_y() == pygui.get_scroll_max_y():
                        self._follow_scroll.value = True
                    if not did_clear:
                        self._previous_frame_scroll = pygui.get_scroll_y()

                    # Demonstrate using clipper for large vertical lists
                    clipper = pygui.ImGuiListClipper.create()

                    # This is our first example of not being able to share heap objects
                    # across the dll. I need to get a pointer to a valid type that it
                    # creates, not me. This requires adding a custom constructor and
                    # destructor for the ImGuiListClipper class.
                    clipper.begin(len(self))
                    while clipper.step():
                        for row_n in range(clipper.display_start, clipper.display_end):
                            # Display a data item
                            reply = self[row_n]

                            if reply.reply_type is Ping.ReplyType.Success:
                                pygui.push_style_color(pygui.COL_TEXT, (0, 1, 0, 1))
                            elif reply.reply_type is Ping.ReplyType.DestinationUnreachable:
                                pygui.push_style_color(pygui.COL_TEXT, (1, 1, 0, 1))
                            elif reply.reply_type is Ping.ReplyType.HostUnknown:
                                pygui.push_style_color(pygui.COL_TEXT, (0, 0, 1, 1))
                            else:
                                pygui.push_style_color(pygui.COL_TEXT, (1, 0, 0, 1))

                            start_time = datetime.datetime.fromtimestamp(int(reply.start_time))
                            start_time_str = start_time.strftime("%d/%m/%y @ %H:%M:%S%p")

                            pygui.text("[{}] {}".format(
                                start_time_str,
                                reply.more_detail_text
                            ))

                            pygui.pop_style_color()
                    clipper.destroy()

                    if self._follow_scroll:
                        pygui.set_scroll_y(pygui.get_scroll_max_y())

                    pygui.end_child()
                    pygui.end_tab_item()
                
                if pygui.begin_tab_item("Trace Route"):
                    pygui.slider_int("Hops", self._tracert_hops, 1, 255, flags=pygui.SLIDER_FLAGS_CLAMP_ON_INPUT | pygui.SLIDER_FLAGS_ALWAYS_CLAMP)
                    
                    if pygui.button("Go"):
                        self._tracert_pings: List[Ping] = [Ping(self._destination, ttl=i, do_reverse_dns_on_found_destination=True) for i in range(1, self._tracert_hops.value)]
                        self._tracert_go = True

                    if self._tracert_go:
                        for ping in self._tracert_pings:
                            if len(ping.get_replies()) < 3:
                                ping.tick()

                    if pygui.begin_table("tracert " + self._destination, 6):
                        pygui.table_setup_column("TTL",            flags=pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
                        pygui.table_setup_column("1",              flags=pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
                        pygui.table_setup_column("2",              flags=pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
                        pygui.table_setup_column("3",              flags=pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
                        pygui.table_setup_column("Reverse Lookup", flags=pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
                        pygui.table_setup_column("Status")
                        pygui.table_headers_row()

                        def show_ms(reply: Optional[Ping.Reply]):
                            if reply is None and self._tracert_go:
                                return "-/|\\"[(pygui.get_frame_count() // 30) % 4]

                            if reply is None:
                                return ""
                            
                            if reply.response_time is None:
                                return "."
                            
                            return "{} ms".format(round(reply.response_time))
                    
                        for ping in self._tracert_pings:
                            pygui.table_next_row()
                            pygui.table_next_column()
                            pygui.text(str(ping.get_ttl()))

                            replies = ping.get_replies()
                            replies_safe = replies + [None, None, None]
                            pygui.table_next_column()
                            pygui.text(show_ms(replies_safe[0]))
                            pygui.table_next_column()
                            pygui.text(show_ms(replies_safe[1]))
                            pygui.table_next_column()
                            pygui.text(show_ms(replies_safe[2]))

                            pygui.table_next_column()
                            if replies_safe[0] and replies_safe[0].response_time:
                                pygui.text(ping.get_reverse_dns_lookup() or "")
                            else:
                                pygui.text("")
                            pygui.table_next_column()

                            # TODO: Choose the best best to show
                            if len(replies) == 0:
                                pygui.text("")
                            else:
                                chosen_reply = replies[0]
                                for reply in replies:
                                    if reply.response_time:
                                        chosen_reply = reply
                                pygui.text(str(chosen_reply))

                        pygui.end_table()
                    
                    pygui.end_tab_item()
                
                if pygui.begin_tab_item("Live Routing"):
                    pygui.push_item_width(100)
                    pygui.input_int("Hops", self._live_routing_hops)
                    pygui.same_line()
                    pygui.checkbox("Auto-limit", self._live_routing_auto_limit)
                    pygui.same_line()
                    pygui.checkbox("Truncate", self._live_routing_auto_truncate)
                    pygui.input_int("Timeout wait", self._live_routing_ping_timeout)
                    pygui.input_int("Ping frequency", self._live_routing_wait_reset)
                    pygui.pop_item_width()
                    self._live_routing_hops.value = clamp(self._live_routing_hops.value, 1, 255)
                    self._live_routing_ping_timeout.value = clamp(self._live_routing_ping_timeout.value, 1, 4)
                    self._live_routing_wait_reset.value = clamp(self._live_routing_wait_reset.value, 1, 6)
                    if pygui.checkbox("Start", self._do_live_routing):
                        self._live_routing_current_trace = PingTrace(
                            [Ping(
                                self._destination,
                                ttl=i + 1,
                                do_reverse_dns_on_found_destination=True,
                                timeout=self._live_routing_ping_timeout.value
                            ) for i in range(self._live_routing_hops.value)]
                        )
                    pygui.same_line()
                    if pygui.button(f"Clear### Live rouing {self._destination}"):
                        self._live_routing_ping_history.clear()
                    
                    pygui.same_line()
                    cx, cy = pygui.get_cursor_screen_pos()
                    dl = pygui.get_window_draw_list()
                    dl.path_arc_to(
                        (cx + 10, cy + pygui.get_text_line_height_with_spacing()/2),
                        pygui.get_text_line_height() / 2,
                        0,
                        math.radians((1 - (self._live_routing_wait / (self._live_routing_wait_reset.value * 60))) * -360)
                    )
                    dl.path_stroke(
                        pygui.Vec4(0.5, 0.5, 0.5, 1).to_u32(),
                        0,
                        2
                    )
                    pygui.dummy((0, 0))
                    pygui.checkbox("Show Line between Timeouts", self._live_routing_show_line_between_timeout)

                    for i, ping_trace in enumerate(self._live_routing_ping_history):
                        pygui.checkbox(f"### Show {i} {self._destination}", ping_trace.show)
                        pygui.same_line()
                        pygui.color_edit3("Path {}".format(i + 1), ping_trace.ping_colour, pygui.COLOR_EDIT_FLAGS_NO_INPUTS)
                        pygui.same_line()
                        if pygui.button("Clear ### Live Routing Hop: {} {}".format(self._destination, i)):
                            ping_trace.clear_hits()
                        pygui.same_line()
                        pygui.text("Hits: {}".format(ping_trace.get_hits()))
                
                    if self._do_live_routing:
                        self._live_routing_current_trace.tick()

                        if self._live_routing_current_trace.trace_complete():
                            if not self._live_routing_try_to_merge_done:
                                merged = False
                                for existing_trace in self._live_routing_ping_history:
                                    if existing_trace.merge_and_mark(self._live_routing_current_trace):
                                        merged = True
                                        continue
                                if not merged and self._live_routing_current_trace not in self._live_routing_ping_history:
                                    self._live_routing_ping_history.append(self._live_routing_current_trace)
                                self._live_routing_try_to_merge_done = True

                                # Let's truncate the hops to include only up to the destination to avoid
                                # slamming the end-point, but don't delete history of other pings.
                                if self._live_routing_auto_limit:
                                    for hop_n, ping in enumerate(self._live_routing_current_trace.get_pings()):
                                        if len(ping.get_successes()) > 0:
                                            if self._live_routing_auto_truncate:
                                                self._live_routing_current_trace.pings = self._live_routing_current_trace.pings[:hop_n + 1]
                                            break
                                    largest_ttl_to_keep = 0
                                    for ping_trace in self._live_routing_ping_history:
                                        largest_ttl_to_keep = max(largest_ttl_to_keep, len(ping_trace))
                                    self._live_routing_hops.value = largest_ttl_to_keep
                            
                            self._live_routing_wait -= 1
                            if self._live_routing_wait == 0:
                                self._live_routing_wait = self._live_routing_wait_reset.value * 60
                                self._live_routing_current_trace = PingTrace([
                                    Ping(
                                        self._destination,
                                        ttl=i + 1,
                                        do_reverse_dns_on_found_destination=True, # Doing the DNS query each second slows it down quite a lot.
                                        timeout=self._live_routing_ping_timeout.value
                                    ) for i in range(self._live_routing_hops.value)])
                                self._live_routing_try_to_merge_done = False
                    
                    ping_lookup: Dict[int, Dict[str, Ping]] = {}
                    for hop_n in range(self._live_routing_hops.value):
                        if hop_n not in ping_lookup:
                            ping_lookup[hop_n] = {}       
                                                 
                        for ping_trace in self._live_routing_ping_history:
                            if not ping_trace.trace_complete():
                                continue

                            try:
                                hop_ip = ping_trace.get_hop(hop_n)
                                ping = ping_trace.get_ping(hop_n)
                            except IndexError:
                                # That's okay. There are likely two ping_traces
                                # with different lengths in the history
                                continue

                            if hop_ip not in ping_lookup[hop_n]:
                                ping_lookup[hop_n][hop_ip] = ping

                    if pygui.begin_child("Live routing window", child_flags=pygui.CHILD_FLAGS_BORDERS):
                        for hop_n in range(self._live_routing_hops.value):
                            if hop_n > 0:
                                pygui.same_line()
                            pygui.begin_group()
                            pygui.text("Hop {}".format(hop_n + 1).ljust(len("xxx.xxx.xxx.xxx dd"), " "))
                            for hop_ip, ping in ping_lookup[hop_n].items():
                                self._pygui_hop_positions_for_drawing_before[(hop_n, hop_ip)] = (
                                    pygui.get_cursor_screen_pos()[0],
                                    pygui.get_cursor_screen_pos()[1] + pygui.get_text_line_height() / 2,
                                )
                                if hop_ip != "" and len(ping.get_successes()) > 0:
                                    pygui.text_colored(pygui.Vec4(0, 1, 0, 1).tuple(), hop_ip)
                                elif hop_ip != "":
                                    pygui.text(hop_ip)
                                else:
                                    pygui.dummy((pygui.calc_text_size("xxx.xxx.xxx.xxx")[0], pygui.get_text_line_height()))
                                pygui.same_line()
                                self._pygui_hop_positions_for_drawing_after[(hop_n, hop_ip)] = (
                                    pygui.get_cursor_screen_pos()[0],
                                    pygui.get_cursor_screen_pos()[1] + pygui.get_text_line_height() / 2,
                                )
                                pygui.dummy((0, 0))
                                if hop_ip != "":
                                    pygui.text((ping.get_reverse_dns_lookup() or "") if ping.get_replies()[0].reply_type != Ping.ReplyType.Timeout else "")
                                else:
                                    pygui.dummy((pygui.calc_text_size("xxx.xxx.xxx.xxx")[0], pygui.get_text_line_height()))


                            pygui.end_group()
                        
                        dl = pygui.get_window_draw_list()

                        paths_start_share_drawn_n_times = {}
                        paths_end_share_drawn_n_times = {}
                        for ping_trace in self._live_routing_ping_history:
                            if not ping_trace.trace_complete():
                                continue

                            if not ping_trace.show:
                                continue

                            hops = ping_trace.get_hops()

                            def draw_line(first_hop_n, second_hop_n, first_hop, second_hop) -> Tuple[Tuple[int, int], Tuple[int, int]]:
                                if (first_hop_n, first_hop) not in paths_start_share_drawn_n_times:
                                    paths_start_share_drawn_n_times[(first_hop_n, first_hop)] = 0
                                
                                if (second_hop_n, second_hop) not in paths_end_share_drawn_n_times:
                                    paths_end_share_drawn_n_times[(second_hop_n, second_hop)] = 0
                                
                                first_offset = paths_start_share_drawn_n_times[(first_hop_n, first_hop)]
                                paths_start_share_drawn_n_times[(first_hop_n, first_hop)] += 1

                                second_offset = paths_end_share_drawn_n_times[(second_hop_n, second_hop)]
                                paths_end_share_drawn_n_times[(second_hop_n, second_hop)] += 1

                                first_pos = self._pygui_hop_positions_for_drawing_after[(first_hop_n, first_hop)]
                                first_pos = (
                                    first_pos[0],
                                    first_pos[1] - 4  + 3 * first_offset
                                )
                                second_pos = self._pygui_hop_positions_for_drawing_before[(second_hop_n, second_hop)]
                                second_pos = (
                                    second_pos[0] - 5,
                                    second_pos[1] - 4  + 3 * second_offset
                                )

                                dl.add_line(
                                    first_pos,
                                    second_pos,
                                    ping_trace.ping_colour.to_u32(),
                                    thickness=2
                                )

                                return first_pos, second_pos
                            
                            def draw_line_timeout(first_hop_n, first_hop):
                                if (first_hop_n, first_hop) not in paths_start_share_drawn_n_times:
                                    paths_start_share_drawn_n_times[(first_hop_n, first_hop)] = 0
                                
                                offset = paths_start_share_drawn_n_times[(first_hop_n, first_hop)]

                                first_pos = self._pygui_hop_positions_for_drawing_before[(first_hop_n, first_hop)]
                                first_pos = (
                                    first_pos[0] - 5,
                                    first_pos[1] - 4  + 3 * offset
                                )
                                second_pos = self._pygui_hop_positions_for_drawing_after[(first_hop_n, first_hop)]
                                second_pos = (
                                    second_pos[0],
                                    second_pos[1] - 4  + 3 * offset
                                )

                                dl.add_line(
                                    first_pos,
                                    second_pos,
                                    ping_trace.ping_colour.to_u32(),
                                    thickness=2
                                )

                            def lerp(ps: Tuple[int, int], pe: Tuple[int, int], percent: float) -> Tuple[int, int]:
                                return (
                                    ps[0] + (pe[0] - ps[0]) * percent,
                                    ps[1] + (pe[1] - ps[1]) * percent,
                                )

                            if self._live_routing_show_line_between_timeout:
                                for hop_n, first_hop in enumerate(hops):
                                    if first_hop == "":
                                        continue

                                    next_hop_n = hop_n + 1
                                    second_hop = None
                                    while next_hop_n < len(hops):
                                        if hops[next_hop_n] != "":
                                            second_hop = hops[next_hop_n]
                                            break

                                        next_hop_n += 1
                                    
                                    if second_hop is None:
                                        continue

                                    ps, pe = draw_line(hop_n, next_hop_n, first_hop, second_hop)

                                    if ping_trace.is_marked():
                                        lerp_point = lerp(ps, pe, (pygui.get_frame_count() % 120) / 120)
                                        dl.add_circle_filled(lerp_point, 4, ping_trace.ping_colour.to_u32())
                            else:
                                for hop_n, (first_hop, second_hop) in enumerate(zip(hops, hops[1:])):
                                    if first_hop == "":
                                        draw_line_timeout(hop_n, first_hop)
                                    
                                    ps, pe = draw_line(hop_n, hop_n + 1, first_hop, second_hop)
                            
                                    if ping_trace.is_marked():
                                        lerp_point = lerp(ps, pe, (pygui.get_frame_count() % 120) / 120)
                                        dl.add_circle_filled(lerp_point, 4, ping_trace.ping_colour.to_u32())

                    pygui.end_child()
                    pygui.end_tab_item()
                pygui.end_tab_bar()
        pygui.end()

    def is_alive(self) -> bool:
        return bool(self._is_alive)

    def get_running_bool(self) -> pygui.Bool:
        return self._do_tick

    def get_is_window_visible_bool(self) -> pygui.Bool:
        return self._show_ping_window

    def set_running(self, do_tick: pygui.Bool):
        # Performs a copy just to be sure were not passing in the wrong thing
        self._do_tick = pygui.Bool(do_tick.value)


class IPFileContent:
    class IPGroup:
        def __init__(self, group_name: str = None):
            self._group_name = group_name
            self.ips: List[str] = []
            self._pygui_pings: List[PyguiPing] = []

        def __len__(self):
            return len(self.ips)

        def add_ip(self, ip: str):
            self.ips.append(ip)

        def add_ips(self, ips: List[str]):
            self.ips += ips

        def clear_pings(self):
            for ping in self._pygui_pings:
                ping.clear()

        def get_pings(self) -> List[PyguiPing]:
            return self._pygui_pings

        def get_group_name(self) -> str:
            return self._group_name

    class IPGroupManager:
        def __init__(self):
            self._current_group = IPFileContent.IPGroup()
            self._groups: List[IPFileContent.IPGroup] = []

        def start_new_group(self, group_name: str):
            self._groups.append(self._current_group)
            self._current_group = IPFileContent.IPGroup(group_name)

        def finish_creating_groups(self):
            if len(self._current_group) > 0:
                self._groups.append(self._current_group)

        def add_ip(self, ip: str):
            self._current_group.add_ip(ip)

        def add_ips(self, ips: List[str]):
            self._current_group.add_ips(ips)

        def create_pygui_pings_missing_from(self, existing_ping_list: List[PyguiPing]):
            existing_pings_lookup = {p.get_destination(): p for p in existing_ping_list}
            for group in self._groups:
                for ip in group.ips:
                    group.get_pings().append(existing_pings_lookup.get(ip, PyguiPing(ip)))

        def get_all_pygui_pings_from_groups(self) -> List[PyguiPing]:
            pings: List[PyguiPing] = []
            for group in self._groups:
                pings += group.get_pings()
            return pings

        def get_groups(self):
            return self._groups

    def __init__(self, file_name: str):
        self._file_name = file_name
        self.pings: List[PyguiPing] = []
        self._content = pygui.String()
        self._group_manager = IPFileContent.IPGroupManager()

    def get_content(self) -> pygui.String:
        return self._content

    def set_content(self, content: str):
        if content != self._content.value:
            self._content = pygui.String(content, buffer_size=len(content) + 2056)
            self.content_changed()

    def get_group_manager(self) -> IPFileContent.IPGroupManager:
        return self._group_manager

    def content_changed(self):
        self._group_manager = IPFileContent.IPGroupManager()
        for entry in self._content.value.split("\n"):
            if entry == "":
                continue

            elif entry.startswith("#"):
                self._group_manager.start_new_group(entry.lstrip("# "))
                continue

            if "/" in entry:
                try:
                    network = ipaddress.IPv4Network(entry, strict=False)
                    if network.prefixlen < 24:
                        raise ValueError(f"{entry}. Too many hosts. Limit /24")
                    self._group_manager.add_ips([str(ip) for ip in network.hosts()])
                except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError) as e:
                    print(e)
            else:
                self._group_manager.add_ip(entry)

        self._group_manager.finish_creating_groups()
        self._group_manager.create_pygui_pings_missing_from(self.pings)
        self.pings = self._group_manager.get_all_pygui_pings_from_groups()

    def get_filename(self) -> str:
        return self._file_name

    def get_longest_found_destination_name(self) -> int:
        longest = 0
        for ping in self.pings:
            longest = max(
                longest,
                pygui.calc_text_size(ping.get_found_destination() or "")[0] + 10
            )
        return longest

    def get_groups(self) -> List[IPGroup]:
        return self._group_manager.get_groups()


class PingApp:
    colour_success =           pygui.Vec4(0, 0.8, 0, 1)
    colour_success_low_ping =  pygui.Vec4(0, 1, 0, 1)
    colour_success_high_ping = pygui.Vec4(1, 1, 1, 1)
    colour_timeout =           pygui.Vec4(1, 0, 0, 1)
    colour_destination_unreachable =  pygui.Vec4(1, 1, 0, 1)
    colour_host_unknown =   pygui.Vec4(0, 0, 1, 1)
    IPS_DIRECTORY = "ips"

    def __init__(self):
        self.current_time = time.time()
        self.play_all = pygui.Bool(True)
        self.width_multiplier = pygui.Int(5)

        self.file_list = []
        self.selected_files: Dict[str, pygui.Bool] = {}
        self.loaded_contents: List[IPFileContent] = []

        self.is_currently_renaming = None
        self.renaming_site = pygui.String()
        self.is_currently_adding_site = False
        self.adding_site = pygui.String()
        self.deleting_site_modal = pygui.Bool(False)
        self.file_currently_deleting: Optional[str] = None
        self.scroll_amount = pygui.Float(0)
        self.scroll_is_locked = pygui.Bool(True)
        self.scroll_max = pygui.Float(0)

        self.ping_logger = PingLogger()
        self.use_logging = pygui.Bool(False)
        self.use_logging_clicked_time = time.time()
        self.rolling_buffer_changed_timer = 120
        self.use_rolling_buffer = pygui.Bool(False)
        self.rolling_buffer_seconds = pygui.Int(600)
        self.ping_interval_seconds = pygui.Int(3) # Clamps to [1, 10]
        self.ping_interval_frames_to_wait = 0
        self.battery_saving_mode = pygui.Bool(False)
        self.extend_ping_by_x_pixels = pygui.Int(1)
        self.source_address_for_pings = pygui.String("")

    def refresh_ip_folder(self):
        if not os.path.exists(PingApp.IPS_DIRECTORY):
            os.makedirs(PingApp.IPS_DIRECTORY)

        self.file_list = os.listdir(PingApp.IPS_DIRECTORY)

        # Keep only the files that have the .txt extension
        def ignore_readme(file_name_with_ext: str):
            _, ext = os.path.splitext(file_name_with_ext)
            return ext != ".md"
        self.file_list = list(filter(ignore_readme, self.file_list))

        # Only keep the files that are in the list
        seen_files: Dict[str, pygui.Bool] = {}
        for file in self.file_list:
            seen_files[file] = self.selected_files.get(file) or pygui.Bool(False)
        self.selected_files = seen_files

    def load_contents_from_selected_files(self):
        existing_file_content = {c.get_filename(): c for c in self.loaded_contents}
        content_to_keep: List[IPFileContent] = []
        for file, is_selected in self.selected_files.items():
            if not is_selected:
                continue

            file_content = existing_file_content.get(file) or IPFileContent(file)
            with open(os.path.join(PingApp.IPS_DIRECTORY, file), encoding="utf-8") as f:
                file_content.set_content(f.read())

            content_to_keep.append(file_content)
        self.loaded_contents = content_to_keep

    def draw_ping_list(self):
        do_reload = False

        if pygui.get_frame_count() % 120 == 1:
            do_reload = True
            self.refresh_ip_folder()

        pygui.separator_text("Ping Lists")
        for file, is_selected in self.selected_files.items():
            if pygui.small_button("/###Rename button " + file):
                self.is_currently_renaming = file
                self.renaming_site = pygui.String(file)
                pygui.set_keyboard_focus_here()
            pygui.same_line()

            if self.is_currently_renaming == file:
                if pygui.is_key_pressed(pygui.KEY_ESCAPE):
                    self.is_currently_renaming = None

                if pygui.input_text("###Renaming file", self.renaming_site, pygui.INPUT_TEXT_FLAGS_ENTER_RETURNS_TRUE):
                    try:
                        os.rename(
                            os.path.join(PingApp.IPS_DIRECTORY, file),
                            os.path.join(PingApp.IPS_DIRECTORY, self.renaming_site.value)
                        )
                        self.refresh_ip_folder()
                    except IOError as e:
                        print(f"Failed to rename {file}: {e}")
                    self.is_currently_renaming = None
            else:
                do_reload = pygui.selectable_bool_ptr(file, is_selected, pygui.SELECTABLE_FLAGS_ALLOW_OVERLAP) or do_reload

            pygui.same_line(pygui.get_content_region_avail()[0] - 15)
            if pygui.small_button("x###Delete button " + file):
                self.file_currently_deleting = file
                self.deleting_site_modal.value = True
                pygui.open_popup("Delete List")

        self.draw_add_site_area()

        if pygui.begin_popup_modal("Delete List", self.deleting_site_modal):
            pygui.text("Are you sure you want to delete:")
            pygui.text("{}".format(self.file_currently_deleting))
            if pygui.button("Confirm"):
                os.remove(os.path.join(PingApp.IPS_DIRECTORY, self.file_currently_deleting))
                self.deleting_site_modal.value = False
                self.refresh_ip_folder()
            pygui.same_line()
            if pygui.button("Cancel") or pygui.is_key_pressed(pygui.KEY_ESCAPE):
                self.deleting_site_modal.value = False
            pygui.end_popup()

        if do_reload:
            self.load_contents_from_selected_files()

    def draw_editor_window(self):
        if pygui.begin_tab_bar("###Editor tabs"):
            for loaded_content in self.loaded_contents:
                if pygui.begin_tab_item(loaded_content.get_filename()):
                    contents_buf = loaded_content.get_content()

                    has_changed = pygui.input_text_multiline(
                        "###Editor",
                        contents_buf,
                        pygui.get_content_region_avail(),
                    )
                    if has_changed:
                        with open(os.path.join(PingApp.IPS_DIRECTORY, loaded_content.get_filename()), "w", encoding="utf-8") as f:
                            f.write(contents_buf.value)
                        loaded_content.content_changed()

                    pygui.end_tab_item()
            pygui.end_tab_bar()

    def draw_add_site_area(self):
        if not self.is_currently_adding_site:
            self.is_currently_adding_site = pygui.button(" + ")
            pygui.same_line()
            if pygui.button("Open Folder"):
                os.startfile(os.path.abspath(PingApp.IPS_DIRECTORY))

        if self.is_currently_adding_site:
            if pygui.is_key_pressed(pygui.KEY_ESCAPE):
                self.is_currently_adding_site = False
                return

            pygui.set_keyboard_focus_here()
            if not pygui.input_text("###Adding new site", self.adding_site, pygui.INPUT_TEXT_FLAGS_ENTER_RETURNS_TRUE):
                return
            self.is_currently_adding_site = False

            if not os.path.exists(os.path.join(PingApp.IPS_DIRECTORY, self.adding_site.value)):
                with open(os.path.join(PingApp.IPS_DIRECTORY, self.adding_site.value), "w", encoding="utf-8") as f:
                    f.write("")
                self.adding_site.value = ""
                self.refresh_ip_folder()

    def get_destination_padding(self) -> int:
        longest = 0
        for content in self.loaded_contents:
            longest = max(longest, content.get_longest_found_destination_name())
        return longest

    def draw_live_graph(self):
        if pygui.tree_node("Settings"):
            pygui.push_item_width(100)
            pygui.input_int("Width Multiplier", self.width_multiplier)
            pygui.pop_item_width()
            self.width_multiplier.value = clamp(self.width_multiplier.value, 1, math.inf)

            if pygui.checkbox("Enable Logging", self.use_logging):
                self.use_logging_clicked_time = time.time()

            pygui.same_line()
            help_marker("Saves results to logging/<file>/<group>/<host> as a csv")
            pygui.same_line()
            if pygui.button("Open folder"):
                # Windows only
                os.startfile(os.path.abspath(self.ping_logger.get_logging_directory()))

            pygui.checkbox("Enable Rolling Buffer", self.use_rolling_buffer)
            pygui.same_line()
            pygui.push_item_width(100)
            did_change = pygui.input_int("seconds###Rolling Buffer seconds", self.rolling_buffer_seconds)
            if did_change:
                self.rolling_buffer_changed_timer = 120
            pygui.pop_item_width()
            pygui.same_line()
            help_marker("May improve performance for longer sessions. Consider " + \
                        "enabling logging if you need a lot of data")
            pygui.same_line()
            pygui.text_disabled("{}/{}".format(int(time.time() - self.current_time), self.rolling_buffer_seconds.value))

            pygui.push_item_width(100)
            pygui.input_int("Ping interval", self.ping_interval_seconds)
            pygui.pop_item_width()
            self.ping_interval_seconds.value = clamp(self.ping_interval_seconds.value, 1, 10)
            pygui.same_line()
            cx, cy = pygui.get_cursor_screen_pos()
            dl = pygui.get_window_draw_list()
            dl.path_arc_to(
                (cx + 10, cy + pygui.get_text_line_height_with_spacing()/2),
                pygui.get_text_line_height() / 2,
                0,
                math.radians((1 - (self.ping_interval_frames_to_wait / (self.ping_interval_seconds.value * 60))) * -360)
            )
            dl.path_stroke(
                pygui.Vec4(0.5, 0.5, 0.5, 1).to_u32(),
                0,
                2
            )
            pygui.dummy((pygui.get_text_line_height(), pygui.get_text_line_height()))
            pygui.push_item_width(100)
            pygui.input_int("Extend ping by (px)", self.extend_ping_by_x_pixels)
            pygui.pop_item_width()
            pygui.checkbox("Battery Saving Mode", self.battery_saving_mode)
            pygui.same_line()
            help_marker("Adds a time.sleep() to the main loop to decrease FPS. " + \
                        "Can reduce the app's CPU usage by up to 90%. But by " + \
                        "roughly 50% if lots of pings are running")
            pygui.push_item_width(120)
            pygui.input_text("Ping source address", self.source_address_for_pings)
            pygui.pop_item_width()
            pygui.same_line()
            help_marker("The source IP for the ping. Can usually be left blank")
            pygui.tree_pop()

        if self.use_logging and pygui.get_frame_count() % 60 - 30 == 0:
            time_to_save = time.time()
            when_logging_clicked_str = datetime.datetime.fromtimestamp(self.use_logging_clicked_time).strftime(r"%d-%m-%Y")
            for file_contents in self.loaded_contents:
                for group in file_contents.get_groups():
                    for ping in group.get_pings():
                        path = [
                            "{} {}.csv".format(file_contents.get_filename(), when_logging_clicked_str),
                        ]
                        self.ping_logger.log_replies_single_file(path, ping.get_replies())

            self.ping_logger.set_last_time_synced(time_to_save)

        # Delete any pings below the rolling buffer
        self.rolling_buffer_changed_timer -= 1
        if self.use_rolling_buffer and self.rolling_buffer_changed_timer < 0:
            if (time.time() - self.current_time) > self.rolling_buffer_seconds.value:
                self.current_time = time.time() - self.rolling_buffer_seconds.value

        if pygui.get_frame_count() % 120 == 0 and self.rolling_buffer_changed_timer < 0:
            for file_contents in self.loaded_contents:
                for group in file_contents.get_groups():
                    for ping in group.get_pings():
                        ping.clear_before(self.current_time)

        # Window widgets
        is_play_all = pygui.Bool(False)
        for content in self.loaded_contents:
            for group in content.get_groups():
                for ping in group.get_pings():
                    if ping.get_running_bool():
                        is_play_all = pygui.Bool(True)
                        break
        if pygui.checkbox("###Play All", is_play_all):
            for content in self.loaded_contents:
                for group in content.get_groups():
                    for ping in group.get_pings():
                        ping.set_running(is_play_all)

        pygui.same_line()

        if did_clear := pygui.button("Clear"):
            self.current_time = time.time()

        pygui.same_line()
        pygui.text("FPS: {:.1f}".format(pygui.get_io().framerate))
        pygui.same_line()
        pygui.text_disabled("({}/{}) {}".format(
            int(self.scroll_amount.value),
            int(self.scroll_max.value),
            "Following" if self.scroll_is_locked else "Scrolling"
        ))
        pygui.separator()

        if len(self.loaded_contents) == 0:
            self.current_time = time.time()

        # Since we are creating each of the ping bars separately, how we
        # handle scrolling has to be done manually. Essentially we set
        # each childs scroll to be the "scroll_amount". This value is
        # clamped by [0, scroll_max]. Scroll_max is calculated each
        # frame; the furthest the first item can scroll. We manually
        # scroll the window with:
        #   pygui.get_io().mouse_wheel_h * SCROLL_SPEED_MULT
        # If the user scrolls completely to the max/right, then the
        # scroll will "lock" causing the scroll to follow the max.
        SCROLL_SPEED_MULT = 15
        scroll_wheel_movement = 0
        if pygui.is_window_hovered(pygui.HOVERED_FLAGS_CHILD_WINDOWS):
            scroll_wheel_movement = pygui.get_io().mouse_wheel_h * SCROLL_SPEED_MULT
        self.scroll_amount.value -= scroll_wheel_movement
        self.scroll_amount.value = clamp(self.scroll_amount.value, 0, self.scroll_max.value)

        if scroll_wheel_movement != 0:
            if abs(self.scroll_amount.value - self.scroll_max.value) - 1 < 0:
                self.scroll_is_locked = pygui.Bool(True)
            else:
                self.scroll_is_locked = pygui.Bool(False)

        if self.scroll_is_locked:
            self.scroll_amount.value = self.scroll_max.value
        self.scroll_max.value = 0 # Calculated each frame

        latest_reply = time.time()

        # Ping interval calculation
        should_ping = False
        self.ping_interval_frames_to_wait -= 1
        if self.ping_interval_frames_to_wait <= 0:
            self.ping_interval_frames_to_wait = self.ping_interval_seconds.value * 60
            should_ping = True

        # Battery saving mode
        if self.battery_saving_mode:
            time.sleep((3 / 60)) # Sleep for 3 frames

        for file_contents in self.loaded_contents:
            graphing_height = pygui.get_frame_height()
            normal_item_padding = pygui.get_style().item_inner_spacing
            normal_window_padding = pygui.get_style().window_padding

            # Following the RHS so that it auto-scrolls. Currently broken
            # since scrolling does not working like it used to.
            if did_clear:
                for group in file_contents.get_group_manager().get_groups():
                    group.clear_pings()

            for i, group in enumerate(file_contents.get_groups()):
                if len(group) == 0:
                    continue
                pygui.push_id(i)

                group_tree_label = group.get_group_name() or file_contents.get_filename()
                at_least_one_ping_running_in_group = pygui.Bool(False)
                for ping in group.get_pings():
                    if ping.get_running_bool():
                        at_least_one_ping_running_in_group = pygui.Bool(True)
                        break

                # Do this outside of the drawing loop to ensure that the tick still
                # occurs regardless of visibility
                for i, ping in enumerate(group.get_pings()):
                    ping.draw(should_ping, self.source_address_for_pings.value)

                pygui.push_style_var(pygui.STYLE_VAR_INDENT_SPACING, 24)


                # Hack that makes the tree nodes taller
                if pygui.button(f"Clear###clear {group_tree_label} {file_contents.get_filename()}"):
                    group.clear_pings()
                pygui.same_line()
                if pygui.tree_node(group_tree_label, pygui.TREE_NODE_FLAGS_DEFAULT_OPEN):
                    # Group Widgets
                    if pygui.checkbox(f"###Play Group{group_tree_label} {file_contents.get_filename()}", at_least_one_ping_running_in_group):
                        for ping in group.get_pings():
                            ping.set_running(at_least_one_ping_running_in_group)
                    # pygui.same_line()

                    for i, ping in enumerate(group.get_pings()):
                        pygui.checkbox(f"###Play {i}", ping.get_running_bool())
                        pygui.same_line()
                        pygui.checkbox(f"###Show window {i}", ping.get_is_window_visible_bool())
                        pygui.same_line()
                        first_part = pygui.get_cursor_pos_x()

                        pygui.text(ping.get_found_destination())
                        pygui.same_line(self.get_destination_padding() + first_part + 10)

                        draw_list = pygui.get_window_draw_list()
                        cx, cy = pygui.get_cursor_screen_pos()
                        draw_list.add_rect(
                            (cx, cy),
                            (cx + pygui.get_content_region_avail()[0], cy + pygui.get_frame_height_with_spacing()),
                            pygui.color_convert_float4_to_u32((0.2, 0.2, 0.2, 1)),
                        )
                        draw_list.push_clip_rect(
                            (cx, cy),
                            (cx + pygui.get_content_region_avail()[0], cy + pygui.get_frame_height_with_spacing()),
                            True
                        )

                        pygui.push_style_var(pygui.STYLE_VAR_WINDOW_PADDING,   (0, 0))
                        pygui.push_style_var(pygui.STYLE_VAR_ITEM_SPACING,     (0, pygui.get_style().item_inner_spacing[1]))
                        pygui.push_style_var(pygui.STYLE_VAR_FRAME_PADDING,    (0, 0))
                        pygui.push_style_var(pygui.STYLE_VAR_FRAME_BORDER_SIZE, 0)

                        pygui.set_next_window_scroll((self.scroll_amount.value, -1))

                        pygui.begin_child(
                            f"Graphing area ### {i} {group_tree_label} {file_contents.get_filename()}",
                            (-1, graphing_height),
                            # pygui.CHILD_FLAGS_BORDER
                        )

                        # The maximum scroll is determined by the longest of all
                        # pygui.begin_child windows.
                        self.scroll_max = pygui.Float(max(
                            self.scroll_max.value,
                            pygui.get_scroll_max_x()
                        ))

                        last_draw_time = self.current_time
                        for j, reply in enumerate(ping):
                            if j > 0:
                                pygui.same_line()

                            if reply.reply_type is Ping.ReplyType.Success:
                                if reply.response_time > 100: # 100ms
                                    colour = PingApp.colour_success_high_ping.to_u32()
                                elif reply.response_time > 20: # 100ms
                                    colour = PingApp.colour_success.to_u32()
                                else:
                                    colour = PingApp.colour_success_low_ping.to_u32()
                            elif reply.reply_type is Ping.ReplyType.DestinationUnreachable:
                                colour = PingApp.colour_destination_unreachable.to_u32()
                            elif reply.reply_type is Ping.ReplyType.HostUnknown:
                                colour = PingApp.colour_host_unknown.to_u32()
                            else:
                                colour = PingApp.colour_timeout.to_u32()

                            gap_width = reply.start_time - last_draw_time
                            pygui.dummy((gap_width * self.width_multiplier.value, pygui.get_content_region_avail()[1]))
                            last_draw_time = reply.start_time

                            pygui.same_line()

                            ping_width = reply.end_time - last_draw_time
                            last_draw_time = reply.end_time
                            pygui.dummy((ping_width * self.width_multiplier.value, pygui.get_content_region_avail()[1]))

                            item_max = pygui.get_item_rect_max()
                            draw_list.add_rect_filled(
                                pygui.get_item_rect_min(),
                                (
                                    item_max[0] + self.extend_ping_by_x_pixels.value,
                                    item_max[1] + 3
                                ),
                                colour,
                            )

                            pygui.push_style_var(pygui.STYLE_VAR_ITEM_SPACING, normal_item_padding)
                            pygui.push_style_var(pygui.STYLE_VAR_WINDOW_PADDING, normal_window_padding)
                            if pygui.is_item_hovered() and pygui.begin_tooltip():
                                start_time = datetime.datetime.fromtimestamp(int(reply.start_time))
                                pygui.text(start_time.strftime("%a %d/%m/%Y @ %H:%M:%S%p"))
                                pygui.push_style_color(pygui.COL_TEXT, colour)
                                pygui.text(f"[{j}] {reply.more_detail_text}")
                                pygui.pop_style_color()
                                pygui.end_tooltip()
                            pygui.pop_style_var(2)

                        # Makes each line the correct length based on time
                        pygui.same_line()
                        GO_AHEAD_BY_SECONDS = 1
                        pygui.dummy(((latest_reply - last_draw_time + GO_AHEAD_BY_SECONDS) * self.width_multiplier.value, 2))
                        draw_list.add_rect_filled(
                            pygui.get_item_rect_min(),
                            pygui.get_item_rect_max(),
                            pygui.Vec4(1, 1, 1, 0.2).to_u32(),
                        )

                        pygui.end_child()
                        pygui.pop_style_var(4)
                        draw_list.pop_clip_rect()
                    pygui.tree_pop()
                pygui.pop_style_var()
                pygui.pop_id()

    def draw_colour_editor(self):
        pygui.color_edit3("Success",   PingApp.colour_success)           # pygui.COLOR_EDIT_FLAGS_NO_INPUTS)
        pygui.color_edit3("High Ping", PingApp.colour_success_high_ping) # pygui.COLOR_EDIT_FLAGS_NO_INPUTS)
        pygui.color_edit3("Timeout",   PingApp.colour_timeout)           # pygui.COLOR_EDIT_FLAGS_NO_INPUTS)

    def draw(self):
        main_viewport = pygui.get_main_viewport()
        id_ = pygui.get_id("Main view")
        ds = pygui.dock_space_over_viewport(id_, main_viewport)

        pygui.set_next_window_dock_id(ds, pygui.COND_FIRST_USE_EVER)
        if pygui.begin("Load IPs", None):
            self.draw_ping_list()
        pygui.end()

        pygui.set_next_window_dock_id(ds, pygui.COND_FIRST_USE_EVER)
        if pygui.begin("Editor"):
            self.draw_editor_window()
        pygui.end()

        pygui.set_next_window_dock_id(ds, pygui.COND_FIRST_USE_EVER)
        if pygui.begin("Live Graph"):
            self.draw_live_graph()
        pygui.end()

        pygui.set_next_window_dock_id(ds, pygui.COND_FIRST_USE_EVER)
        if pygui.begin("Colour editor"):
            self.draw_colour_editor()
        pygui.end()
