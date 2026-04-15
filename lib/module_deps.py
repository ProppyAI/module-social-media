#!/usr/bin/env python3
"""Build a dependency graph from module manifests."""

import json
import os
import sys


def load_manifest(path):
    manifest_path = os.path.join(path, "module.harness.json")
    if not os.path.isfile(manifest_path):
        return None
    try:
        with open(manifest_path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Warning: invalid JSON in {manifest_path}: {e}", file=sys.stderr)
        return None


def build_graph(module_paths, output_format="text"):
    modules = {}
    for path in module_paths:
        manifest = load_manifest(path)
        if manifest and "name" in manifest:
            modules[manifest["name"]] = manifest

    if not modules:
        print("No valid modules found.")
        return

    # Build entity producer/consumer map
    producers = {}  # entity -> [module_name]
    consumers = {}  # entity -> [module_name]
    for name, m in modules.items():
        for e in m.get("entities", {}).get("produces", []):
            producers.setdefault(e, []).append(name)
        for e in m.get("entities", {}).get("consumes", []):
            consumers.setdefault(e, []).append(name)

    if output_format == "dot":
        print("digraph modules {")
        print("  rankdir=LR;")
        # Entity-based edges
        for entity, consumer_list in consumers.items():
            for producer_list in [producers.get(entity, [])]:
                for producer in producer_list:
                    for consumer in consumer_list:
                        if producer != consumer:
                            print(f'  "{producer}" -> "{consumer}" [label="{entity}"];')
        # Explicit dependency edges
        for name, m in modules.items():
            for dep in m.get("dependencies", []):
                if dep in modules:
                    print(f'  "{dep}" -> "{name}" [style=dashed, label="depends"];')
        print("}")
    else:
        print("HARNESS — Module dependency graph\n")
        for name, m in modules.items():
            produces = ", ".join(m.get("entities", {}).get("produces", [])) or "none"
            consumes_list = m.get("entities", {}).get("consumes", [])
            consumes = ", ".join(consumes_list) or "none"
            deps = m.get("dependencies", [])

            print(f"  {name}")
            print(f"    produces: {produces}")
            print(f"    consumes: {consumes}")
            if deps:
                print(f"    depends on: {', '.join(deps)}")
            print()

        # Find unresolved entities
        all_consumed = set()
        all_produced = set()
        for m in modules.values():
            all_consumed.update(m.get("entities", {}).get("consumes", []))
            all_produced.update(m.get("entities", {}).get("produces", []))
        unresolved = all_consumed - all_produced
        if unresolved:
            print(f"  Unresolved: {', '.join(sorted(unresolved))} (no module produces these)")


def main():
    if len(sys.argv) < 2:
        print("Usage: module_deps.py [--format dot] <path1> [path2] ...", file=sys.stderr)
        sys.exit(2)

    output_format = "text"
    paths = []
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--format" and i + 1 < len(sys.argv):
            output_format = sys.argv[i + 1]
            i += 2
        else:
            paths.append(sys.argv[i])
            i += 1

    build_graph(paths, output_format)


if __name__ == "__main__":
    main()
