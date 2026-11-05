import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import miniyaml

try:
    import yaml as reference_yaml
except ImportError:
    reference_yaml = None

OPENAPI = """\
openapi: 3.0.3
info:
  title: Pet store   # a comment after a value
  version: "1.0.0"
  description: |
    Line one
    Line two
servers:
  - url: https://api.example.com/v1
  - url: http://localhost:8080
tags: [pets, store]
paths:
  /pets:
    get:
      tags:
        - pets
      summary: List pets
      operationId: listPets
      parameters:
        - name: limit
          in: query
          required: false
          schema:
            type: integer
            maximum: 100
      responses:
        200:
          description: A list of pets
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Pet'
        '404':
          description: "Not found: no such pet"
  /pets/{petId}:
    delete:
      summary: Remove a pet
      responses:
        204:
          description: Gone
components:
  schemas:
    Pet:
      type: object
      required: [id, name]
      properties:
        id: {type: integer, format: int64}
        name: {type: string, example: "Rex"}
        tag:
          type: string
          nullable: true
"""

SAMPLES = {
    "scalars": "a: 1\nb: -2\nc: 3.5\nd: true\ne: false\nf: null\ng: ~\nh: text\ni: '12'\nj: \"x\\ty\"\nk:\nl: 1.5e+3\n",
    "sequence of maps": "items:\n  - name: one\n    value: 1\n  - name: two\n    value: 2\n    nested:\n      - a\n      - b\n",
    "same-indent sequence": "list:\n- a\n- b\nafter: 1\n",
    "nested sequences": "matrix:\n  - - 1\n    - 2\n  - - 3\n    - 4\n",
    "literal block": "text: |\n  first\n  second\n\n  third\nnext: 1\n",
    "folded block": "text: >\n  folded line one\n  continues here\n\n  new paragraph\nnext: 1\n",
    "chomping": "keep: |+\n  a\n\nstrip: |-\n  b\nclip: |\n  c\n",
    "flow": "a: [1, 2, [3, 4]]\nb: {x: 1, y: [a, b], z: {q: null}}\nc: []\nd: {}\n",
    "quoted keys": "'a: b': 1\n\"c d\": 2\n",
    "comments": "# heading\na: 1  # trailing\n# between\nb: 'has # inside'\nc: \"also # inside\"\n",
    "multi-line plain": "summary: this runs\n  over two lines\nnext: ok\n",
    "document marker": "---\na: 1\n",
    "url values": "url: https://example.com:8080/path?x=1#frag\nname: a:b\n",
    "empty": "",
}


def normalise(value):
    if isinstance(value, dict):
        return {str(key): normalise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalise(item) for item in value]
    return value


class ReadingTests(unittest.TestCase):
    def test_an_openapi_document(self):
        document = miniyaml.loads(OPENAPI)
        self.assertEqual(document["openapi"], "3.0.3")
        self.assertEqual((document["info"]["title"], document["info"]["version"]), ("Pet store", "1.0.0"))
        self.assertEqual(document["info"]["description"], "Line one\nLine two\n")
        self.assertEqual([server["url"] for server in document["servers"]], ["https://api.example.com/v1", "http://localhost:8080"])
        self.assertEqual(document["tags"], ["pets", "store"])
        get = document["paths"]["/pets"]["get"]
        self.assertEqual((get["operationId"], get["parameters"][0]["schema"]["maximum"], get["parameters"][0]["required"]), ("listPets", 100, False))
        self.assertEqual(sorted(get["responses"]), ["200", "404"])
        self.assertEqual(get["responses"]["404"]["description"], "Not found: no such pet")
        self.assertEqual(get["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"], "#/components/schemas/Pet")
        self.assertIn("/pets/{petId}", document["paths"])
        pet = document["components"]["schemas"]["Pet"]
        self.assertEqual((pet["required"], pet["properties"]["id"], pet["properties"]["tag"]["nullable"]), (["id", "name"], {"type": "integer", "format": "int64"}, True))

    def test_scalar_types(self):
        values = miniyaml.loads(SAMPLES["scalars"])
        self.assertEqual(values, {"a": 1, "b": -2, "c": 3.5, "d": True, "e": False, "f": None, "g": None, "h": "text", "i": "12", "j": "x\ty", "k": None, "l": 1500.0})

    def test_block_scalars(self):
        self.assertEqual(miniyaml.loads(SAMPLES["literal block"]), {"text": "first\nsecond\n\nthird\n", "next": 1})
        self.assertEqual(miniyaml.loads(SAMPLES["folded block"]), {"text": "folded line one continues here\nnew paragraph\n", "next": 1})
        self.assertEqual(miniyaml.loads(SAMPLES["chomping"]), {"keep": "a\n\n", "strip": "b", "clip": "c\n"})

    def test_structure(self):
        self.assertEqual(miniyaml.loads(SAMPLES["sequence of maps"]), {"items": [{"name": "one", "value": 1}, {"name": "two", "value": 2, "nested": ["a", "b"]}]})
        self.assertEqual(miniyaml.loads(SAMPLES["same-indent sequence"]), {"list": ["a", "b"], "after": 1})
        self.assertEqual(miniyaml.loads(SAMPLES["nested sequences"]), {"matrix": [[1, 2], [3, 4]]})
        self.assertEqual(miniyaml.loads(SAMPLES["flow"]), {"a": [1, 2, [3, 4]], "b": {"x": 1, "y": ["a", "b"], "z": {"q": None}}, "c": [], "d": {}})

    def test_keys_comments_and_urls(self):
        self.assertEqual(miniyaml.loads(SAMPLES["quoted keys"]), {"a: b": 1, "c d": 2})
        self.assertEqual(miniyaml.loads(SAMPLES["comments"]), {"a": 1, "b": "has # inside", "c": "also # inside"})
        self.assertEqual(miniyaml.loads(SAMPLES["url values"]), {"url": "https://example.com:8080/path?x=1#frag", "name": "a:b"})
        self.assertEqual(miniyaml.loads(SAMPLES["multi-line plain"]), {"summary": "this runs over two lines", "next": "ok"})
        self.assertEqual(miniyaml.loads(SAMPLES["document marker"]), {"a": 1})
        self.assertIsNone(miniyaml.loads(SAMPLES["empty"]))

    def test_integer_keys_become_text(self):
        self.assertEqual(miniyaml.loads("200:\n  x: 1\n"), {"200": {"x": 1}})

    def test_json_is_valid_yaml(self):
        self.assertEqual(miniyaml.loads('{"a": [1, 2, {"b": "c"}], "d": null}'), {"a": [1, 2, {"b": "c"}], "d": None})


class RefusalTests(unittest.TestCase):
    def test_what_is_not_supported_is_refused_with_a_line_number(self):
        cases = {
            "tab indent": "a:\n\tb: 1\n",
            "anchor": "a: &x 1\n",
            "alias": "a: 1\nb: *x\n",
            "tag": "a: !!str 1\n",
            "merge": "base:\n  a: 1\nthing:\n  <<: 1\n",
            "two documents": "a: 1\n---\nb: 2\n",
            "duplicate key": "a: 1\na: 2\n",
            "open quote": "a: \"unclosed\n",
            "open flow": "a: [1, 2\n",
            "bad escape": 'a: "\\q"\n',
            "stray text": "a: 1\n  b: 2\n  - c\n",
        }
        for name, text in cases.items():
            with self.assertRaises(miniyaml.YamlError, msg=name) as raised:
                miniyaml.loads(text)
            self.assertIn("YAML", str(raised.exception), name)


@unittest.skipIf(reference_yaml is None, "PyYAML is not installed; the cross-check is only a bonus")
class CrossCheckTests(unittest.TestCase):
    def test_every_sample_reads_the_same_as_a_reference_reader(self):
        documents = {**SAMPLES, "openapi": OPENAPI}
        for name, text in documents.items():
            with self.subTest(name):
                self.assertEqual(miniyaml.loads(text), normalise(reference_yaml.safe_load(text)))


if __name__ == "__main__":
    unittest.main()
