"""Request and response bodies, mirroring the schemas in contract/openapi.yaml.

Python uses snake_case; the JSON uses camelCase like the contract. Requests refuse unknown
fields (the contract says additionalProperties: false).
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base for every body: camelCase in JSON, snake_case in Python."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RequestModel(ApiModel):
    """Base for request bodies: unknown fields are a 422, not silently ignored."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class TokenRequest(RequestModel):
    """POST /auth/token body."""

    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1)


class TokenResponse(ApiModel):
    """POST /auth/token 200 response."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
