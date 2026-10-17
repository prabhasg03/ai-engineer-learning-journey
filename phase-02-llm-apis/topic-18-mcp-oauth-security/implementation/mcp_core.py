"""Topic 18 - MCP (Model Context Protocol): tiny server/client, transports, OAuth 2.1, security.

Single source of truth for the topic. Hand-written, typed where it helps, fully
offline and deterministic: NO network, NO MCP SDK, NO HTTP library. Sockets are faked
by in-process transports so the protocol mechanics stay visible.

What lives here
---------------
* Primitives ..... Tool, Resource, ResourceTemplate, Prompt + Registry
* Server/client .. McpServer (JSON-RPC 2.0 dispatch) and McpClient
* Transports ..... stdio (newline-delimited JSON-RPC, creds from env) and
                   HTTP (method + path + status codes, Streamable-HTTP style /mcp)
* OAuth 2.1 ...... protected-resource metadata (RFC 9728), AS metadata (RFC 8414),
                   PKCE S256, authorization URL with resource indicators (RFC 8707),
                   token exchange with audience validation, 401 challenge and
                   403 ``insufficient_scope`` step-up challenge
* Security ....... prompt/tool-description injection heuristic and audience checks
                   that stop token passthrough
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import parse_qs, quote, urlencode, urlsplit

# --------------------------------------------------------------------------- #
# Protocol constants
# --------------------------------------------------------------------------- #

PROTOCOL_VERSION = "2026-07-28"
SERVER_NAME = "tiny-mcp-server"
SERVER_VERSION = "1.0.0"
CLIENT_NAME = "tiny-mcp-client"
CLIENT_VERSION = "1.0.0"

#: The canonical URI identifying our demo MCP server (its "resource" / audience).
DEMO_RESOURCE = "https://mcp.example.com/mcp"
DEMO_AS_ISSUER = "https://auth.example.com"

# JSON-RPC 2.0 reserved error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
# Custom codes used to carry HTTP auth semantics through JSON-RPC.
UNAUTHORIZED = -32001        # -> HTTP 401
INSUFFICIENT_SCOPE = -32002  # -> HTTP 403

_HTTP_STATUS_BY_CODE: Dict[int, int] = {
    PARSE_ERROR: 400,
    INVALID_REQUEST: 400,
    INVALID_PARAMS: 400,
    METHOD_NOT_FOUND: 404,
    INTERNAL_ERROR: 500,
    UNAUTHORIZED: 401,
    INSUFFICIENT_SCOPE: 403,
}


class McpError(Exception):
    """Raised by :func:`unwrap_result` when a JSON-RPC response carries an error."""

    def __init__(self, code: int, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data: Dict[str, Any] = data or {}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "McpError":
        return cls(
            int(payload.get("code", INTERNAL_ERROR)),
            str(payload.get("message", "")),
            payload.get("data"),
        )


# --------------------------------------------------------------------------- #
# Primitives: tools, resources, prompts
# --------------------------------------------------------------------------- #


@dataclass
class Tool:
    """A model-controlled *executable* action (the model decides to call it)."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    required_scopes: List[str] = field(default_factory=list)
    handler: Callable[[Dict[str, Any]], Dict[str, Any]] = field(default=lambda _: {})

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "required_scopes": self.required_scopes,
        }


@dataclass
class Resource:
    """Application-controlled *context* (files, records, URIs) the app chooses to load."""

    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"
    required_scopes: List[str] = field(default_factory=list)
    #: Either a constant string or ``callable(Resource) -> str``.
    body: Any = ""

    def read(self) -> str:
        if callable(self.body):
            return str(self.body(self))
        return str(self.body)

    def describe(self) -> Dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
            "required_scopes": self.required_scopes,
        }


@dataclass
class ResourceTemplate:
    """A parameterised resource URI, e.g. ``notes://{topic}/{slug}``."""

    uri_template: str
    name: str
    description: str = ""
    required_scopes: List[str] = field(default_factory=list)

    def describe(self) -> Dict[str, Any]:
        return {
            "uriTemplate": self.uri_template,
            "name": self.name,
            "description": self.description,
            "required_scopes": self.required_scopes,
        }


@dataclass
class Prompt:
    """A user-controlled reusable template/slash-command surfaced by the client."""

    name: str
    description: str = ""
    arguments: List[Dict[str, Any]] = field(default_factory=list)
    required_scopes: List[str] = field(default_factory=list)
    render: Callable[[Dict[str, Any]], str] = field(default=lambda _: "")

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
            "required_scopes": self.required_scopes,
        }


def _visible(required_scopes: Iterable[str], scopes: Optional[Iterable[str]]) -> bool:
    """Visibility rule shared by every primitive."""
    required = set(required_scopes)
    if scopes is None:
        return True
    if not required:
        return True
    return bool(set(scopes) & required)


class Registry:
    """Holds every primitive a server exposes. Names keep topic-17 ergonomics."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self._resources: Dict[str, Resource] = {}
        self._templates: Dict[str, ResourceTemplate] = {}
        self._prompts: Dict[str, Prompt] = {}

    # -- tools -------------------------------------------------------------- #
    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list(self, scopes: Optional[List[str]] = None) -> List[Tool]:
        return [t for t in self._tools.values() if _visible(t.required_scopes, scopes)]

    # -- resources ---------------------------------------------------------- #
    def register_resource(self, resource: Resource) -> None:
        self._resources[resource.uri] = resource

    def get_resource(self, uri: str) -> Optional[Resource]:
        return self._resources.get(uri)

    def read_resource(self, uri: str) -> str:
        resource = self._resources.get(uri)
        if resource is None:
            raise KeyError(f"unknown resource '{uri}'")
        return resource.read()

    def list_resources(self, scopes: Optional[List[str]] = None) -> List[Resource]:
        return [r for r in self._resources.values() if _visible(r.required_scopes, scopes)]

    def register_resource_template(self, template: ResourceTemplate) -> None:
        self._templates[template.uri_template] = template

    def list_resource_templates(self, scopes: Optional[List[str]] = None) -> List[ResourceTemplate]:
        return [t for t in self._templates.values() if _visible(t.required_scopes, scopes)]

    # -- prompts ------------------------------------------------------------ #
    def register_prompt(self, prompt: Prompt) -> None:
        self._prompts[prompt.name] = prompt

    def get_prompt(self, name: str) -> Optional[Prompt]:
        return self._prompts.get(name)

    def list_prompts(self, scopes: Optional[List[str]] = None) -> List[Prompt]:
        return [p for p in self._prompts.values() if _visible(p.required_scopes, scopes)]


# --------------------------------------------------------------------------- #
# Tokens and authorization
# --------------------------------------------------------------------------- #


class TokenStore:
    """In-memory access tokens: scopes + the resource (audience) they were issued for."""

    def __init__(self) -> None:
        self._scopes: Dict[str, List[str]] = {}
        self._audience: Dict[str, Optional[str]] = {}
        self._ttl: Dict[str, int] = {}

    def issue(self, token: str, scopes: List[str], resource: Optional[str] = None, expires_in: int = 3600) -> None:
        self._scopes[token] = list(scopes)
        self._audience[token] = resource
        self._ttl[token] = expires_in

    def scopes_for(self, token: Optional[str]) -> Optional[List[str]]:
        if token is None:
            return None
        return self._scopes.get(token)

    def audience_for(self, token: Optional[str]) -> Optional[str]:
        if token is None:
            return None
        return self._audience.get(token)

    def token_for_audience(self, resource: str) -> Optional[str]:
        for token, audience in self._audience.items():
            if audience == resource:
                return token
        return None

    def revoke(self, token: str) -> None:
        self._scopes.pop(token, None)
        self._audience.pop(token, None)
        self._ttl.pop(token, None)


#: Fallback store so ``validate_token_audience(token, resource)`` works with two args.
_TOKENS = TokenStore()


def validate_token_audience(token: Optional[str], server_resource: str, store: Optional[TokenStore] = None) -> bool:
    """True only when ``token`` was issued *for this* MCP server (its resource).

    This is the defence against **token passthrough**: a token minted for server A
    must never be accepted by server B, so B validates the ``aud``/resource and
    rejects a mismatch. Tokens with no audience recorded (e.g. stdio env creds) fail.
    """
    store = store if store is not None else _TOKENS
    if token is None:
        return False
    if store.scopes_for(token) is None:
        return False
    return store.audience_for(token) == server_resource


class AuthChecker:
    """Deny-by-default scope + audience checks used by the server."""

    def __init__(self, tokens: TokenStore, resource: Optional[str] = None) -> None:
        self.tokens = tokens
        self.resource = resource

    def _audience_ok(self, token: Optional[str]) -> Tuple[bool, str]:
        """Reject a token minted for a different server (token passthrough defence)."""
        if self.resource is None:
            return True, ""
        audience = self.tokens.audience_for(token)
        if audience is None:
            return True, ""  # not audience-bound (e.g. stdio env credential)
        if audience == self.resource:
            return True, ""
        return False, f"token passthrough rejected: audience mismatch, token not issued for {self.resource} (403)"

    def _check(self, token: Optional[str], required: Iterable[str], strict_all: bool) -> Tuple[bool, str]:
        scopes = self.tokens.scopes_for(token)
        if scopes is None:
            return False, "missing or invalid access token (401)"
        ok, why = self._audience_ok(token)
        if not ok:
            return False, why
        needed = list(required)
        if not needed:
            return True, ""
        if strict_all:
            if all(scope in scopes for scope in needed):
                return True, ""
        elif set(scopes) & set(needed):
            return True, ""
        return False, f"insufficient scope; required {' '.join(needed)} (403)"

    # Backwards-compatible names from the first cut of this topic.
    def check_list(self, token: Optional[str]) -> Tuple[bool, str]:
        return self._check(token, ["tools:list"], strict_all=True)

    def check_call(self, tool: Tool, token: Optional[str]) -> Tuple[bool, str]:
        return self._check(token, tool.required_scopes, strict_all=False)

    def check_resources_list(self, token: Optional[str]) -> Tuple[bool, str]:
        return self._check(token, ["resources:list"], strict_all=True)

    def check_resource(self, resource: Resource, token: Optional[str]) -> Tuple[bool, str]:
        return self._check(token, resource.required_scopes, strict_all=False)

    def check_prompts_list(self, token: Optional[str]) -> Tuple[bool, str]:
        return self._check(token, ["prompts:list"], strict_all=True)

    def check_prompt(self, prompt: Prompt, token: Optional[str]) -> Tuple[bool, str]:
        return self._check(token, prompt.required_scopes, strict_all=False)


# --------------------------------------------------------------------------- #
# OAuth 2.1 helpers
# --------------------------------------------------------------------------- #


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return url.rstrip("/")


def www_authenticate_challenge(
    resource_metadata_url: str,
    *,
    realm: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    scope: Optional[str] = None,
) -> str:
    """Build the ``WWW-Authenticate: Bearer ...`` challenge (RFC 6750 + RFC 9728).

    A 401 carries only ``resource_metadata`` so the client can *discover* the
    authorization servers. A 403 adds ``error="insufficient_scope"`` and ``scope``
    which is the MCP signal for **step-up authorization**.
    """
    parts: List[str] = []
    if realm:
        parts.append(f'realm="{realm}"')
    parts.append(f'resource_metadata="{resource_metadata_url}"')
    if error:
        parts.append(f'error="{error}"')
    if error_description:
        parts.append(f'error_description="{error_description}"')
    if scope:
        parts.append(f'scope="{scope}"')
    return "Bearer " + ", ".join(parts)


@dataclass
class ProtectedResourceMetadata:
    """RFC 9728 document served at ``/.well-known/oauth-protected-resource``."""

    resource: str
    authorization_servers: List[str] = field(default_factory=list)
    scopes_supported: List[str] = field(default_factory=list)
    bearer_methods_supported: List[str] = field(default_factory=lambda: ["header"])
    resource_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "resource": self.resource,
            "authorization_servers": list(self.authorization_servers),
            "bearer_methods_supported": list(self.bearer_methods_supported),
            "scopes_supported": list(self.scopes_supported),
        }
        if self.resource_name:
            data["resource_name"] = self.resource_name
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProtectedResourceMetadata":
        return cls(
            resource=str(data["resource"]),
            authorization_servers=list(data.get("authorization_servers", [])),
            scopes_supported=list(data.get("scopes_supported", [])),
            bearer_methods_supported=list(data.get("bearer_methods_supported", ["header"])),
            resource_name=str(data.get("resource_name", "")),
        )

    @staticmethod
    def well_known_path() -> str:
        return "/.well-known/oauth-protected-resource"


@dataclass
class AuthorizationServerMetadata:
    """RFC 8414 document served at ``/.well-known/oauth-authorization-server``."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str = ""
    scopes_supported: List[str] = field(default_factory=list)
    response_types_supported: List[str] = field(default_factory=lambda: ["code"])
    grant_types_supported: List[str] = field(default_factory=lambda: ["authorization_code"])
    code_challenge_methods_supported: List[str] = field(default_factory=lambda: ["S256"])
    token_endpoint_auth_methods_supported: List[str] = field(default_factory=lambda: ["none"])

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "response_types_supported": list(self.response_types_supported),
            "grant_types_supported": list(self.grant_types_supported),
            "code_challenge_methods_supported": list(self.code_challenge_methods_supported),
            "token_endpoint_auth_methods_supported": list(self.token_endpoint_auth_methods_supported),
            "scopes_supported": list(self.scopes_supported),
        }
        if self.registration_endpoint:
            data["registration_endpoint"] = self.registration_endpoint
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuthorizationServerMetadata":
        return cls(
            issuer=str(data["issuer"]),
            authorization_endpoint=str(data["authorization_endpoint"]),
            token_endpoint=str(data["token_endpoint"]),
            registration_endpoint=str(data.get("registration_endpoint", "")),
            scopes_supported=list(data.get("scopes_supported", [])),
            response_types_supported=list(data.get("response_types_supported", ["code"])),
            grant_types_supported=list(data.get("grant_types_supported", ["authorization_code"])),
            code_challenge_methods_supported=list(data.get("code_challenge_methods_supported", ["S256"])),
            token_endpoint_auth_methods_supported=list(data.get("token_endpoint_auth_methods_supported", ["none"])),
        )

    @staticmethod
    def well_known_path() -> str:
        return "/.well-known/oauth-authorization-server"


def generate_code_verifier(length: int = 64) -> str:
    """PKCE code_verifier: 43-128 chars of unreserved characters."""
    return secrets.token_urlsafe(48)[: max(43, min(128, length))]


def code_challenge_s256(verifier: str) -> str:
    """``BASE64URL(SHA256(ASCII(code_verifier)))`` with padding stripped."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_pkce_pair(length: int = 64) -> Tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for the S256 method."""
    verifier = generate_code_verifier(length)
    return verifier, code_challenge_s256(verifier)


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """Constant-time check that ``code_verifier`` matches the stored challenge."""
    return hmac.compare_digest(code_challenge_s256(code_verifier), code_challenge)


def build_authorization_url(
    authorization_endpoint: str,
    *,
    client_id: str,
    redirect_uri: str,
    resource: str,
    scope: Optional[Iterable[str]] = None,
    code_challenge: Optional[str] = None,
    state: Optional[str] = None,
    response_type: str = "code",
    extra: Optional[Mapping[str, str]] = None,
) -> str:
    """Authorization request URL with PKCE and the RFC 8707 ``resource`` indicator."""
    params: List[Tuple[str, str]] = [
        ("response_type", response_type),
        ("client_id", client_id),
        ("redirect_uri", redirect_uri),
    ]
    if scope:
        params.append(("scope", " ".join(scope)))
    if state:
        params.append(("state", state))
    if code_challenge:
        params.append(("code_challenge", code_challenge))
        params.append(("code_challenge_method", "S256"))
    params.append(("resource", resource))
    for key, value in (extra or {}).items():
        params.append((key, value))
    return f"{authorization_endpoint}?{urlencode(params)}"


@dataclass
class AuthorizationCode:
    code: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    resource: str
    scopes: List[str]


class OAuthServer:
    """A miniature OAuth 2.1 authorization server (authorization + token endpoints)."""

    def __init__(
        self,
        metadata: AuthorizationServerMetadata,
        resource: str,
        token_store: TokenStore,
        *,
        allowed_clients: Optional[Iterable[str]] = None,
    ) -> None:
        self.metadata = metadata
        self.resource = resource
        self.tokens = token_store
        self.allowed_clients = set(allowed_clients or ["mcp-client"])
        self._codes: Dict[str, AuthorizationCode] = {}

    # -- discovery ---------------------------------------------------------- #
    def protected_resource_metadata(self, resource_name: str = "") -> ProtectedResourceMetadata:
        return ProtectedResourceMetadata(
            resource=self.resource,
            authorization_servers=[self.metadata.issuer],
            scopes_supported=list(self.metadata.scopes_supported),
            resource_name=resource_name,
        )

    # -- authorization endpoint -------------------------------------------- #
    def authorize(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        scope: Iterable[str],
        resource: str,
        code_challenge: str,
        state: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Simulate the user consenting; return the redirect parameters."""
        if resource != self.resource:
            raise ValueError(f"resource must be {self.resource} (got {resource})")
        if client_id not in self.allowed_clients:
            raise ValueError(f"unknown client_id '{client_id}'")
        code = secrets.token_urlsafe(24)
        self._codes[code] = AuthorizationCode(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            resource=resource,
            scopes=list(scope),
        )
        return {"code": code, "state": state, "redirect_uri": redirect_uri, "resource": resource}

    # -- token endpoint ----------------------------------------------------- #
    def token(
        self,
        *,
        grant_type: str = "authorization_code",
        code: str = "",
        code_verifier: str = "",
        client_id: str = "",
        redirect_uri: Optional[str] = None,
        resource: Optional[str] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        """Exchange an authorization code for an audience-bound access token."""
        if grant_type != "authorization_code":
            return 400, {"error": "unsupported_grant_type"}
        record = self._codes.get(code)
        if record is None:
            return 400, {"error": "invalid_grant", "error_description": "unknown or already used code"}
        if client_id and client_id != record.client_id:
            return 400, {"error": "invalid_grant", "error_description": "client_id mismatch"}
        if redirect_uri and redirect_uri != record.redirect_uri:
            return 400, {"error": "invalid_grant", "error_description": "redirect_uri mismatch"}
        if resource is not None and resource != self.resource:
            # Never mint a token for another audience -> no token passthrough.
            return 400, {"error": "invalid_target", "error_description": "resource does not match this server"}
        if not record.code_challenge or not verify_pkce(code_verifier, record.code_challenge):
            return 400, {"error": "invalid_grant", "error_description": "PKCE verification failed"}
        self._codes.pop(code, None)  # a code is single-use -> replay fails
        token = secrets.token_urlsafe(32)
        self.tokens.issue(token, record.scopes, resource=self.resource)
        return 200, {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": " ".join(record.scopes),
            "resource": self.resource,
        }


def build_demo_oauth(resource: str = DEMO_RESOURCE, issuer: str = DEMO_AS_ISSUER) -> OAuthServer:
    """A ready-made authorization server for the demo and the notebook."""
    metadata = AuthorizationServerMetadata(
        issuer=issuer,
        authorization_endpoint=f"{issuer}/authorize",
        token_endpoint=f"{issuer}/token",
        registration_endpoint=f"{issuer}/register",
        scopes_supported=["tools:list", "resources:list", "prompts:list", "math", "notes:read"],
    )
    return OAuthServer(metadata, resource, TokenStore())


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #

INJECTION_PATTERNS: Tuple[str, ...] = (
    r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)",
    r"disregard\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)",
    r"do\s+not\s+(tell|reveal|mention|inform|report)",
    r"don'?t\s+(tell|reveal|mention|inform|report)",
    r"(^|\W)system\s*:",
    r"(^|\W)assistant\s*:",
    r"<\s*important\s*>",
    r"<\s*system\s*>",
    r"you\s+must\s+(always|never|now|first|not)",
    r"exfiltrate",
    r"override\s+(the\s+)?(safety|system|previous|developer)",
    r"new\s+instructions",
    r"reveal\s+(the\s+)?(api\s*key|secret|token|password|credential)",
    r"send\s+.{0,60}?\s+to\s+https?://",
    r"curl\s+http",
    r"~/\.ssh",
    r"BEGIN\s+(RSA\s+)?PRIVATE\s+KEY",
    r"base64\s+-d",
)


def injection_matches(text: Optional[str]) -> List[str]:
    """Return every injection-pattern regex that matches ``text`` (empty = clean)."""
    if not text:
        return []
    low = text.lower()
    return [pattern for pattern in INJECTION_PATTERNS if re.search(pattern, low)]


def looks_like_injection(text: Optional[str]) -> bool:
    """Heuristic: does this server-provided string read like an instruction to the model?

    Tool descriptions, resource bodies and prompt templates are *data supplied by the
    server*. A malicious or compromised server can hide instructions in them, and the
    model will read those instructions as if they came from the user. Treat every hit
    as untrusted; review/allow-list servers and keep the human in the consent loop.
    """
    return bool(injection_matches(text))


def scan_capabilities(registry: Registry) -> Dict[str, Dict[str, List[str]]]:
    """Scan every tool description, resource body and prompt template for injection."""
    findings: Dict[str, Dict[str, List[str]]] = {"tools": {}, "resources": {}, "prompts": {}}
    for tool in registry.list():
        hits = injection_matches(f"{tool.description}\n{json.dumps(tool.input_schema, sort_keys=True)}")
        if hits:
            findings["tools"][tool.name] = hits
    for resource in registry.list_resources():
        hits = injection_matches(f"{resource.description}\n{resource.read()}")
        if hits:
            findings["resources"][resource.uri] = hits
    for prompt in registry.list_prompts():
        hits = injection_matches(f"{prompt.description}\n{prompt.render({})}")
        if hits:
            findings["prompts"][prompt.name] = hits
    return findings


def extract_bearer(headers: Optional[Mapping[str, str]]) -> Optional[str]:
    """Pull the token out of an ``Authorization: Bearer <token>`` header."""
    if not headers:
        return None
    for key, value in headers.items():
        if key.lower() == "authorization" and isinstance(value, str) and value.startswith("Bearer "):
            return value[7:]
    return None


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #


class McpServer:
    """A tiny MCP server: JSON-RPC 2.0 dispatch over an HTTP-ish surface.

    The server owns no sockets. :meth:`handle` is the JSON-RPC core; the two
    transports (:mod:`stdio_transport`, :func:`http_transport_factory`) are thin
    adapters that make the framing difference explicit.
    """

    PRIMITIVES: Tuple[str, ...] = ("tools", "resources", "prompts")

    def __init__(
        self,
        registry: Registry,
        auth: Optional[AuthChecker] = None,
        *,
        resource: Optional[str] = None,
        scopes_supported: Optional[Iterable[str]] = None,
        authorization_servers: Optional[Iterable[str]] = None,
        oauth: Optional[OAuthServer] = None,
        primitives: Iterable[str] = PRIMITIVES,
        server_name: str = SERVER_NAME,
        server_version: str = SERVER_VERSION,
    ) -> None:
        self.registry = registry
        if auth is None:
            auth = AuthChecker(TokenStore())
        self.auth = auth
        self.resource = resource or auth.resource or DEMO_RESOURCE
        # Keep the checker's audience in sync with the server identity.
        if self.auth.resource is None:
            self.auth.resource = self.resource
        self.oauth = oauth
        if scopes_supported is not None:
            self.scopes_supported = list(scopes_supported)
        elif oauth is not None:
            self.scopes_supported = list(oauth.metadata.scopes_supported)
        else:
            self.scopes_supported = []
        if authorization_servers is not None:
            self.authorization_servers = list(authorization_servers)
        elif oauth is not None:
            self.authorization_servers = [oauth.metadata.issuer]
        else:
            self.authorization_servers = [DEMO_AS_ISSUER]
        self.server_name = server_name
        self.server_version = server_version

        self._enabled: set[str] = set(primitives)
        self._notifications: List[Dict[str, Any]] = []
        self.client_info: Optional[Dict[str, Any]] = None
        self.client_capabilities: Dict[str, Any] = {}
        self.initialized = False

    # -- capabilities ------------------------------------------------------- #
    def primitives(self) -> List[str]:
        return [name for name in self.PRIMITIVES if name in self._enabled]

    def capabilities(self) -> Dict[str, Any]:
        """Only enabled primitives appear, each advertising ``listChanged``."""
        return {name: {"listChanged": True} for name in self.primitives()}

    def enable_primitive(self, name: str) -> None:
        self._enabled.add(name)
        self.notify_list_changed(name)

    def disable_primitive(self, name: str) -> None:
        self._enabled.discard(name)

    def primitive_enabled(self, name: str) -> bool:
        return name in self._enabled

    def notify_list_changed(self, primitive: str) -> Dict[str, Any]:
        """Queue a ``notifications/<primitive>/list_changed`` message (server -> client)."""
        notification = {"jsonrpc": "2.0", "method": f"notifications/{primitive}/list_changed"}
        self._notifications.append(notification)
        return notification

    def pop_notifications(self) -> List[Dict[str, Any]]:
        pending, self._notifications = self._notifications, []
        return pending

    # -- dynamic registration (adds emit list_changed) ---------------------- #
    def add_tool(self, tool: Tool) -> None:
        self.registry.register(tool)
        self.notify_list_changed("tools")

    def add_resource(self, resource: Resource) -> None:
        self.registry.register_resource(resource)
        self.notify_list_changed("resources")

    def add_resource_template(self, template: ResourceTemplate) -> None:
        self.registry.register_resource_template(template)
        self.notify_list_changed("resources")

    def add_prompt(self, prompt: Prompt) -> None:
        self.registry.register_prompt(prompt)
        self.notify_list_changed("prompts")

    # -- OAuth surface ------------------------------------------------------ #
    def resource_metadata_url(self) -> str:
        return f"{origin_of(self.resource)}{ProtectedResourceMetadata.well_known_path()}"

    def protected_resource_metadata(self) -> Dict[str, Any]:
        if self.oauth is not None:
            return self.oauth.protected_resource_metadata(self.server_name).to_dict()
        return ProtectedResourceMetadata(
            resource=self.resource,
            authorization_servers=list(self.authorization_servers),
            scopes_supported=list(self.scopes_supported),
            resource_name=self.server_name,
        ).to_dict()

    def authorization_server_metadata(self) -> Optional[Dict[str, Any]]:
        return self.oauth.metadata.to_dict() if self.oauth is not None else None

    def challenge(self, *, error: Optional[str] = None, scope: Optional[str] = None,
                  error_description: Optional[str] = None) -> str:
        """The ``WWW-Authenticate`` value advertised on 401 / 403."""
        return www_authenticate_challenge(
            self.resource_metadata_url(),
            realm=self.server_name,
            error=error,
            error_description=error_description,
            scope=scope,
        )

    # -- JSON-RPC core ------------------------------------------------------ #
    @staticmethod
    def _ok(request_id: Any, result: Any) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _err(request_id: Any, code: int, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        error: Dict[str, Any] = {"code": code, "message": message}
        if data:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    def _auth_error(self, request_id: Any, why: str, required: Iterable[str] = ()) -> Dict[str, Any]:
        if "401" in why:
            challenge = self.challenge(error_description=why)
            return self._err(request_id, UNAUTHORIZED, why, {"status": 401, "WWW-Authenticate": challenge})
        scope = " ".join(required) or (" ".join(self.scopes_supported) if self.scopes_supported else None)
        challenge = self.challenge(error="insufficient_scope", scope=scope, error_description=why)
        return self._err(request_id, INSUFFICIENT_SCOPE, why, {"status": 403, "WWW-Authenticate": challenge, "scope": scope})

    def initialize_result(self, params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        self.client_info = dict(params.get("clientInfo") or {})
        self.client_capabilities = dict(params.get("capabilities") or {})
        self.initialized = True
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": self.capabilities(),
            "serverInfo": {"name": self.server_name, "version": self.server_version},
            "instructions": "Tiny MCP server. Tools are model-controlled, resources app-controlled, prompts user-controlled.",
        }

    def handle(self, request: Any, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Dispatch one JSON-RPC message. Returns ``None`` for notifications."""
        if not isinstance(request, dict):
            return self._err(None, INVALID_REQUEST, "request must be a JSON object")
        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            return self._err(request_id, INVALID_REQUEST, "missing 'method'")
        params = request.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return self._err(request_id, INVALID_PARAMS, "params must be an object")

        if method.startswith("notifications/"):
            return None  # notifications get no JSON-RPC response

        primitive = self._primitive_for_method(method)
        if primitive is not None and not self.primitive_enabled(primitive):
            return self._err(request_id, METHOD_NOT_FOUND, f"primitive '{primitive}' is disabled")

        if method == "initialize":
            return self._ok(request_id, self.initialize_result(params))
        if method == "ping":
            return self._ok(request_id, {})
        if method == "tools/list":
            ok, why = self.auth.check_list(token)
            if not ok:
                return self._auth_error(request_id, why, ["tools:list"])
            tools = self.registry.list(self.auth.tokens.scopes_for(token))
            return self._ok(request_id, {"tools": [t.describe() for t in tools]})
        if method == "tools/call":
            return self._tools_call(request_id, params, request, token)
        if method == "resources/list":
            ok, why = self.auth.check_resources_list(token)
            if not ok:
                return self._auth_error(request_id, why, ["resources:list"])
            items = self.registry.list_resources(self.auth.tokens.scopes_for(token))
            return self._ok(request_id, {"resources": [r.describe() for r in items]})
        if method == "resources/read":
            return self._resources_read(request_id, params, token)
        if method == "resources/templates/list":
            ok, why = self.auth.check_resources_list(token)
            if not ok:
                return self._auth_error(request_id, why, ["resources:list"])
            items = self.registry.list_resource_templates(self.auth.tokens.scopes_for(token))
            return self._ok(request_id, {"resourceTemplates": [t.describe() for t in items]})
        if method == "prompts/list":
            ok, why = self.auth.check_prompts_list(token)
            if not ok:
                return self._auth_error(request_id, why, ["prompts:list"])
            items = self.registry.list_prompts(self.auth.tokens.scopes_for(token))
            return self._ok(request_id, {"prompts": [p.describe() for p in items]})
        if method == "prompts/get":
            return self._prompts_get(request_id, params, token)
        return self._err(request_id, METHOD_NOT_FOUND, f"unknown method '{method}'")

    @staticmethod
    def _primitive_for_method(method: str) -> Optional[str]:
        if method.startswith("tools/"):
            return "tools"
        if method.startswith("resources/"):
            return "resources"
        if method.startswith("prompts/"):
            return "prompts"
        return None

    def _tools_call(self, request_id: Any, params: Mapping[str, Any], request: Mapping[str, Any],
                    token: Optional[str]) -> Dict[str, Any]:
        name = params.get("name") or request.get("name")
        arguments = params.get("arguments", request.get("arguments"))
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return self._err(request_id, INVALID_PARAMS, "arguments must be an object")
        tool = self.registry.get(str(name)) if name else None
        if tool is None:
            return self._err(request_id, INVALID_PARAMS, f"unknown tool '{name}'")
        ok, why = self.auth.check_call(tool, token)
        if not ok:
            return self._auth_error(request_id, why, tool.required_scopes)
        try:
            result = tool.handler(dict(arguments))
        except Exception as exc:  # handlers are user code; surface, never crash the server
            return self._err(request_id, INTERNAL_ERROR, f"handler error: {exc}")
        warning = looks_like_injection(tool.description)
        return self._ok(request_id, {
            "content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}],
            "structuredContent": result,
            "isError": False,
            "untrusted_description_warning": warning,
        })

    def _resources_read(self, request_id: Any, params: Mapping[str, Any], token: Optional[str]) -> Dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            return self._err(request_id, INVALID_PARAMS, "missing 'uri'")
        resource = self.registry.get_resource(uri)
        if resource is None:
            return self._err(request_id, INVALID_PARAMS, f"unknown resource '{uri}'")
        ok, why = self.auth.check_resource(resource, token)
        if not ok:
            return self._auth_error(request_id, why, resource.required_scopes)
        text = resource.read()
        return self._ok(request_id, {
            "contents": [{"uri": resource.uri, "mimeType": resource.mime_type, "text": text}],
            "untrusted_content_warning": looks_like_injection(text),
        })

    def _prompts_get(self, request_id: Any, params: Mapping[str, Any], token: Optional[str]) -> Dict[str, Any]:
        name = params.get("name")
        prompt = self.registry.get_prompt(str(name)) if name else None
        if prompt is None:
            return self._err(request_id, INVALID_PARAMS, f"unknown prompt '{name}'")
        ok, why = self.auth.check_prompt(prompt, token)
        if not ok:
            return self._auth_error(request_id, why, prompt.required_scopes)
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return self._err(request_id, INVALID_PARAMS, "arguments must be an object")
        for spec in prompt.arguments:
            if spec.get("required") and spec.get("name") not in arguments:
                return self._err(request_id, INVALID_PARAMS, f"missing required argument '{spec['name']}'")
        text = prompt.render(dict(arguments))
        return self._ok(request_id, {
            "description": prompt.description,
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            "untrusted_template_warning": looks_like_injection(text),
        })

    # -- stdio transport ---------------------------------------------------- #
    def stdio_request(self, line: str, token: Optional[str] = None) -> str:
        """Handle ONE newline-delimited JSON-RPC line; return the response line ("" = none)."""
        try:
            request = json.loads(line)
        except Exception as exc:
            return json.dumps(self._err(None, PARSE_ERROR, f"parse error: {exc}"))
        response = self.handle(request, token)
        if response is None:
            return ""
        return json.dumps(response)

    # -- HTTP transport ----------------------------------------------------- #
    def http_request(
        self,
        method: str,
        path: str,
        headers: Optional[Mapping[str, str]] = None,
        body: Optional[Any] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        """HTTP-surface dispatch: method + path + headers in, (status, json body) out."""
        method = (method or "GET").upper()
        headers = headers or {}
        token = extract_bearer(headers)
        parts = urlsplit(path)
        route = parts.path.rstrip("/") or "/"

        # Discovery documents need no auth.
        if method == "GET" and route == ProtectedResourceMetadata.well_known_path():
            return 200, self.protected_resource_metadata()
        if method == "GET" and route == AuthorizationServerMetadata.well_known_path():
            metadata = self.authorization_server_metadata()
            if metadata is None:
                return 404, {"error": "authorization server metadata not configured"}
            return 200, metadata

        # Token endpoint -> delegate to the authorization server.
        if method == "POST" and route == "/token":
            if self.oauth is None:
                return 404, {"error": "token endpoint not configured"}
            payload = body if isinstance(body, dict) else {}
            return self.oauth.token(
                grant_type=payload.get("grant_type", "authorization_code"),
                code=payload.get("code", ""),
                code_verifier=payload.get("code_verifier", ""),
                client_id=payload.get("client_id", ""),
                redirect_uri=payload.get("redirect_uri"),
                resource=payload.get("resource"),
            )

        # JSON-RPC endpoint, Streamable-HTTP style.
        if method == "POST" and route == "/mcp":
            response = self.handle(body, token)
            if response is None:
                return 202, {"jsonrpc": "2.0", "result": "accepted"}
            error = response.get("error")
            if error:
                status = _HTTP_STATUS_BY_CODE.get(int(error.get("code", INTERNAL_ERROR)), 200)
                data = error.get("data") or {}
                if "WWW-Authenticate" in data:
                    return status, {"jsonrpc": "2.0", "error": error, "WWW-Authenticate": data["WWW-Authenticate"]}
                return status, {"jsonrpc": "2.0", "error": error}
            return 200, response

        # Legacy / convenience REST routes (kept from the first cut of this topic).
        if method == "GET" and route == "/tools":
            ok, why = self.auth.check_list(token)
            if not ok:
                return self._legacy_auth_error(why, ["tools:list"])
            tools = self.registry.list(self.auth.tokens.scopes_for(token))
            return 200, {"tools": [t.describe() for t in tools]}

        if method == "POST" and route.startswith("/tools/") and route.endswith("/call"):
            name = route.split("/")[2]
            arguments = body if isinstance(body, dict) else {}
            if self.registry.get(name) is None:
                return 404, {"error": f"unknown tool '{name}'"}
            result = self._tools_call("http", {"name": name, "arguments": arguments}, {}, token)
            if "error" in result:
                return self._legacy_error(result["error"])
            return 200, result["result"]

        if method == "GET" and route == "/resources":
            ok, why = self.auth.check_resources_list(token)
            if not ok:
                return self._legacy_auth_error(why, ["resources:list"])
            items = self.registry.list_resources(self.auth.tokens.scopes_for(token))
            return 200, {"resources": [r.describe() for r in items]}

        if method == "GET" and route == "/resources/read":
            query = parse_qs(parts.query)
            uri = (query.get("uri") or [""])[0]
            result = self._resources_read("http", {"uri": uri}, token)
            if "error" in result:
                return self._legacy_error(result["error"])
            return 200, result["result"]

        if method == "GET" and route == "/resources/templates":
            ok, why = self.auth.check_resources_list(token)
            if not ok:
                return self._legacy_auth_error(why, ["resources:list"])
            items = self.registry.list_resource_templates(self.auth.tokens.scopes_for(token))
            return 200, {"resourceTemplates": [t.describe() for t in items]}

        if method == "GET" and route == "/prompts":
            ok, why = self.auth.check_prompts_list(token)
            if not ok:
                return self._legacy_auth_error(why, ["prompts:list"])
            items = self.registry.list_prompts(self.auth.tokens.scopes_for(token))
            return 200, {"prompts": [p.describe() for p in items]}

        if route.startswith("/prompts/") and method in ("GET", "POST"):
            name = route.split("/")[2]
            arguments = body if isinstance(body, dict) else {}
            if method == "GET":
                arguments = {k: v[0] for k, v in parse_qs(parts.query).items()}
            result = self._prompts_get("http", {"name": name, "arguments": arguments}, token)
            if "error" in result:
                return self._legacy_error(result["error"])
            return 200, result["result"]

        return 404, {"error": "not found"}

    def _legacy_error(self, error: Mapping[str, Any]) -> Tuple[int, Dict[str, Any]]:
        status = _HTTP_STATUS_BY_CODE.get(int(error.get("code", INTERNAL_ERROR)), 200)
        data = error.get("data") or {}
        payload: Dict[str, Any] = {"error": error.get("message", "")}
        if "WWW-Authenticate" in data:
            payload["WWW-Authenticate"] = data["WWW-Authenticate"]
        if data.get("status"):
            payload["status"] = data["status"]
        return status, payload

    def _legacy_auth_error(self, why: str, required: Iterable[str]) -> Tuple[int, Dict[str, Any]]:
        error = self._auth_error(None, why, required)["error"]
        status = int(error.get("data", {}).get("status", 403))
        payload: Dict[str, Any] = {"error": why, "status": status}
        if "WWW-Authenticate" in (error.get("data") or {}):
            payload["WWW-Authenticate"] = error["data"]["WWW-Authenticate"]
        return status, payload


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


def response_error(response: Any) -> Optional[Dict[str, Any]]:
    """Return the JSON-RPC ``error`` object if the response carries one."""
    if isinstance(response, dict):
        error = response.get("error")
        if isinstance(error, dict):
            return error
    return None


def unwrap_result(response: Any) -> Any:
    """Return the JSON-RPC ``result`` (raising :class:`McpError` on error).

    Works for both transports: an HTTP legacy response like ``{"status": 200,
    "tools": [...]}`` has no ``result`` key, so it is returned unchanged.
    """
    error = response_error(response)
    if error is not None:
        raise McpError.from_payload(error)
    if isinstance(response, dict) and "result" in response and set(response) <= {"jsonrpc", "id", "result", "status"}:
        return response["result"]
    return response


class McpClient:
    """A connector living inside the *host*. One client == one server, 1:1 session."""

    def __init__(self, transport: Callable[..., Any], token: Optional[str] = None) -> None:
        self.transport = transport
        self.token = token
        self._request_id = 0
        self.protocol_version: Optional[str] = None
        self.server_capabilities: Dict[str, Any] = {}
        self.server_info: Dict[str, Any] = {}
        self.notifications: List[Dict[str, Any]] = []

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Send a JSON-RPC *notification* (no id, no response expected)."""
        request: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            request["params"] = params
        return self.transport(request, self.token)

    def send(self, method: str, params: Optional[Dict[str, Any]] = None, token: Optional[str] = None) -> Any:
        request: Dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            request["params"] = params
        return self.transport(request, token if token is not None else self.token)

    # -- lifecycle ---------------------------------------------------------- #
    def initialize(self, capabilities: Optional[Dict[str, Any]] = None) -> Any:
        response = self.send("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            "capabilities": capabilities or {
                "roots": {"listChanged": True},
                "sampling": {},
                "elicitation": {},
            },
        })
        result = unwrap_result(response)
        if isinstance(result, dict):
            self.protocol_version = result.get("protocolVersion")
            self.server_capabilities = dict(result.get("capabilities") or {})
            self.server_info = dict(result.get("serverInfo") or {})
        return response

    def initialized(self) -> Any:
        """Tell the server the handshake is complete (``notifications/initialized``)."""
        return self.notify("notifications/initialized")

    def supports(self, primitive: str) -> bool:
        return primitive in self.server_capabilities

    def collect_list_changed(self, response: Any) -> None:
        """Record ``list_changed`` notifications piggy-backed on a transport response."""
        if isinstance(response, dict):
            for item in response.get("notifications", []) or []:
                self.notifications.append(item)

    # -- tools -------------------------------------------------------------- #
    def list_tools(self, token: Optional[str] = None) -> Any:
        return self.send("tools/list", {}, token)

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None, token: Optional[str] = None) -> Any:
        return self.send("tools/call", {"name": name, "arguments": arguments or {}}, token)

    def tool_names(self, token: Optional[str] = None) -> List[str]:
        result = unwrap_result(self.list_tools(token))
        return [t["name"] for t in (result.get("tools") if isinstance(result, dict) else []) or []]

    # -- resources ---------------------------------------------------------- #
    def list_resources(self, token: Optional[str] = None) -> Any:
        return self.send("resources/list", {}, token)

    def read_resource(self, uri: str, token: Optional[str] = None) -> Any:
        return self.send("resources/read", {"uri": uri}, token)

    def list_resource_templates(self, token: Optional[str] = None) -> Any:
        return self.send("resources/templates/list", {}, token)

    # -- prompts ------------------------------------------------------------ #
    def list_prompts(self, token: Optional[str] = None) -> Any:
        return self.send("prompts/list", {}, token)

    def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None, token: Optional[str] = None) -> Any:
        return self.send("prompts/get", {"name": name, "arguments": arguments or {}}, token)

    # -- errors ------------------------------------------------------------- #
    def raise_for_error(self, response: Any) -> Any:
        error = response_error(response)
        if error is not None:
            raise McpError.from_payload(error)
        return response


# --------------------------------------------------------------------------- #
# Transports
# --------------------------------------------------------------------------- #


def stdio_transport(server: McpServer, request: Dict[str, Any], token: Optional[str] = None) -> Dict[str, Any]:
    """stdio: one newline-delimited JSON-RPC line in, one (or none) out."""
    line = json.dumps(request)
    response_line = server.stdio_request(line, token)
    if not response_line:
        return {}
    return json.loads(response_line)


def stdio_lines(server: McpServer, lines: Iterable[str], token: Optional[str] = None) -> List[str]:
    """Feed a stream of NDJSON lines through the server, collecting non-empty replies."""
    replies: List[str] = []
    for line in lines:
        reply = server.stdio_request(line, token)
        if reply:
            replies.append(reply)
    return replies


def parse_ndjson(text: str) -> List[Dict[str, Any]]:
    """Parse a newline-delimited JSON-RPC stream (the stdio framing)."""
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def credentials_from_env(env: Mapping[str, str], variable: str = "MCP_TOKEN") -> Optional[str]:
    """stdio servers get credentials from the environment -> NOT OAuth.

    A locally launched subprocess inherits env vars (set by the host) and prints logs
    to stderr. There is no discovery document and no authorization-code flow.
    """
    return env.get(variable)


def http_transport_factory(server: McpServer):
    """HTTP: translate a JSON-RPC request into method + path, then read status codes."""

    def transport(
        request: Dict[str, Any],
        token: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        headers = dict(headers or {})
        if token:
            headers.setdefault("Authorization", f"Bearer {token}")
        method = request.get("method")
        params = request.get("params") or {}
        http_method, path, body = "POST", "/mcp", dict(request)
        if method == "tools/list":
            http_method, path, body = "GET", "/tools", None
        elif method == "tools/call":
            name = params.get("name") or request.get("name")
            arguments = params.get("arguments", request.get("arguments")) or {}
            http_method, path, body = "POST", f"/tools/{name}/call", arguments
        elif method == "resources/list":
            http_method, path, body = "GET", "/resources", None
        elif method == "resources/read":
            uri = str(params.get("uri", ""))
            http_method, path, body = "GET", f"/resources/read?uri={quote(uri, safe='')}", None
        elif method == "resources/templates/list":
            http_method, path, body = "GET", "/resources/templates", None
        elif method == "prompts/list":
            http_method, path, body = "GET", "/prompts", None
        elif method == "prompts/get":
            name = params.get("name") or request.get("name")
            http_method, path, body = "POST", f"/prompts/{name}", params.get("arguments") or {}
        # Escape hatches kept from the first cut of this topic.
        if "_method" in request:
            http_method = request["_method"]
        if "_path" in request:
            path = request["_path"]
        if "_body" in request:
            body = request["_body"]
        status, response = server.http_request(http_method, path, headers, body)
        return {"status": status, **response}

    return transport


# --------------------------------------------------------------------------- #
# Demo wiring
# --------------------------------------------------------------------------- #


def build_demo_server(resource: str = DEMO_RESOURCE, issuer: str = DEMO_AS_ISSUER) -> Tuple[McpServer, TokenStore]:
    """A ready-made server + token store used by the notebook and the smoke tests."""
    oauth = build_demo_oauth(resource, issuer)
    tokens = oauth.tokens
    auth = AuthChecker(tokens, resource=resource)
    registry = Registry()

    registry.register(Tool(
        "echo",
        "Echo a message back.",
        {"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]},
        handler=lambda args: {"echo": args.get("msg", "")},
    ))
    registry.register(Tool(
        "add",
        "Add two numbers.",
        {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]},
        required_scopes=["math"],
        handler=lambda args: {"sum": args.get("a", 0) + args.get("b", 0)},
    ))
    registry.register_resource(Resource(
        uri="notes://topic18/overview",
        name="Topic 18 overview",
        description="A short local note about MCP.",
        mime_type="text/markdown",
        required_scopes=["notes:read"],
        body="# MCP\nTools are model-controlled, resources are app-controlled, prompts are user-controlled.",
    ))
    registry.register_resource_template(ResourceTemplate(
        uri_template="notes://topic18/{slug}",
        name="Topic 18 note by slug",
        description="Read any note in the topic-18 store.",
    ))
    registry.register_prompt(Prompt(
        name="explain-mcp-role",
        description="Ask the model to explain one MCP role.",
        arguments=[{"name": "role", "description": "host | client | server", "required": True}],
        required_scopes=["prompts:list"],
        render=lambda args: f"Explain the role of the {args.get('role', 'server')} in MCP in two sentences.",
    ))

    server = McpServer(
        registry,
        auth,
        resource=resource,
        oauth=oauth,
        scopes_supported=["tools:list", "resources:list", "prompts:list", "math", "notes:read"],
    )
    return server, tokens


__all__ = [
    "PROTOCOL_VERSION", "SERVER_NAME", "CLIENT_NAME", "DEMO_RESOURCE", "DEMO_AS_ISSUER",
    "PARSE_ERROR", "INVALID_REQUEST", "METHOD_NOT_FOUND", "INVALID_PARAMS", "INTERNAL_ERROR",
    "UNAUTHORIZED", "INSUFFICIENT_SCOPE",
    "McpError", "Tool", "Resource", "ResourceTemplate", "Prompt", "Registry",
    "TokenStore", "AuthChecker", "validate_token_audience",
    "www_authenticate_challenge", "ProtectedResourceMetadata", "AuthorizationServerMetadata",
    "generate_code_verifier", "code_challenge_s256", "generate_pkce_pair", "verify_pkce",
    "build_authorization_url", "AuthorizationCode", "OAuthServer", "build_demo_oauth",
    "INJECTION_PATTERNS", "injection_matches", "looks_like_injection", "scan_capabilities",
    "extract_bearer", "origin_of",
    "McpServer", "McpClient", "response_error", "unwrap_result",
    "stdio_transport", "stdio_lines", "parse_ndjson", "credentials_from_env",
    "http_transport_factory", "build_demo_server",
]



