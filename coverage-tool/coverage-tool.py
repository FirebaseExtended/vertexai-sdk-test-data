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
from argparse import ArgumentParser
from glob import glob
from urllib.request import urlopen

DISCOVERY_DOC_URL = "https://aiplatform.googleapis.com/$discovery/rest?version=v1beta1"
SCHEMA_PREFIX = "GoogleCloudAiplatformV1beta1"
RESPONSE_TYPES = ["GenerateContentResponse", "CountTokensResponse"]
SCRIPT_DIR = os.path.dirname(__file__)
MOCK_RESPONSES_PATH = os.path.join(SCRIPT_DIR, "..", "mock-responses")

NUM_KEYWORD = "_coverage_num"
FILES_KEYWORD = "_coverage_files"
TOTAL_KEYWORD = "_total_coverage_percentage"


def get_args():
    """Parse, validate, and return command line arguments."""

    def get_files_from_patterns(pattern, root_dir="."):
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
        help="Print only the total coverage percentage",
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
        type=lambda x: get_files_from_patterns(x),
        nargs="+",
        help="Scan files matching the given pattern(s) for names of mock response files"
        " (without the extension) to evaluate",
    )
    parser.add_argument(
        "--exclude",
        "-e",
        metavar="PATTERN",
        type=lambda x: get_files_from_patterns(x, MOCK_RESPONSES_PATH),
        nargs="+",
        help="Exclude mock response files matching the given pattern(s) from being"
        " evaluated",
    )
    args = parser.parse_args()
    if args.percent_only and (args.json_output or args.list_files):
        parser.error(
            "`--percent-only` cannot be used with `--json-output` or `--list-files`."
        )
    return args


def get_schemas():
    """Download discovery document and return its schemas."""
    doc_path = os.path.join(SCRIPT_DIR, "discovery_doc.json")
    if not os.path.exists(doc_path):
        with open(doc_path, "w") as doc:
            with urlopen(DISCOVERY_DOC_URL) as response:
                doc.write(response.read().decode("utf-8"))
    with open (doc_path) as f:
        return json.load(f)["schemas"]


def get_mock_responses_list():
    """Return a list of mock response files to evaluate according to args."""
    mock_responses = sorted(os.listdir(MOCK_RESPONSES_PATH))
    if args.exclude:
        mock_responses = [
            file_path
            for file_path in mock_responses
            if not any(file_path in files_set for files_set in args.exclude)
        ]
    if args.scan_files:
        content = ""
        for files_set in args.scan_files:
            for file_path in files_set:
                with open(file_path) as f:
                    content += f.read()
        mock_responses = [f for f in mock_responses if f.split(".")[0] in content]
    return mock_responses


def load_mock_response(file_path):
    """Return a mock response file's content as a list of dictionaries."""
    with open(file_path) as f:
        lines = f.readlines()
    ans = []
    for n, line in enumerate(lines):
        if line.strip() == "":
            continue
        elif line.startswith("data:"):
            # For streaming responses
            ans.append(json.loads(line[5:]))
        else:
            # For unary responses and last part of some streaming responses
            ans.append(json.loads("".join(lines[n:])))
            break
    return ans


def is_response_type(file_part, schema_props):
    """Check if the given response file part matches the given schema properties."""
    for field in file_part:
        if field not in schema_props:
            return False
        if "$ref" in schema_props[field]:
            # Recursively check nested properties
            if not is_response_type(
                file_part[field], schemas[schema_props[field]["$ref"]]["properties"]
            ):
                return False
    return True


def get_grouped_mock_responses():
    """Return a dictionary of mock responses grouped by response type."""
    responses_content = {
        file_name: load_mock_response(os.path.join(MOCK_RESPONSES_PATH, file_name))
        for file_name in get_mock_responses_list()
    }
    grouped_mock_responses = {t: {} for t in RESPONSE_TYPES}
    # Check each file's first part against each response type
    for file_name, content in responses_content.items():
        for response_type in RESPONSE_TYPES:
            response_type_props = schemas[SCHEMA_PREFIX + response_type]["properties"]
            if is_response_type(content[0], response_type_props):
                grouped_mock_responses[response_type][file_name] = content
                break
        else:
            # Failure responses are not expected to match any response type
            if "failure" not in file_name:
                raise ValueError(f"File {file_name} does not match any response type.")
    return grouped_mock_responses


def find_coverage(properties, responses):
    """Return a dictionary with coverage information for the given properties."""
    global total_fields, covered_fields
    output = {}
    # Look for each property in the mock response files
    for prop_name, prop_content in properties.items():
        if args.ignore_fields and prop_name in args.ignore_fields:
            continue
        coverage_files = []
        for file_name in responses:
            if any(prop_name in part for part in responses[file_name]):
                coverage_files.append(file_name)
        total_fields += 1
        if coverage_files:
            covered_fields += 1
        output[prop_name] = {NUM_KEYWORD: len(coverage_files)}
        if args.list_files:
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
                total_fields += 1
                if coverage_files:
                    covered_fields += 1
                output[prop_name][enum] = {NUM_KEYWORD: (len(coverage_files))}
                if args.list_files:
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
                find_coverage(
                    schemas[prop_content["$ref"]]["properties"], next_responses
                )
            )

        # If property is an array of a schema, find coverage for each instance
        if prop_content.get("type") == "array" and "$ref" in prop_content["items"]:
            next_responses = {
                f: [elem for part in responses[f] for elem in part.get(prop_name, [])]
                for f in responses
            }
            output[prop_name].update(
                find_coverage(
                    schemas[prop_content["items"]["$ref"]]["properties"], next_responses
                )
            )
    return output


def print_output(output, indent=0, red_indent=0):
    """Print the coverage data."""
    if args.percent_only:
        print(output[TOTAL_KEYWORD])
    elif args.json_output:
        print(json.dumps(output, indent=2))
    else:
        color_red, color_end = "\033[91m", "\033[0m"
        for key, value in output.items():
            if key == TOTAL_KEYWORD:
                print(f"Total Coverage: {value[NUM_KEYWORD]}%")
            elif key not in {NUM_KEYWORD, FILES_KEYWORD}:
                color = not args.no_color and value[NUM_KEYWORD] == 0
                print(
                    "| " * (indent - red_indent)
                    + (color_red if color else "")
                    + "| " * red_indent
                    + f"{key}: {value[NUM_KEYWORD]} "
                    + str(value.get(FILES_KEYWORD) or "")
                    + (color_end if color else "")
                )
                print_output(value, indent + 1, red_indent + (color))


args = get_args()
schemas = get_schemas()
mock_responses = get_grouped_mock_responses()
total_fields, covered_fields = 0, 0
output = {}
# Find and print coverage for each response type
for response_type in RESPONSE_TYPES:
    response_type_schema = schemas[SCHEMA_PREFIX + response_type]
    output[response_type] = {
        NUM_KEYWORD: len(mock_responses[response_type]),
        **find_coverage(
            response_type_schema["properties"], mock_responses[response_type]
        ),
    }
    if args.list_files:
        output[response_type][FILES_KEYWORD] = list(mock_responses[response_type])
output[TOTAL_KEYWORD] = {NUM_KEYWORD: round(covered_fields / total_fields * 100, 2)}

print_output(output)
