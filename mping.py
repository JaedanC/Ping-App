from __future__ import annotations
from typing import List
import os
import time
import ipaddress

from ping_cmd import Ping
import pygui
import datetime


class PyguiPing(Ping):
    def __init__(self, destination: str):
        super().__init__(destination)
        self._is_alive = pygui.Bool(True)
        self._do_tick = pygui.Bool(True)
        self._show_ping_window = pygui.Bool(False)
        self._follow_scroll = pygui.Bool(True)
        self._previous_frame_scroll = 0
        self._show_stats = pygui.Bool(False)

    def pygui_tick(self):
        if pygui.get_frame_count() % 60 == 0 and self._do_tick:
            self.tick()
        self._draw()

    def _draw(self):
        if not self._show_ping_window:
            return
        
        window_animation = "|/-\\"[int(pygui.get_time() / 0.5) % 3]
        window_title = "{} {}###{}".format(
            self.get_found_destination(),
            window_animation if self._do_tick else "",
            self.get_destination(),
        )

        if pygui.begin(window_title, self._show_ping_window):
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
            pygui.begin_child(self.get_found_ip(), (-1, -1), pygui.CHILD_FLAGS_BORDER)

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
                    elif reply.reply_type is Ping.ReplyType.DestinationHostUnreachable:
                        pygui.push_style_color(pygui.COL_TEXT, (1, 1, 0, 1))
                    elif reply.reply_type is Ping.ReplyType.RequestTimedOut:
                        pygui.push_style_color(pygui.COL_TEXT, (1, 0, 0, 1))
                    else:
                        pygui.push_style_color(pygui.COL_TEXT, pygui.get_style_color_vec4(pygui.COL_TEXT))
                    
                    pygui.text("[{}] {}".format(
                        row_n,
                        reply.line
                    ))
                    
                    pygui.pop_style_color()
            clipper.destroy()

            if self._follow_scroll:
                pygui.set_scroll_y(pygui.get_scroll_max_y())
            
            pygui.end_child()
        pygui.end()

    def is_alive(self) -> bool:
        return bool(self._is_alive)


class PingApp:
    def __init__(self):
        self.current_time = time.time()
        self.play_all = pygui.Bool(True)
        self.follow_scroll = pygui.Bool(True)
        self.previous_frame_scroll = 0
        self.width_multiplier = pygui.Int(5)

        self.ip_contents: List[pygui.String] = []
        self.selected_file = None
        self.pings: List[PyguiPing] = []
        self.refresh_file_list()
        self.reload_pings()

    def reload_pings(self):
        self.pings.clear()
        for ping_data in self.file_is_loaded.values():
            if not ping_data["selected"]:
                continue

            self.pings += ping_data["pings"]
    
    def refresh_file_list(self):
        self.file_is_loaded = {}
        for file in os.listdir("ips"):
            with open(f"ips/{file}") as f:
                ips = f.read().split("\n")
                ips = list(filter(lambda x: x != "", ips))
            
            ip_list = []
            for entry in ips:
                if "/" in entry:
                    try:
                        network = ipaddress.IPv4Network(entry, strict=False)
                        if network.prefixlen < 24:
                            raise ValueError(f"{entry}. Too many hosts. Limit /24")
                        ip_list += [str(ip) for ip in network.hosts()]
                    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError) as e:
                        print(e)
                else:
                    ip_list.append(entry)
        
            self.file_is_loaded[file] = {}
            self.file_is_loaded[file]["selected"] = pygui.Bool(False)
            self.file_is_loaded[file]["pings"] = [PyguiPing(ip) for ip in ip_list]
        
        # self.file_is_loaded["Default"]["selected"].value = True
    
    def draw_ip_list(self):
        if pygui.button("Refresh list"):
            self.refresh_file_list()
        pygui.dummy((0, 5))
        pygui.separator_text("Ping Lists")
        do_reload = False
        for file, file_data in self.file_is_loaded.items():
            do_reload = do_reload or pygui.selectable_bool_ptr(file, file_data["selected"])
        
        if do_reload:
            self.reload_pings()

    def draw_live_graph(self):
        if did_clear := pygui.button("Clear"):
            self.current_time = time.time()
            for pw in self.pings:
                pw.clear()
        for pw in self.pings:
            pw.pygui_tick()
        
        pygui.same_line()
        self.play_all.value = any([pw._do_tick.value for pw in self.pings])
        if pygui.checkbox("Play all", self.play_all):
            for pw in self.pings:
                pw._do_tick.value = self.play_all.value
        
        pygui.same_line()
        if self.follow_scroll:
            pygui.text_disabled("Following")
        else:
            pygui.text_disabled("Scrolling")
            pygui.same_line()
            if pygui.button("Reset"):
                self.follow_scroll.value = True

        pygui.same_line()
        pygui.push_item_width(100)
        pygui.input_int("Width", self.width_multiplier)
        pygui.pop_item_width()
        pygui.same_line()
        pygui.text("FPS: {:.1f}".format(pygui.get_io().framerate))

        pygui.begin_group()
        for x, pw in enumerate(self.pings):
            pygui.checkbox(f"###Play {x}", pw._do_tick)
            pygui.same_line()
            pygui.checkbox(f"###Show window {x}", pw._show_ping_window)
            pygui.same_line()
            pygui.text(str(pw.get_found_destination()))
        pygui.end_group()

        pygui.same_line()

        graphing_height = pygui.get_frame_height_with_spacing() * len(self.pings)
        normal_item_padding = pygui.get_style().item_inner_spacing
        normal_window_padding = pygui.get_style().window_padding

        pygui.push_style_var(pygui.STYLE_VAR_WINDOW_PADDING, (0, 0))
        pygui.push_style_var(
            pygui.STYLE_VAR_ITEM_SPACING,
            (0, pygui.get_style().item_inner_spacing[1])
        )
        pygui.begin_child(
            "Graphing area",
            (-1, graphing_height),
            pygui.CHILD_FLAGS_BORDER
        )
        pygui.begin_group()
        
        # Following the RHS so that it auto-scrolls
        if pygui.get_scroll_x() < self.previous_frame_scroll:
            self.follow_scroll.value = False
        elif pygui.get_scroll_x() == pygui.get_scroll_max_x():
            self.follow_scroll.value = True
        if not did_clear:
            self.previous_frame_scroll = pygui.get_scroll_x()


        draw_list = pygui.get_window_draw_list()
        for x, pw in enumerate(self.pings):
            cx, cy = pygui.get_cursor_screen_pos()
            draw_list.add_rect(
                (cx, cy),
                (cx + pygui.get_content_region_avail()[0], cy + pygui.get_frame_height_with_spacing()),
                pygui.color_convert_float4_to_u32((0.2, 0.2, 0.2, 1)),
            )

            if len(pw) == 0:
                pygui.dummy((0, pygui.get_frame_height()))

            last_draw_time = self.current_time
            for i, reply in enumerate(pw):
                if i > 0:
                    pygui.same_line()
                
                if reply.reply_type is Ping.ReplyType.Success:
                    if reply.response_time > 100: # 100ms
                        colour = (1, 1, 1, 1)
                    else:
                        colour = (0, 1, 0, 1)
                elif reply.reply_type is Ping.ReplyType.DestinationHostUnreachable:
                    colour = (1, 1, 0, 1)
                elif reply.reply_type is Ping.ReplyType.DestinationNetUnreachable:
                    colour = (1, 1, 0, 1)
                elif reply.reply_type is Ping.ReplyType.GeneralFailure:
                    colour = (0, 0, 1, 1)
                else:
                    colour = (1, 0, 0, 1)
                
                gap_width = reply.start_time - last_draw_time
                pygui.dummy((gap_width * self.width_multiplier.value, pygui.get_frame_height()))
                last_draw_time = reply.start_time
                
                pygui.same_line()

                ping_width = reply.end_time - last_draw_time
                last_draw_time = reply.end_time
                pygui.dummy((ping_width * self.width_multiplier.value, pygui.get_frame_height()))

                item_max = pygui.get_item_rect_max()
                draw_list.add_rect_filled(
                    pygui.get_item_rect_min(),
                    (
                        item_max[0] + self.width_multiplier.value // 2,
                        item_max[1] + 2
                    ),
                    pygui.color_convert_float4_to_u32(colour),
                )

                pygui.push_style_var(pygui.STYLE_VAR_ITEM_SPACING, normal_item_padding)
                pygui.push_style_var(pygui.STYLE_VAR_WINDOW_PADDING, normal_window_padding)
                if pygui.is_item_hovered() and pygui.begin_tooltip():
                    start_time = datetime.datetime.fromtimestamp(int(reply.start_time))
                    pygui.text(start_time.strftime("%a %d @ %H:%M:%S%p"))
                    pygui.push_style_color(pygui.COL_TEXT, colour)
                    pygui.text(f"[{i}] {reply.line}")
                    pygui.pop_style_color()
                    pygui.end_tooltip()
                pygui.pop_style_var()
                pygui.pop_style_var()


        if self.follow_scroll:
            pygui.set_scroll_x(pygui.get_scroll_max_x())

        pygui.pop_style_var()
        pygui.end_group()
        pygui.end_child()
        pygui.pop_style_var()
    
    def draw_editor_window(self):
        pygui.input_text_multiline("Editor", )

    def draw(self):
        if pygui.begin("Load IPs"):
            self.draw_ip_list()
        pygui.end()

        if pygui.begin("Live Graph"):
            self.draw_live_graph()
        pygui.end()