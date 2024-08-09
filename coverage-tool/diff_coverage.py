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

# Keywords for this script
OLD_KEYWORD = "_old_num"
NEW_KEYWORD = "_new_num"


class DiffCoverage:
    def __init__(self):
        self.args = self.get_args()

    def get_args(self):
        """Parse, validate, and return command line arguments."""

        def read_json(file):
            if not isfile(file):
                parser.error(f"File {file} does not exist.")
            return json.load(open(file))

        parser = ArgumentParser()
        parser.add_argument(
            "file1", metavar="FILE", type=str, help="First coverage output in JSON"
        )
        parser.add_argument(
            "file2", metavar="FILE", type=str, help="Second coverage output in JSON"
        )
        parser.add_argument(
            "--no-color",
            "-n",
            action="store_true",
            help="Disable color in output",
        )
        parser.add_argument(
            "--all-fields",
            "-a",
            action="store_true",
            help="Output all fields, not just the ones with changes",
        )
        args = parser.parse_args()
        args.file1 = read_json(args.file1)
        args.file2 = read_json(args.file2)
        return args

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

    def print_output(self, output, indent=0):
        """Print the diff."""

        def has_changes(field):
            return field[OLD_KEYWORD] != field[NEW_KEYWORD] or any(
                has_changes(value)
                for key, value in field.items()
                if key not in {OLD_KEYWORD, NEW_KEYWORD}
            )

        colors = {
            "green": "\033[92m",
            "blue": "\033[94m",
            "yellow": "\033[93m",
            "red": "\033[91m",
            "end": "\033[0m",
        }

        for key, value in output.items():
            if key not in {OLD_KEYWORD, NEW_KEYWORD} and (
                self.args.all_fields or has_changes(value)
            ):
                if value[OLD_KEYWORD] == value[NEW_KEYWORD]:
                    print("| " * indent + f"{key}: {value[OLD_KEYWORD]}")
                else:
                    if not self.args.no_color:
                        if value[OLD_KEYWORD] == 0:
                            color = "green"
                        elif value[NEW_KEYWORD] == 0:
                            color = "red"
                        elif value[OLD_KEYWORD] > value[NEW_KEYWORD]:
                            color = "yellow" if key != TOTAL_KEYWORD else "red"
                        else:
                            color = "blue" if key != TOTAL_KEYWORD else "green"

                    print(
                        "| " * indent
                        + f"{key if key != TOTAL_KEYWORD else 'Total Coverage'}: "
                        + (colors[color] if not self.args.no_color else "")
                        + f"{value[OLD_KEYWORD]} -> {value[NEW_KEYWORD]}"
                        + (colors["end"] if not self.args.no_color else "")
                    )
                self.print_output(value, indent + 1)

    def main(self):
        output = self.find_diff(self.args.file1, self.args.file2)
        self.print_output(output)


if __name__ == "__main__":
    DiffCoverage().main()