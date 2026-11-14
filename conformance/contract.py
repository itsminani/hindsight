"""Load contract/openapi.yaml and check real HTTP responses against it.

This is the "black box" side (Ch2 p.27-30): it knows the contract and a URL, never the server's code.
OpenAPI 3.1 schemas are JSON Schema 2020-12, so the standard jsonschema library validates them.
"""

import re
from pathlib import Path

import httpx
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "contract" / "openapi.yaml"
CONTRACT_URI = "urn:hindsight:openapi"


class Contract:
    """The parsed contract, able to validate a response for (method, path template, status)."""

    def __init__(self, path: Path = CONTRACT_PATH) -> None:
        """Parse the YAML and register it so "$ref: '#/components/...'" resolves."""
        self.document = yaml.safe_load(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(self.document, default_specification=DRAFT202012)
        self._registry = Registry().with_resource(CONTRACT_URI, resource)
        self._templates = [(t, _template_regex(t)) for t in self.document["paths"]]

    def template_for(self, url_path: str) -> str:
        """The contract path template matching a real path, e.g. /portfolios/pf_1 -> /portfolios/{portfolioId}."""
        for template, regex in self._templates:
            if regex.fullmatch(url_path):
                return template
        raise AssertionError(f"{url_path} is not a path in the contract")

    def _resolve(self, node: dict) -> dict:
        """Follow a $ref (like '#/components/responses/NotFound') to the object it points to."""
        while "$ref" in node:
            target = self.document
            for part in node["$ref"].removeprefix("#/").split("/"):
                target = target[part]
            node = target
        return node

    def check(self, response: httpx.Response) -> None:
        """Fail if the response's status, content type or body is not what the contract declares."""
        method = response.request.method.lower()
        template = self.template_for(response.request.url.path)
        operation = self.document["paths"][template].get(method)
        assert operation is not None, f"{method.upper()} {template} is not in the contract"

        status = str(response.status_code)
        declared = operation["responses"]
        assert status in declared, (
            f"{method.upper()} {template} returned {status}, contract only allows {sorted(declared)}: {response.text}"
        )
        spec = self._resolve(declared[status])
        content = spec.get("content")
        if not content:
            assert not response.content, f"{status} must have no body, got {response.text!r}"
            return

        media_type = response.headers.get("content-type", "").split(";")[0].strip()
        assert media_type in content, f"content-type {media_type!r} not in {list(content)} for {status}"
        schema = content[media_type]["schema"]
        validator = Draft202012Validator(
            {"$ref": CONTRACT_URI + schema["$ref"]} if "$ref" in schema else schema,
            registry=self._registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        errors = sorted(validator.iter_errors(response.json()), key=lambda e: list(e.path))
        assert not errors, f"{method.upper()} {template} {status} body breaks the contract: " + "; ".join(
            f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors
        )

        for name, header in spec.get("headers", {}).items():
            if name.lower() == "location":
                assert name in response.headers, f"{status} must send a {name} header"


def _template_regex(template: str) -> re.Pattern:
    """/portfolios/{portfolioId} -> a regex where each {param} matches one path segment."""
    return re.compile(re.sub(r"\\\{[^/]+?\\\}", "[^/]+", re.escape(template)))
