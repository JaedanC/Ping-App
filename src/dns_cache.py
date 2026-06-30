import csv
import json
import math
import re
import subprocess
import time
from io import StringIO
from threading import Thread, Lock

from .tables.dns_cache_table import DNSCacheTable

import pygui_cython as pygui


class DNSCache:
    def __init__(self):
        self.reset_wait_time = 120
        self.dns_table = None
        self.dns_table = DNSCacheTable("DNS Cache", [], time.time())
        self.did_refresh = False
        self.t_refreshing = False
        self.filter_text = pygui.String("")
        self.t_lock = Lock()
        self.keep_expired = pygui.Bool(True)

    def _thread_refresh(self):
        result = subprocess.run(
            ["powershell.exe", "./dns_cmd.ps1"],
            capture_output=True,
            text=True,
        )
        data = result.stdout
        powershell_dns_cache = [{k: v for k, v in row.items()} for row in csv.DictReader(StringIO(data))]
        dns_table = DNSCacheTable("DNS Cache", powershell_dns_cache, time.time())
        with self.t_lock:
            self.dns_table.merge(dns_table, self.keep_expired.value)
        self.did_refresh = True
        self.t_refreshing = False

    def refresh(self):
        if not self.t_refreshing:
            self.t_refreshing = True
            self.t = Thread(target=self._thread_refresh)
            self.t.start()

    def draw(self):
        if pygui.get_frame_count() % self.reset_wait_time == 0:
            self.refresh()

        pygui.checkbox("Keep expired", self.keep_expired)

        cx, cy = pygui.get_cursor_screen_pos()
        dl = pygui.get_window_draw_list()
        dl.path_arc_to(
            (cx + 10, cy + pygui.get_text_line_height_with_spacing()/2),
            pygui.get_text_line_height() / 2,
            0,
            math.radians((1 - ((pygui.get_frame_count() % self.reset_wait_time) / self.reset_wait_time)) * -360)
        )
        dl.path_stroke(
            pygui.Vec4(0.5, 0.5, 0.5, 1).to_u32(),
            0,
            2
        )
        pygui.dummy((pygui.get_text_line_height(), pygui.get_text_line_height()))
        pygui.same_line()

        with self.t_lock:
            if pygui.button("Clear###DNS Cache Clear"):
                self.dns_table.data.clear()
                self.did_refresh = True
            
            if pygui.input_text("Filter", self.filter_text) or self.did_refresh:
                self.dns_table.reapply_filter(self.filter_text.value, default_field="Entry")

            if pygui.begin_child("DNS Cache", pygui.get_content_region_avail()):
                self.dns_table.draw(force_sort=self.did_refresh)
                self.did_refresh = False
            pygui.end_child()
        
        # fqdns = list(self.cache.keys())
        # fqdns.sort()
        # for fqdn in fqdns:
        #     dns_results = self.cache[fqdn]
        #     if pygui.tree_node(fqdn):
        #         for result in dns_results:
        #             for key, value in result.items():
        #                 pygui.text("{}: {}".format(key, value))
        #             pygui.separator()
        #         pygui.tree_pop()

    # def __str__(self):
    #     return json.dumps(self.cache, indent=4)