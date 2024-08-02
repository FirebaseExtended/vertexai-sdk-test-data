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

NUM_KEYWORD = "_coverage_num"
FILES_KEYWORD = "_coverage_files"
TOTAL_KEYWORD = "_total_coverage_percentage"


def get_args():
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
    args = parser.parse_args()
    args.file1 = read_json(args.file1)
    args.file2 = read_json(args.file2)
    return args


def print_output(old, new, indent=0):
    """Print the diff between two coverage outputs."""
    colors = {
        "green": "\033[92m",
        "blue": "\033[94m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "end": "\033[0m",
    }

    if old.keys() != new.keys():
        print(
            "Different keys in the given coverage output files, using keys from second"
            " file only."
        )
        print("Old keys: ", old.keys())
        print("New keys: ", new.keys())

    for key in new:
        if key not in {NUM_KEYWORD, FILES_KEYWORD}:
            if key not in old:
                old[key] = {NUM_KEYWORD: 0}
            if old[key][NUM_KEYWORD] == new[key][NUM_KEYWORD]:
                print("| " * indent + f"{key}: {old[key][NUM_KEYWORD]}")
            else:
                if not args.no_color:
                    if old[key][NUM_KEYWORD] == 0:
                        color = "green"
                    elif new[key][NUM_KEYWORD] == 0:
                        color = "red"
                    elif old[key][NUM_KEYWORD] > new[key][NUM_KEYWORD]:
                        color = "yellow" if key != TOTAL_KEYWORD else "red"
                    else:
                        color = "blue" if key != TOTAL_KEYWORD else "green"

                print(
                    "| " * indent
                    + f"{key if key != TOTAL_KEYWORD else 'Total Coverage'}: "
                    + (colors[color] if not args.no_color else "")
                    + f"{old[key][NUM_KEYWORD]} -> {new[key][NUM_KEYWORD]}"
                    + (colors["end"] if not args.no_color else "")
                )
            print_output(old[key], new[key], indent + 1)


args = get_args()
print_output(args.file1, args.file2)
