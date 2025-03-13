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

# This tool assesses the coverage of mock response files used for testing the Vertex AI
# for Firebase SDKs, as measured by the fraction of all possible fields in the model’s
# response that the files cover.
#
# Design doc: http://go/firebase-vertexai-test-coverage-tool-doc

import json
import os
import re
from argparse import ArgumentParser
from glob import glob
from sys import stderr
from urllib.request import urlopen

DISCOVERY_DOC_URL = "https://firebasevertexai.googleapis.com/$discovery/rest?version=v1beta"
SCHEMA_PREFIX = "GoogleCloudAiplatformV1beta1"
RESPONSE_TYPES = ["GenerateContentResponse", "CountTokensResponse"]
SCRIPT_DIR = os.path.dirname(__file__)
MOCK_RESPONSES_PATH = os.path.join(SCRIPT_DIR, "..", "mock-responses", "vertexai")

NUM_KEYWORD = "_coverage_num"
FILES_KEYWORD = "_coverage_files"
TOTAL_KEYWORD = "Total Coverage"


class CoverageTool:
    def __init__(
        self,
        percent_only=False,
        json_output=False,
        list_files=False,
        no_color=False,
        ignore_fields=None,
        scan_files=None,
        exclude=None,
    ):
        self.percent_only = percent_only
        self.json_output = json_output
        self.list_files = list_files
        self.no_color = no_color
        self.ignore_fields = ignore_fields
        self.scan_files = scan_files
        self.exclude = exclude

        self.schemas = self.get_schemas()
        self.mock_responses = self.get_grouped_mock_responses()
        self.total_fields, self.covered_fields = 0, 0

    def get_schemas(self):
        """Fetch discovery document and return its schemas."""
        with urlopen(DISCOVERY_DOC_URL) as response:
            return json.load(response)["schemas"]

    def get_mock_responses_list(self):
        """Return a list of mock response files to evaluate according to args."""

        def filter_by_scan_files(mock_responses):
            """Return mock responses that are mentioned in the given files to scan."""
            pattern = re.compile(r"[a-zA-Z0-9-]+")
            matches = set()
            for files_set in self.scan_files:
                for file_path in files_set:
                    with open(file_path) as f:
                        matches.update(pattern.findall(f.read()))
            return [f for f in mock_responses if f.split(".")[0] in matches]

        mock_responses = sorted(os.listdir(MOCK_RESPONSES_PATH))
        if self.exclude:
            mock_responses = [
                file_path
                for file_path in mock_responses
                if not any(file_path in files_set for files_set in self.exclude)
            ]
        if self.scan_files:
            mock_responses = filter_by_scan_files(mock_responses)
        return mock_responses

    def load_mock_response(self, file_path):
        """Return a mock response file's content as a list of dictionaries, where each
        dictionary represents a part of the response."""
        # Try to load file as a single JSON object
        try:
            with open(file_path) as f:
                return [json.load(f)]
        # Handle streaming response files with multiple parts
        except json.JSONDecodeError:
            with open(file_path) as f:
                return [json.loads(line[5:]) for line in f if line.startswith("data:")]

    def is_response_type(self, file_part, schema_props):
        """Check if the given response file part matches the given schema properties."""
        for field in file_part:
            if field not in schema_props:
                return False
            if "$ref" in schema_props[field]:
                # Recursively check nested properties
                if not self.is_response_type(
                    file_part[field],
                    self.schemas[schema_props[field]["$ref"]]["properties"],
                ):
                    return False
        return True

    def get_grouped_mock_responses(self):
        """Return a dictionary of mock responses grouped by response type, where the key is
        a response type and the value is a dictionary of file names to their content."""
        grouped_mock_responses = {t: {} for t in RESPONSE_TYPES}
        for file_name in self.get_mock_responses_list():
            # Get the content of the mock response file
            content = self.load_mock_response(
                os.path.join(MOCK_RESPONSES_PATH, file_name)
            )
            if not content:
                print(f"No data extracted from file {file_name}", file=stderr)
                continue
            # Check the first part of the response against each response type schema
            for response_type in RESPONSE_TYPES:
                response_type_props = self.schemas[SCHEMA_PREFIX + response_type][
                    "properties"
                ]
                if self.is_response_type(content[0], response_type_props):
                    grouped_mock_responses[response_type][file_name] = content
                    break
            else:
                # Error responses are not expected to match any response type
                if not (
                    len(content) == 1 and len(content[0]) == 1 and "error" in content[0]
                ):
                    print(
                        f"File {file_name} does not match any response type.",
                        file=stderr,
                    )
        return grouped_mock_responses

    def find_coverage(self, properties, responses):
        """Return a dictionary with coverage information for the given properties.

        @param properties: the "properties" field of a schema from the discovery doc
        @param responses:  mock responses to find coverage in, as a dict where the key
                           is a file name and value is a list of dictionaries, each
                           representing a part of the response
        """
        output = {}
        # Look for each property in the mock response files
        for prop_name, prop_content in sorted(properties.items()):
            if self.ignore_fields and prop_name in self.ignore_fields:
                continue
            coverage_files = []
            for file_name in responses:
                if any(prop_name in part for part in responses[file_name]):
                    coverage_files.append(file_name)
            self.total_fields += 1
            if coverage_files:
                self.covered_fields += 1
            output[prop_name] = {NUM_KEYWORD: len(coverage_files)}
            if self.list_files:
                output[prop_name][FILES_KEYWORD] = coverage_files

            # If property is an enum, find coverage for each enum value
            if "enum" in prop_content:
                for enum in prop_content["enum"]:
                    coverage_files = []
                    for file_name in responses:
                        if any(
                            enum == part.get(prop_name) for part in responses[file_name]
                        ):
                            coverage_files.append(file_name)
                    self.total_fields += 1
                    if coverage_files:
                        self.covered_fields += 1
                    output[prop_name][enum] = {NUM_KEYWORD: (len(coverage_files))}
                    if self.list_files:
                        output[prop_name][enum][FILES_KEYWORD] = coverage_files

            # If property is an instance of a schema, find coverage for that schema
            if "$ref" in prop_content:
                # Move into the referenced property in each response
                next_responses = {
                    f: [part[prop_name] for part in responses[f] if prop_name in part]
                    for f in responses
                }
                # Recursively find coverage of referenced schema with updated responses
                output[prop_name].update(
                    self.find_coverage(
                        self.schemas[prop_content["$ref"]]["properties"], next_responses
                    )
                )

            # If property is an array of a schema, find coverage for each instance
            if prop_content.get("type") == "array" and "$ref" in prop_content["items"]:
                next_responses = {
                    f: [
                        elem
                        for part in responses[f]
                        for elem in part.get(prop_name, [])
                    ]
                    for f in responses
                }
                output[prop_name].update(
                    self.find_coverage(
                        self.schemas[prop_content["items"]["$ref"]]["properties"],
                        next_responses,
                    )
                )
        return output

    def print_output(self, output, indent=0, red_indent=0):
        """Print the coverage data."""
        if self.percent_only:
            print(output[TOTAL_KEYWORD][NUM_KEYWORD])
        elif self.json_output:
            print(json.dumps(output, indent=2))
        else:
            color_red, color_end = "\033[91m", "\033[0m"
            for key, value in output.items():
                if key not in {NUM_KEYWORD, FILES_KEYWORD}:
                    color = value[NUM_KEYWORD] == 0 and not self.no_color
                    print(
                        "| " * (indent - red_indent)
                        + (color_red if color else "")
                        + "| " * red_indent
                        + f"{key}: {value[NUM_KEYWORD]}"
                        + str(value.get(FILES_KEYWORD) or "")
                        + ("%" if key == TOTAL_KEYWORD else "")
                        + (color_end if color else "")
                    )
                    self.print_output(value, indent + 1, red_indent + (color))

    def main(self):
        output = {}
        # Find and print coverage for each response type
        for response_type in RESPONSE_TYPES:
            response_type_schema = self.schemas[SCHEMA_PREFIX + response_type]
            output[response_type] = {
                NUM_KEYWORD: len(self.mock_responses[response_type]),
                **self.find_coverage(
                    response_type_schema["properties"],
                    self.mock_responses[response_type],
                ),
            }
            if self.list_files:
                output[response_type][FILES_KEYWORD] = list(
                    self.mock_responses[response_type]
                )
        output[TOTAL_KEYWORD] = {
            NUM_KEYWORD: round(self.covered_fields / self.total_fields * 100, 2)
        }
        self.print_output(output)


def get_args():
    """Parse, validate, and return command line arguments."""

    def get_files_from_pattern(pattern, root_dir="."):
        """Return a set of file paths matching the given pattern."""
        matches = {
            path
            for path in glob(pattern, recursive=True, root_dir=root_dir)
            if os.path.isfile(os.path.join(root_dir, path))
        }
        if not matches:
            parser.error(f"No matching files found for pattern: {pattern}")
        return matches

    parser = ArgumentParser()
    parser.add_argument(
        "--percent-only",
        "-p",
        action="store_true",
        help="Print only the total coverage percentage, takes precedence over other"
        " arguments",
    )
    parser.add_argument(
        "--json-output",
        "-j",
        action="store_true",
        help="Output the coverage data as JSON",
    )
    parser.add_argument(
        "--list-files",
        "-l",
        action="store_true",
        help="Output list of mock response files that cover each field",
    )
    parser.add_argument(
        "--no-color",
        "-n",
        action="store_true",
        help="Disable color in output",
    )
    parser.add_argument(
        "--ignore-fields",
        "-i",
        metavar="FIELDS",
        type=lambda x: set(x.split(",")),
        help="Ignore the fields in the given comma-separated list when calculating"
        " coverage",
    )
    parser.add_argument(
        "--scan-files",
        "-s",
        metavar="PATTERN",
        type=get_files_from_pattern,
        nargs="+",
        help="Scan files matching the given pattern(s) for names of mock response"
        " files (without the extension) to evaluate",
    )
    parser.add_argument(
        "--exclude",
        "-e",
        metavar="PATTERN",
        type=lambda x: get_files_from_pattern(x, MOCK_RESPONSES_PATH),
        nargs="+",
        help="Exclude mock response files matching the given pattern(s) from being"
        " evaluated",
    )
    return parser.parse_args()


def main():
    args = get_args()
    tool = CoverageTool(**vars(args))
    tool.main()


if __name__ == "__main__":
    main()
