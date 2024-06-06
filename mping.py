from __future__ import annotations
from typing import List, Dict
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

        self.file_list = []
        self.selected_files: Dict[str, pygui.Bool] = {}
        self.selected_files_contents: Dict[str, pygui.String] = {}

        self.selected_file = None
        self.pings: List[PyguiPing] = []

        self.is_currently_renaming = None
        self.renaming_site = pygui.String()
        self.is_currently_adding_site = False
        self.adding_site = pygui.String()
        self.deleting_site_modal = pygui.Bool(False)
        self.is_currently_deleting = None
    
    def refresh_ip_folder(self):
        self.file_list = os.listdir("ips")
        
        # Only keep the files that are in the list
        seen_files: Dict[str, pygui.Bool] = {}
        for file in self.file_list:
            seen_files[file] = self.selected_files.get(file) or pygui.Bool(False)
        self.selected_files = seen_files
    
    def load_contents_from_selected_files(self):
        self.selected_files_contents.clear()
        for file, is_selected in self.selected_files.items():
            if not is_selected:
                continue

            with open(f"ips/{file}") as f:
                contents = f.read()
                self.selected_files_contents[file] = pygui.String(contents, buffer_size=len(contents)+2048)
    
    def load_pings_from_strings(self):
        new_pings = []
        for contents in self.selected_files_contents.values():
            contents: pygui.String
            for entry in contents.value.split("\n"):
                if entry == "":
                    continue

                if "/" in entry:
                    try:
                        network = ipaddress.IPv4Network(entry, strict=False)
                        if network.prefixlen < 24:
                            raise ValueError(f"{entry}. Too many hosts. Limit /24")
                        new_pings += [str(ip) for ip in network.hosts()]
                    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError) as e:
                        print(e)
                else:
                    new_pings.append(entry)
        
        old_pings_lookup = {p.get_destination(): p for p in self.pings}

        new_pings_while_keeping_old = []
        for new_ping in new_pings:
            existing_ping = old_pings_lookup.get(new_ping)
            new_pings_while_keeping_old.append(existing_ping if existing_ping is not None else PyguiPing(new_ping))
        self.pings = new_pings_while_keeping_old 
    
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
                    print("Rename", file, "to", self.renaming_site.value)
                    self.is_currently_renaming = None
            else:
                do_reload = pygui.selectable_bool_ptr(file, is_selected, pygui.SELECTABLE_FLAGS_ALLOW_OVERLAP) or do_reload
            
            pygui.same_line(pygui.get_content_region_avail()[0] - 15)
            if pygui.small_button("x###Delete button " + file):
                self.is_currently_deleting = file
                self.deleting_site_modal.value = True
                pygui.open_popup("Delete List")

        self.draw_add_site_area()

        if pygui.begin_popup_modal("Delete List", self.deleting_site_modal):
            pygui.text("Are you sure you want to delete:")
            pygui.text("{}".format(self.is_currently_deleting))
            if pygui.button("Confirm"):
                os.remove("ips/" + self.is_currently_deleting)
                self.deleting_site_modal.value = False
                self.refresh_ip_folder()
            pygui.same_line()
            if pygui.button("Cancel") or pygui.is_key_pressed(pygui.KEY_ESCAPE):
                self.deleting_site_modal.value = False
            pygui.end_popup()
        
        if do_reload:
            self.load_contents_from_selected_files()
            self.load_pings_from_strings()
    
    def draw_add_site_area(self):
        if not self.is_currently_adding_site:
            self.is_currently_adding_site = pygui.button(" + ")
        
        if self.is_currently_adding_site:
            if pygui.is_key_pressed(pygui.KEY_ESCAPE):
                self.is_currently_adding_site = False
                return
            
            pygui.set_keyboard_focus_here()
            if not pygui.input_text("###Adding new site", self.adding_site, pygui.INPUT_TEXT_FLAGS_ENTER_RETURNS_TRUE):
                return
            self.is_currently_adding_site = False
            
            if not os.path.exists("ips/" + self.adding_site.value):
                with open("ips/" + self.adding_site.value, "w") as f:
                    f.write("")
                
                self.refresh_ip_folder()

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
        if len(self.selected_files_contents) == 0:
            return

        file, contents_buf = list(self.selected_files_contents.items())[0]
        file: str
        contents_buf: pygui.String

        has_changed = pygui.input_text_multiline("Editor", contents_buf, pygui.get_content_region_avail())

        if has_changed:
            with open(f"ips/{file}", "w") as f:
                f.write(contents_buf.value)
            self.load_pings_from_strings()

    def draw(self):
        if pygui.begin("Load IPs"):
            self.draw_ping_list()
        pygui.end()

        if pygui.begin("Editor"):
            self.draw_editor_window()
        pygui.end()

        if pygui.begin("Live Graph"):
            self.draw_live_graph()
        pygui.end()