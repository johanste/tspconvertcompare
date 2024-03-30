import argparse
import functools
import json
import pathlib
import sys
import typing

import json_merge_patch as mergepatch
import jsonpatch

JsonPtr = typing.NewType("JsonPtr", str)


class OpenApiDocument(dict):

    def __init__(self, data: dict[str, object], *, path: str | list[str] = []):
        super().__init__(data)
        self.path = [path] if isinstance(path, str) else path

    def merge(self, other: dict[str, object]) -> None:
        self.update(mergepatch.merge(self, other))


@functools.lru_cache
def load_document(path: str) -> OpenApiDocument:
    try:
        with open(path, mode="r") as f:
            result = OpenApiDocument(json.load(f), path=path)
            return result
    except FileNotFoundError:
        if "/examples/" in path:
            return OpenApiDocument({}, path=path)
        raise


def load(paths: list[str]) -> OpenApiDocument:
    root = load_document(paths.pop(0))
    for path in paths:
        root.merge(load_document(path))
    return root


@functools.lru_cache
def load_fragment(path: str, raw_jsonptr: JsonPtr) -> OpenApiDocument:
    filepath, relative_jsonptr = split_ref(raw_jsonptr)
    if filepath:
        document = load_document(str(pathlib.Path(path).parents[0] / filepath))
    else:
        document = load_document(path)

    if relative_jsonptr:
        for segment in relative_jsonptr.replace("//", "/")[1:].split("/"):
            if isinstance(document, list):
                document = document[int(segment)]
            assert isinstance(document, dict)
            document = document[segment]
    document["__fragment"] = {"raw": raw_jsonptr}
    return document


def split_ref(jsonptr: JsonPtr) -> tuple[str, JsonPtr]:
    if jsonptr.startswith("#"):
        return ("", JsonPtr(jsonptr[1:]))
    if "#" in jsonptr:
        parts = jsonptr.split("#", 1)
        return parts[0], JsonPtr(parts[1])
    return jsonptr, JsonPtr("")


def normalize(doc: OpenApiDocument, source_path: list[str]) -> dict[str, object]:
    def iter_normalize(
        data: dict[str, object] | str | int | float | bool, source_path: list[str]
    ) -> dict[str, object] | str | int | float | bool:
        if isinstance(
            data,
            (
                str,
                int,
                float,
                bool,
            ),
        ):
            return data
        result = {}
        if "$ref" in data:
            dereffed = load_fragment(doc.path[-1], JsonPtr(str(data.pop("$ref"))))
            dereffed.update(data)
            data = dereffed
        for key in list(sorted(data.keys())):
            value = data[key]
            if isinstance(value, dict):
                result[key] = iter_normalize(value, source_path + [key])
            elif isinstance(value, list):
                result[key] = [
                    iter_normalize(item, source_path=source_path + [str(index)])
                    for index, item in enumerate(value)
                ]
            elif isinstance(value, str):
                result[key] = value.strip()
            else:
                result[key] = value
        return result

    return typing.cast(dict[str, object], iter_normalize(doc, []))


def compare(old: list[str], new: list[str]) -> jsonpatch.JsonPatch:
    old_document = normalize(load(old), [])
    new_document = normalize(load(new), [])

    for doc in (old_document, new_document):
        doc.pop("definitions", None)
        doc.pop("parameters", None)

    return jsonpatch.make_patch(dict(old_document), dict(new_document))


def _ignore_response_property_readonly(diff: dict[str, str]) -> bool:
    path = diff.get("path", "")
    return "/responses/" in path and path.endswith("readOnly")


filters = {
    "ignore-examples": {"func": lambda diff: "/x-ms-examples" in diff.get("path", "")},
    "ignore-descriptions": {
        "func": lambda diff: diff.get("path", "").endswith("/description")
    },
    "ignore-operation-ids": {
        "func": lambda diff: diff.get("path", "").endswith("/operationId")
    },
    "ignore-fragments": {"func": lambda diff: "/__fragment" in diff.get("path", "")},
    "ignore-consumes-produces": {
        "func": lambda diff: diff.get("path", "").endswith("/consumes")
        or diff.get("path", "").endswith("/produces")
    },
    "ignore-response-readonly": {"func": _ignore_response_property_readonly},
    "ignore-x-ms-parameterlocation": {
        "func": lambda diff: diff.get("path", "").endswith("/x-ms-parameter-location")
    },
    "ignore-x-ms-mutability": {
        "func": lambda diff: diff.get("path", "").endswith("/x-ms-mutability")
    },
    "ignore-x-ms-client-name": {
        "func": lambda diff: diff.get("path", "").endswith("/x-ms-client-name")
    },
    "ignore-security-definition": {
        "func": lambda diff: diff.get("path", "").startswith("/security")
    },
    "ignore-info-definition": {
        "func": lambda diff: diff.get("path", "").startswith("/info")
    },
    "ignore-tags": {"func": lambda diff: diff.get("path", "").startswith("/tags")},
    "ignore-schemes": {
        "func": lambda diff: diff.get("path", "").startswith("/schemes")
    },
    "ignore-added-paths": {
        "func": lambda diff: diff.get("op", "") == "add"
        and diff.get("path", "").startswith("/paths/")
        and len(diff.get("path", "").split("/")) == 3
    },
    "ignore-example": {"func": lambda diff: diff.get("path", "").endswith("/example")},
}


def main():
    import argparse

    def is_filter(name: str) -> str:
        if not "ignore-" + name in filters:
            raise ValueError(
                f"Filter {name} not found - valid rules are {filters.keys()}"
            )
        return "ignore-" + name

    app = argparse.ArgumentParser()
    app.add_argument(
        "-f",
        "--from",
        dest="old",
        type=argparse.FileType("r"),
        nargs="+",
        required=True,
    )
    app.add_argument(
        "-t", "--to", dest="new", type=argparse.FileType("r"), nargs="+", required=True
    )
    app.add_argument("--no-filter", dest="no_filter", action="store_true")
    params = app.parse_args()
    diffs = compare([f.name for f in params.old], [f.name for f in params.new])
    for diff in diffs:
        should_ignore = False
        for name, definition in filters.items():
            if not params.no_filter and definition["func"](diff):
                should_ignore = True
                break
        if not should_ignore:
            print(diff)
