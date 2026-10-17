"""Topic 17 - Tool Calling Core.

Core types, the tool-calling loop and supporting utilities. This module is the
single source of truth so that the notebook and test_tool_calling.py import the
same code.
"""

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, ValidationError

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, for example Seattle",
                    },
                    "units": {
                        "type": "string",
                        "enum": ["c", "f"],
                        "default": "c",
                    },
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a simple arithmetic expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                },
                "required": ["expression"],
            },
        },
    },
]


class GetWeatherArgs(BaseModel):
    city: str
    units: Literal["c", "f"] = "c"


class CalculateArgs(BaseModel):
    expression: str


def get_weather(city: str, units: str = "c") -> dict:
    """Stand-in for a real weather API. Runs locally, in this process."""
    table = {"seattle": 15, "portland": 18, "london": 12, "tokyo": 22}
    celsius = table.get(city.strip().lower(), 20)
    if units == "f":
        value = float(celsius) * 9 / 5 + 32
    else:
        value = float(celsius)
    return {"city": city, "temperature": round(value, 1), "units": units}


def calculate(expression: str) -> dict:
    """A tiny safe calculator. Runs locally, in this process."""
    allowed = set("0123456789+-*/.() ")
    if not set(expression) <= allowed:
        return {"error": "unsafe expression"}
    try:
        return {"expression": expression, "result": eval(expression)}
    except Exception as exc:
        return {"error": "could not evaluate: " + str(exc)}


TOOL_FUNCTIONS: dict[str, Callable[..., dict]] = {
    "get_weather": get_weather,
    "calculate": calculate,
}

ARG_MODELS: dict[str, type[BaseModel]] = {
    "get_weather": GetWeatherArgs,
    "calculate": CalculateArgs,
}


def execute_tool(name: str, raw_arguments: Any) -> dict:
    """Validate the model's arguments, then run the tool. Never raises."""
    if name not in TOOL_FUNCTIONS:
        return {"error": "unknown tool " + repr(name)}

    if isinstance(raw_arguments, str):
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            return {"error": "arguments were not valid JSON: " + str(exc)}
    else:
        parsed = raw_arguments

    if not isinstance(parsed, dict):
        return {"error": "arguments must be a JSON object"}

    model = ARG_MODELS.get(name)
    if model is not None:
        try:
            parsed = model(**parsed).model_dump()
        except ValidationError as exc:
            return {"error": "invalid arguments", "details": json.loads(exc.json())}

    try:
        return TOOL_FUNCTIONS[name](**parsed)
    except TypeError as exc:
        return {"error": "could not call " + name + ": " + str(exc)}


def assistant_text(text: str) -> dict:
    """A plain assistant message: the model is done and is answering."""
    return {"role": "assistant", "content": text, "tool_calls": None}


def tool_call_request(call_id: str, name: str, arguments: Any) -> dict:
    """A tool-call REQUEST. arguments is a JSON string, as in the real API."""
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments)
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ],
    }


def parallel_tool_call_request(calls: list) -> dict:
    """One assistant message that asks for several tools at once."""
    tool_calls = []
    for call_id, name, arguments in calls:
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        tool_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        )
    return {"role": "assistant", "content": None, "tool_calls": tool_calls}


def tool_result_messages(messages: list) -> list:
    return [m for m in messages if m.get("role") == "tool"]


class ChatModel(Protocol):
    """What the loop needs from a model: answer one chat turn with data."""

    def chat(self, messages: list, tools: list | None = None) -> dict: ...


class ScriptedLLM:
    """A deterministic stand-in for a chat model."""

    def __init__(self, script: list, label: str = "scripted"):
        self.script = list(script)
        self.label = label
        self.turns = 0

    def chat(self, messages: list, tools: list | None = None) -> dict:
        self.turns += 1
        if self.script:
            step = self.script.pop(0)
        else:
            step = assistant_text("(script exhausted)")
        message = step(messages) if callable(step) else step
        return {"choices": [{"message": message}]}


SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. "
    "Call a tool when you need real data. "
    "When you have enough information, answer in one short sentence."
)


@dataclass
class LoopResult:
    answer: str
    messages: list
    tool_calls_made: int
    iterations: int


def run_tool_call_loop(
    user_message: str,
    chat: Callable[..., dict] | ChatModel,
    tools: list | None = None,
    max_iterations: int = 6,
    verbose: bool = True,
) -> LoopResult:
    """Send messages, model replies. Repeat until the reply is plain text."""
    if not callable(chat) and hasattr(chat, "chat"):
        chat = chat.chat  # type: ignore
    tools = TOOLS if tools is None else tools
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    tool_calls_made = 0

    for iteration in range(1, max_iterations + 1):
        response = chat(messages, tools)
        message = response["choices"][0]["message"]
        tool_calls = message.get("tool_calls")

        if tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls,
                }
            )
            if verbose:
                names = [c["function"]["name"] for c in tool_calls]
                print("  turn", iteration, ": model requested", names)

            for call in tool_calls:
                tool_calls_made += 1
                name = call["function"]["name"]
                payload = execute_tool(name, call["function"]["arguments"])
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(payload, default=str),
                    }
                )
                if verbose:
                    print("           ->", name, "returned", json.dumps(payload, default=str))
            continue

        content = (message.get("content") or "").strip()
        if content:
            if verbose:
                print("  turn", iteration, ": final answer")
            return LoopResult(content, messages, tool_calls_made, iteration)

        raise RuntimeError("model returned neither text nor a tool call")

    raise RuntimeError("gave up after " + str(max_iterations) + " iterations")


def check_protocol(messages: list) -> list:
    """Check the request/response pairing the API will not check for us."""
    problems = []
    open_ids = set()
    for message in messages:
        if message.get("role") == "assistant" and message.get("tool_calls"):
            for call in message["tool_calls"]:
                if call["id"] in open_ids:
                    problems.append("duplicate tool_call id: " + call["id"])
                open_ids.add(call["id"])
        if message.get("role") == "tool":
            if message["tool_call_id"] not in open_ids:
                problems.append("tool result with no matching request: " + message["tool_call_id"])
            else:
                open_ids.discard(message["tool_call_id"])
    for leftover in sorted(open_ids):
        problems.append("tool call never answered: " + leftover)
    return problems
