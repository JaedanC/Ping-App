from __future__ import annotations
from typing import List, Dict, Set, Any
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

    def draw(self):
        if pygui.get_frame_count() % 60 == 0 and self._do_tick:
            self.tick()

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
                    group._pygui_pings.append(existing_pings_lookup.get(ip, PyguiPing(ip)))
        
        def get_all_pygui_pings_from_groups(self) -> List[PyguiPing]:
            pings: List[PyguiPing] = []
            for group in self._groups:
                pings += group._pygui_pings
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
    colour_success =           pygui.Vec4(0, 1, 0, 1)
    colour_success_high_ping = pygui.Vec4(1, 1, 1, 1)
    colour_timeout =           pygui.Vec4(1, 0, 0, 1)
    colour_host_unreachable =  pygui.Vec4(1, 1, 0, 1)
    colour_general_failure =   pygui.Vec4(0, 0, 1, 1)

    def __init__(self):
        self.current_time = time.time()
        self.play_all = pygui.Bool(True)
        self.follow_scroll = pygui.Bool(True)
        self.previous_frame_scroll = pygui.Int(0)
        self.width_multiplier = pygui.Int(5)

        self.file_list = []
        self.selected_files: Dict[str, pygui.Bool] = {}
        self.loaded_contents: List[IPFileContent] = []

        self.is_currently_renaming = None
        self.renaming_site = pygui.String()
        self.is_currently_adding_site = False
        self.adding_site = pygui.String()
        self.deleting_site_modal = pygui.Bool(False)
        self.is_currently_deleting = None

    
    def refresh_ip_folder(self):
        if not os.path.exists("ips"):
            os.makedirs("ips")

        self.file_list = os.listdir("ips")
        
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
            with open(f"ips/{file}") as f:
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
            # self.load_pings_from_strings()
    
    def draw_editor_window(self):
        if len(self.loaded_contents) == 0:
            return

        loaded = self.loaded_contents[0]
        file = loaded.get_filename()
        contents_buf = loaded.get_content()

        has_changed = pygui.input_text_multiline(
            "###Editor",
            contents_buf,
            pygui.get_content_region_avail(),
        )

        if has_changed:
            with open(f"ips/{file}", "w") as f:
                f.write(contents_buf.value)
            loaded.content_changed()
            # self.load_pings_from_strings()

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
                self.adding_site.value = ""
                self.refresh_ip_folder()

    def get_destination_padding(self) -> int:
        longest = 0
        for content in self.loaded_contents:
            longest = max(longest, content.get_longest_found_destination_name())
        return longest

    def draw_live_graph(self):
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

        if len(self.loaded_contents) == 0:
            self.current_time = time.time()

        for file_contents in self.loaded_contents:
            graphing_height = pygui.get_frame_height()
            normal_item_padding = pygui.get_style().item_inner_spacing
            normal_window_padding = pygui.get_style().window_padding
            
            # Following the RHS so that it auto-scrolls. Currently broken
            # since scrolling does not working like it used to.
            if pygui.get_scroll_x() < self.previous_frame_scroll.value:
                self.follow_scroll.value = False
            elif pygui.get_scroll_x() == pygui.get_scroll_max_x():
                self.follow_scroll.value = True
            if did_clear:
                for group in file_contents._group_manager._groups:
                    group.clear_pings()
            else:
                self.previous_frame_scroll.value = pygui.get_scroll_x()

            for group in file_contents.get_groups():
                if len(group) == 0:
                    continue
                
                group_tree_label = group.get_group_name() or file_contents.get_filename()
                at_least_one_ping_running_in_group = pygui.Bool(False)
                for ping in group.get_pings():
                    if ping.get_running_bool():
                        at_least_one_ping_running_in_group = pygui.Bool(True)
                        break
                
                
                # Do this outside of the drawing loop to ensure that the tick still
                # occurs regardless of visibility
                for i, pw in enumerate(group.get_pings()):
                    pw.draw()

                pygui.push_style_var(pygui.STYLE_VAR_INDENT_SPACING, 24)
                
                # Hack that makes the tree nodes taller
                if pygui.button(f"Clear###clear {group_tree_label} {file_contents.get_filename()}"):
                    group.clear_pings()
                pygui.same_line()
                if pygui.tree_node(group_tree_label, pygui.TREE_NODE_FLAGS_DEFAULT_OPEN):
                    # Group Widgets
                    if pygui.checkbox(f"###Play Group{group_tree_label} {file_contents.get_filename()}", at_least_one_ping_running_in_group):
                        for ping in group._pygui_pings:
                            ping.set_running(at_least_one_ping_running_in_group)
                    # pygui.same_line()
                    
                    for i, pw in enumerate(group.get_pings()):
                        pygui.checkbox(f"###Play {i}", pw.get_running_bool())
                        pygui.same_line()
                        pygui.checkbox(f"###Show window {i}", pw.get_is_window_visible_bool())
                        pygui.same_line()
                        first_part = pygui.get_cursor_pos_x()

                        pygui.text(pw.get_found_destination())
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
                        if len(pw) == 0:
                            pass

                        pygui.push_style_var(pygui.STYLE_VAR_WINDOW_PADDING,   (0, 0))
                        pygui.push_style_var(pygui.STYLE_VAR_ITEM_SPACING,     (0, pygui.get_style().item_inner_spacing[1]))
                        pygui.push_style_var(pygui.STYLE_VAR_FRAME_PADDING,    (0, 0))
                        pygui.push_style_var(pygui.STYLE_VAR_FRAME_BORDER_SIZE, 0)
                        pygui.begin_child(
                            f"Graphing area ### {i} {group_tree_label} {file_contents.get_filename()}",
                            (-1, graphing_height),
                            # pygui.CHILD_FLAGS_BORDER
                        )
                        # pygui.begin_group()
                        last_draw_time = self.current_time
                        for i, reply in enumerate(pw):
                            if i > 0:
                                pygui.same_line()
                            
                            if reply.reply_type is Ping.ReplyType.Success:
                                if reply.response_time > 100: # 100ms
                                    colour = PingApp.colour_success_high_ping.to_u32()
                                else:
                                    colour = PingApp.colour_success.to_u32()
                            elif reply.reply_type is Ping.ReplyType.DestinationHostUnreachable:
                                colour = PingApp.colour_host_unreachable.to_u32()
                            elif reply.reply_type is Ping.ReplyType.DestinationNetUnreachable:
                                colour = PingApp.colour_host_unreachable.to_u32()
                            elif reply.reply_type is Ping.ReplyType.GeneralFailure:
                                colour = PingApp.colour_general_failure.to_u32()
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
                                    item_max[0] + self.width_multiplier.value // 2,
                                    item_max[1] + 3
                                ),
                                colour,
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
                            pygui.pop_style_var(2)
                        
                        # pygui.end_group()
                        pygui.end_child()
                        pygui.pop_style_var(4)
                        draw_list.pop_clip_rect()
                    pygui.tree_pop()
                pygui.pop_style_var()

            if self.follow_scroll:
                pygui.set_scroll_x(pygui.get_scroll_max_x())
    
    def draw_colour_editor(self):
        pygui.color_edit3("Success",       PingApp.colour_success,    )#  pygui.COLOR_EDIT_FLAGS_NO_INPUTS)
        pygui.color_edit3("High Ping", PingApp.colour_success_high_ping)#, pygui.COLOR_EDIT_FLAGS_NO_INPUTS)
        pygui.color_edit3("Timeout",       PingApp.colour_timeout,    )#  pygui.COLOR_EDIT_FLAGS_NO_INPUTS)
        pass

    def draw(self):
        main_viewport = pygui.get_main_viewport()
        ds = pygui.dock_space_over_viewport(main_viewport)

        pygui.set_next_window_dock_id(ds, pygui.COND_FIRST_USE_EVER)
        if pygui.begin("Load IPs"):
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
