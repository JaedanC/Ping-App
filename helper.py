from typing import Tuple

def clamp(value, lower_bound, upper_bound):
    if value < lower_bound:
        return lower_bound
    if value > upper_bound:
        return upper_bound
    return value


def lerp(ps: Tuple[int, int], pe: Tuple[int, int], percent: float) -> Tuple[int, int]:
    return (
        ps[0] + (pe[0] - ps[0]) * percent,
        ps[1] + (pe[1] - ps[1]) * percent,
    )


def parse_filter_string(filter_string: str) -> dict:
    """
    Returns a dictionary of tokens in this format:


    e.g. `Hello name:Jimmy status!lawyer brother:Chuck`

    ```json
    {
        "_default": {
            "value": [
                "Hello"
            ]
        },
        "name": {
            "type": "normal",
            "value": [
                "Jimmy"
            ]
        },
        "status": {
            "type": "negated",
            "value": [
                "lawyer"
            ]
        },
        "brother": {
            "type": "normal",
            "value": [
                "Chuck"
            ]
        }
    }
    ```
    """
    def smart_split(s: str, delimiter: str, maxsplit=-1):
        """
        Allows for the use of quotation marks to includes spaces and the
        delimiter in values
        """
        tokens = []
        current_token = ""
        inside_quotation = False
        for char in s:
            if char == '"':
                inside_quotation = not inside_quotation

            if char == delimiter and not inside_quotation and maxsplit != 0:
                maxsplit -= 1
                tokens.append(current_token)
                current_token = ""
                continue

            if char != '"':
                current_token += char

        tokens.append(current_token)

        return tokens

    parsed_tokens = {}
    tokens = smart_split(filter_string.strip(), " ")
    for token in tokens:
        if ":" in token:
            subheading, value = smart_split(token, ":", maxsplit=1)
            parsed_tokens[subheading] = {
                "type": "normal",
                "value": value.split("|"),
            }
        elif "!" in token:
            subheading, value = smart_split(token, "!", maxsplit=1)
            parsed_tokens[subheading] = {
                "type": "negated",
                "value": value.split("|"),
            }
        else:
            if "_default" not in parsed_tokens:
                parsed_tokens["_default"] = {"value": []}


            parsed_tokens["_default"]["value"].append(token)
    return parsed_tokens


class negated:
    def __init__(self, obj):
        self.obj = obj

    def __eq__(self, other):
        return other.obj == self.obj

    def __lt__(self, other):
        return other.obj < self.obj


class none_compare:
    def __eq__(self, other):
        return False

    def __lt__(self, other):
        # False: Sorting from lowest to highest makes this the last element in
        # the list.
        return False

    def __gt__(self, other):
        return not self.__lt__(other)
