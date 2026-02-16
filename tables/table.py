from abc import ABC
from typing import List, Any
import pygui
from helper import negated, none_compare, parse_filter_string


class Table(ABC):
    """
    An abstracted Pygui table that can handle sorting, filtering, and rendering
    of the table.
    """
    def __init__(
            self,
            table_name: str,
            fields_spec: List[tuple],
            data: List[dict]
        ):
        """
        e.g.
        fields_spec = [
            (str, "name",   "Name"),
            (str, "serial", "Serial"),
            (str, "mac",    "MAC"),
        ]
        """
        self.table_name = table_name
        self.fields_spec = fields_spec
        self.data = data
        self.filtered_data = data
        self.flags = \
            pygui.TABLE_FLAGS_RESIZABLE | \
            pygui.TABLE_FLAGS_REORDERABLE | \
            pygui.TABLE_FLAGS_HIDEABLE | \
            pygui.TABLE_FLAGS_SORTABLE | \
            pygui.TABLE_FLAGS_SORT_MULTI | \
            pygui.TABLE_FLAGS_ROW_BG | \
            pygui.TABLE_FLAGS_SCROLL_Y | \
            pygui.TABLE_FLAGS_SCROLL_X


    def __len__(self) -> int:
        return len(self.data)


    def _custom_key(self, element: dict):
        sort_specs = pygui.table_get_sort_specs()
        sort_with = []
        for sort_spec in sort_specs.specs:
            element_type = self.fields_spec[sort_spec.column_index][0] # str, int, float, IPv4Address
            field        = self.fields_spec[sort_spec.column_index][1] # name, serial, mac
            compare_obj = element.get(field)

            # Massage the data

            if compare_obj is None:
                compare_obj = none_compare()
            else:
                compare_obj = element_type(compare_obj)

            if sort_spec.sort_direction == pygui.SORT_DIRECTION_DESCENDING:
                compare_obj = negated(compare_obj)
            sort_with.append(compare_obj)

        # Add a default sorting method
        sort_with.append(element[self.fields_spec[0][1]])
        return tuple(sort_with)


    def sort(self):
        self.data.sort(key=self._custom_key)
        self.filtered_data.sort(key=self._custom_key)


    def draw(self, force_sort=False):
        """
        Draw the table. Requires all rows to have the same height. Make sure no
        text includes newlines. If rows have unequal heights and the number of
        rows is short, consider using `.draw_unequal_height()`.
        """
        if len(self.data) == 0:
            return

        if pygui.begin_table(self.table_name, len(self.fields_spec), self.flags):
            # Declare columns
            for _, api_column_name, column_name in self.fields_spec:
                pygui.table_setup_column(column_name if len(self.filtered_data) == len(self.data) else f"{column_name} ({api_column_name})")
            pygui.table_setup_scroll_freeze(0, 1) # Make row always visible
            pygui.table_headers_row()

            if (sort_specs := pygui.table_get_sort_specs()):
                if sort_specs.specs_dirty or force_sort:
                    self.sort()
                sort_specs.specs_dirty = False

            # Demonstrate using clipper for large vertical lists
            clipper: pygui.ImGuiListClipper = pygui.ImGuiListClipper.create()

            # This is our first example of not being able to share heap objects
            # across the dll. I need to get a pointer to a valid type that it
            # creates, not me. This requires adding a custom constructor and
            # destructor for the ImGuiListClipper class.
            clipper.begin(len(self.filtered_data))
            while clipper.step():
                for i in range(clipper.display_start, clipper.display_end):
                    # Display a data item
                    element = self.filtered_data[i]
                    pygui.push_id(element[self.fields_spec[0][1]])
                    pygui.table_next_row()

                    for _, field, column_name in self.fields_spec:
                        pygui.table_next_column()

                        custom_getter = getattr(self, field, None)
                        if custom_getter is None:
                            pygui.text_unformatted(element.get(field, "") or "")
                        else:
                            custom_getter(element)

                    pygui.pop_id()
            clipper.destroy()
            pygui.end_table()


    def draw_unequal_height(self):
        """
        This function draws the table, but enables row to have differing heights,
        at the expense of extra computation due to not using ImguiListClipper.
        Thus, unless there is a requirement for multi-height rows, use `.draw()`
        instead. Since this function must "submit" every row, consider the
        length of the table being drawn.
        """
        if pygui.begin_table(self.table_name, len(self.fields_spec), self.flags):
            # Declare columns
            for _, _, column_name in self.fields_spec:
                pygui.table_setup_column(column_name)
            pygui.table_setup_scroll_freeze(0, 1) # Make row always visible
            pygui.table_headers_row()

            if (sort_specs := pygui.table_get_sort_specs()):
                if sort_specs.specs_dirty:
                    self.sort()
                sort_specs.specs_dirty = False

            for element in self.data:
                pygui.push_id(element[self.fields_spec[0][1]])
                pygui.table_next_row()

                for _, field, column_name in self.fields_spec:
                    pygui.table_next_column()

                    custom_getter = getattr(self, field, None)
                    if custom_getter is None:
                        pygui.text_unformatted(element.get(field, "") or "")
                    else:
                        custom_getter(element)

                pygui.pop_id()
            pygui.end_table()


    def reapply_filter(self, filter_string: str, default_field: None):
        """
        Call this function when you have a new filter string that you would like
        to use. This allows you to avoid parsing the string and filtering every
        frame which is wasteful.
        """
        parsed_tokens = parse_filter_string(filter_string)
        default_field = default_field or self.fields_spec[0][1]

        def _are_equal(t: str, cell: Any):
            return t.lower() in str(cell or "").lower()

        refiltered_data = self.data
        for token, token_data in parsed_tokens.items():
            if token == "_default":
                refiltered_data = filter(lambda row, tk=token_data: any([_are_equal(val, row.get(default_field, "")) for val in tk["value"]]), refiltered_data)

            if token_data.get("type") == "normal":
                refiltered_data = filter(lambda row, t=token, tk=token_data: any([_are_equal(val, row.get(t, "")) for val in tk["value"]]), refiltered_data)

            if token_data.get("type") == "negated":
                refiltered_data = filter(lambda row, t=token, tk=token_data: all([_are_equal(val, row.get(t, "")) for val in tk["value"] if val != ""]), refiltered_data)

        self.filtered_data = list(refiltered_data)
