from __future__ import annotations
import time

from .table import Table

import pygui_cython as pygui


class DNSCacheTable(Table):
    spec = [
        (int, "TTL",            "TTL"),
        (str, "Caption",        "Caption"),
        (str, "Description",    "Description"),
        (str, "ElementName",    "ElementName"),
        (str, "InstanceId",     "InstanceId"),
        (str, "Data",           "Data"),
        (int, "DataLength",     "DataLength"),
        (str, "Entry",          "Entry"),
        (str, "Name",           "Name"),
        (int, "Section",        "Section"),
        (int, "TimeToLive",     "TimeToLive"),
        (int, "Type",           "Type"),
        (int, "PSComputerName", "PSComputerName"),
    ]
    def __init__(self, table_name, data, creation_time: float):
        super().__init__(table_name, DNSCacheTable.spec, data)
        self.creation_time = creation_time

    def TimeToLive(self, dns_entry: dict):
        seconds_since_refresh = round(time.time() - self.creation_time)
        value = max(int(dns_entry["TimeToLive"]) - seconds_since_refresh, 0)
        if value == 0:
            pygui.text_colored((1, 0, 0, 1), "{}".format(value))
        else:
            pygui.text("{}".format(value))
            

    def Type(self, dns_entry: dict):
        lookup = {
            "1": "A Record",
            "5": "CNAME Record",
            "12": "PTR Record",
        }
        pygui.text("{}".format(lookup.get(dns_entry["Type"]) or dns_entry["Type"]))
    
    def merge(self, other: DNSCacheTable, keep_expired: bool):
        if keep_expired:
            final_set = {}
            same_fields_to_be_considered_same = ["Entry", "Name", "Data"]
            for s_row in self.data:
                seconds_since_refresh = round(time.time() - self.creation_time)
                value = max(int(s_row["TimeToLive"]) - seconds_since_refresh, 0)
                s_row["TimeToLive"] = value
                
                final_set[tuple(s_row[field] for field in same_fields_to_be_considered_same)] = s_row
            for o_row in other.data:
                final_set[tuple(o_row[field] for field in same_fields_to_be_considered_same)] = o_row
            self.data = list(final_set.values())
        else:
            self.data = other.data
        self.creation_time = other.creation_time
