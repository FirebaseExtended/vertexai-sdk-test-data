# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This script takes two JSON outputs from `coverage-tool.py` and prints the diff.

import json
from argparse import ArgumentParser
from os.path import isfile
from coverage_tool import NUM_KEYWORD, FILES_KEYWORD, TOTAL_KEYWORD

OLD_KEYWORD = "_old_num"
NEW_KEYWORD = "_new_num"

COLORS = {
    "green": "\033[92m",
    "blue": "\033[94m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "end": "\033[0m",
}

EMOJIS = {
    "green": "✅",
    "blue": "🔵",
    "yellow": "🟡",
    "red": "❌",
}

COLOR_DESC = {
    "green": "total coverage increase",
    "blue": "files number increase, total coverage unaffected",
    "yellow": "files number decrease, total coverage unaffected",
    "red": "total coverage decrease",
}


class DiffCoverage:
    def __init__(self, file1, file2, no_color=False, all_fields=False):
        self.file1 = file1
        self.file2 = file2
        self.no_color = no_color
        self.all_fields = all_fields

    def find_diff(self, old, new):
        """Find the diff between two coverage outputs, returning the old and new
        coverage numbers for each field."""
        assert old.keys() == new.keys(), "Different keys in the coverage output files."
        return {
            key: {
                OLD_KEYWORD: old[key][NUM_KEYWORD],
                NEW_KEYWORD: new[key][NUM_KEYWORD],
                **self.find_diff(old[key], new[key]),
            }
            for key in old
            if key not in {NUM_KEYWORD, FILES_KEYWORD}
        }

    def get_output(self, diff, indent=0):
        """Return the diff to output as a string."""
        output = ""
        for key, value in diff.items():
            if key not in {OLD_KEYWORD, NEW_KEYWORD}:
                percent = "%" if key == TOTAL_KEYWORD else ""
                if value[OLD_KEYWORD] == value[NEW_KEYWORD]:
                    inner_output = self.get_output(value, indent + 1)
                    if inner_output or self.all_fields:
                        output += (
                            "| " * indent
                            + f"{key}: {value[OLD_KEYWORD]}{percent}\n"
                            + inner_output
                        )
                else:
                    if value[OLD_KEYWORD] == 0:
                        color = "green"
                    elif value[NEW_KEYWORD] == 0:
                        color = "red"
                    elif value[OLD_KEYWORD] > value[NEW_KEYWORD]:
                        color = "yellow" if key != TOTAL_KEYWORD else "red"
                    else:
                        color = "blue" if key != TOTAL_KEYWORD else "green"

                    output += (
                        "| " * indent
                        + f"{key}: "
                        + (COLORS[color] if not self.no_color else "")
                        + f"{value[OLD_KEYWORD]}{percent} -> {value[NEW_KEYWORD]}{percent}"
                        + (COLORS["end"] if not self.no_color else f" {EMOJIS[color]}")
                        + "\n"
                        + self.get_output(value, indent + 1)
                    )
        return output

    def get_legend(self):
        """Return a legend for the colors as a string."""
        output = "Legend:\n"
        for color, meaning in COLOR_DESC.items():
            if not self.no_color:
                output += (
                    f"{COLORS[color]}{color.ljust(6)}{COLORS['end']} : {meaning}\n"
                )
            else:
                output += f"{EMOJIS[color]} : {meaning}\n"
        return output

    def main(self):
        diff = self.find_diff(self.file1, self.file2)
        output = self.get_output(diff)
        if output:
            print(output)
            print(self.get_legend(), end="")


def get_args():
    """Parse, validate, and return command line arguments."""

    def read_json(file):
        if not isfile(file):
            parser.error(f"File {file} does not exist.")
        return json.load(open(file))

    parser = ArgumentParser()
    parser.add_argument(
        "file1", metavar="FILE", type=read_json, help="First coverage output in JSON"
    )
    parser.add_argument(
        "file2", metavar="FILE", type=read_json, help="Second coverage output in JSON"
    )
    parser.add_argument(
        "--no-color",
        "-n",
        action="store_true",
        help="Disable color in output and add emojis",
    )
    parser.add_argument(
        "--all-fields",
        "-a",
        action="store_true",
        help="Output all fields, not just the ones with changes",
    )
    return parser.parse_args()


def main():
    args = get_args()
    tool = DiffCoverage(**vars(args))
    tool.main()


if __name__ == "__main__":
    main()
