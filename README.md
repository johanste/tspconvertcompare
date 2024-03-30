# Semantic comparison of OpenAPI2 files with Microsoft autorest extensions

### Installation:
```
pip install git+https://github.com/johanste/tspconvertcompare.git
```

### Usage:
```sh
$> tspconvertcompare
usage: tspconvertcompare [-h] -f OLD [OLD ...] -t NEW [NEW ...] [--no-filter]
tspconvertcompare: error: the following arguments are required: -f/--from, -t/--to
```

|Argument   | Description|
|-----------|------------|
|-f/--from  | One or more files to use as the baseline. Include all files that are referenced directly or indirectly|
|-t/--to    | One or more files to use as the updated files. Typically just one file if it was generated from TypeSpec tsp compile|
|--no-filter| Include all changes, including changes that are considered semantically not meaningful (e.g. changes in model names, descriptions, examples etc.)

Example:
```
$> tspconvertcompare -f azure-rest-api-specs/service.json azure-rest-api-specs/common.json -t build-output/generated.json
```

## How to interpret the output:

The output is a list of [json-patch operations](https://datatracker.ietf.org/doc/html/rfc6902) describing all the changes from the `--from/-f` to the `--to/-t` document(s). By default, semantically not-meaningful change are excluded.

Example output:

```jsonl
{'op': 'remove', 'path': '/~1paths/smurfs'}```
```
The whole route `/smurfs` was removed. This is very likely a breaking change.

> Note: The `~1` is the escaped value of forward slash ('/') in the path key. 

#### Examples of semantically non-relevant changes

```jsonl
{'op': 'replace', 'path': '/paths/smurfs/get/x-ms-examples/smurfExample/parameters/api-version', 'value': '2023-03-01'}
```
The API version in the example was changed to '2023-03-01'

