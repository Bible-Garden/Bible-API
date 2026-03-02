# extract-openapi.py
import argparse
import json
import sys
import yaml
from uvicorn.importer import import_from_string

parser = argparse.ArgumentParser(prog="extract-openapi.py")
parser.add_argument("app",       help='App import string. Eg. "main:app"', default="main:app")
parser.add_argument("--app-dir", help="Directory containing the app", default=None)
parser.add_argument("--out",     help="Output file ending in .json or .yaml", default="openapi.yaml")

def replace_anyof_with_string_type(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                # Check for anyOf construct: [{type: X}, {type: null}] -> {type: X}
                if 'anyOf' in value and isinstance(value['anyOf'], list):
                    types = {v.get('type') for v in value['anyOf'] if isinstance(v, dict)}
                    non_null = types - {'null'}
                    if len(non_null) == 1 and 'null' in types:
                        actual_type = non_null.pop()
                        value.pop('anyOf')
                        value['type'] = actual_type
                    else:
                        replace_anyof_with_string_type(value)
                else:
                    # Recursively traverse nested dictionaries
                    replace_anyof_with_string_type(value)
            elif isinstance(value, list):
                # Recursively traverse lists
                for item in value:
                    replace_anyof_with_string_type(item)
    elif isinstance(data, list):
        for item in data:
            replace_anyof_with_string_type(item)

if __name__ == "__main__":
    args = parser.parse_args()

    if args.app_dir is not None:
        print(f"adding {args.app_dir} to sys.path")
        sys.path.insert(0, args.app_dir)

    print(f"importing app from {args.app}")
    app = import_from_string(args.app)
    openapi = app.openapi()
    version = openapi.get("openapi", "unknown version")

    # hook to solve the issue https://github.com/apple/swift-openapi-generator/issues/513#issuecomment-1911980259
    replace_anyof_with_string_type(openapi)

    print(f"writing openapi spec v{version}")
    with open(args.out, "w") as f:
        if args.out.endswith(".json"):
            json.dump(openapi, f, indent=2)
        else:
            yaml.dump(openapi, f, sort_keys=False)

    print(f"spec written to {args.out}")
