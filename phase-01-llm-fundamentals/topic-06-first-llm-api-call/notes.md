# Topic 6 — Your First LLM API Call

## 1. Purpose of This Topic

This is your first transition from **learning how LLMs work** to **actually communicating with one programmatically**.

The goal is not to learn an SDK.

The goal is to understand what is happening underneath an SDK.

You should be able to look at an LLM API request and identify:

```text
HTTP request
    ↓
endpoint
    ↓
headers
    ↓
authentication
    ↓
JSON body
    ↓
LLM provider
    ↓
HTTP response
    ↓
status code
    ↓
JSON response
```

And you should be able to troubleshoot the most basic failures without immediately asking an AI for help.

---

# 2. Prerequisites

The syllabus specifies:

```text
Before:
Topic 4 — Statelessness
Topic 5 — Python unassisted #1
```

This ordering is deliberate.

Topic 4 gave you the mental model that an API does not magically remember your conversation.

Topic 5 gave you the Python ability to manipulate dictionaries and JSON.

Now those two ideas come together:

```text
stateless API
      +
Python + JSON
      ↓
LLM API request
```

---

# 3. What an API Actually Is

At its simplest, an API is a defined interface through which one program communicates with another.

For an LLM API:

```text
Your Python program
       │
       │ HTTP request
       ↓
LLM provider
       │
       │ HTTP response
       ↓
Your Python program
```

Your program does not directly "talk to the model."

It sends a structured HTTP request to an API endpoint.

The provider receives the request, processes it, and returns a structured response.

---

# 4. The Important Mental Model

Do not initially think:

> "I call GPT/Claude."

Think:

> "I send an HTTP request to an API endpoint containing authentication, headers, and structured JSON, and I receive an HTTP response containing structured JSON."

That distinction matters because an SDK eventually hides much of this.

You need to understand it **before allowing the SDK to hide it**.

---

# 5. Raw HTTP Anatomy

A raw API request consists of several important parts.

```text
HTTP request
│
├── Method
├── URL / endpoint
├── Headers
│   ├── Authentication
│   └── Content type
└── JSON body
```

For an LLM request, think:

```text
POST
  ↓
API endpoint
  ↓
headers
  ↓
JSON request body
  ↓
provider
```

The syllabus specifically requires:

* endpoint
* headers
* authentication key
* JSON body
* no SDK yet

---

# 6. HTTP Method

The method describes what kind of HTTP operation you are performing.

For an LLM generation request, you will commonly encounter:

```text
POST
```

The basic idea is:

```text
POST /some/endpoint
```

You are sending data to the API for it to process.

For example, Anthropic's Messages API currently exposes:

```text
POST /v1/messages
```

for creating a message.

---

# 7. Endpoint

An endpoint is the destination of your HTTP request.

Conceptually:

```text
https://provider.example/v1/...
```

For Anthropic's direct API, the API base URL is:

```text
https://api.anthropic.com
```

and the Messages API endpoint is:

```text
POST /v1/messages
```

The important concept is:

```text
base URL
   +
path
   ↓
specific API endpoint
```

Do not confuse:

```text
provider
model
endpoint
```

They are different concepts.

---

# 8. Headers

HTTP headers carry metadata about the request.

For an LLM API call, two particularly important categories are:

```text
Authentication
Content type
```

Conceptually:

```text
Authorization / API key
Content-Type: application/json
```

The exact authentication header differs by provider, so you must read the provider's documentation instead of assuming every API uses the same header.

This is one reason the syllabus explicitly includes:

> Reading provider docs as an engineer.

---

# 9. Authentication

An LLM API needs to know who is making the request and whether that request is authorized.

This is generally done using an API credential.

Conceptually:

```text
your program
    ↓
API key
    ↓
provider
    ↓
authenticate request
```

Do **not** think of the API key as part of the JSON prompt.

It belongs to the request's authentication mechanism.

---

# 10. API Keys Are Credentials

Treat an API key like a password or credential.

Do not put a real key directly into:

* GitHub repositories
* public notebooks
* screenshots
* README files
* error reports
* social media posts

Instead, your application should obtain the credential from a secure environment/configuration mechanism.

For this topic, the important principle is:

```text
code
  ↓
reads credential securely
  ↓
request header
  ↓
API
```

not:

```text
code
  ↓
hard-coded secret
```

---

# 11. Content-Type

When you send JSON, the server needs to know that the request body contains JSON.

The HTTP header commonly used for this is:

```text
Content-Type: application/json
```

So the request can conceptually look like:

```text
POST /endpoint

Content-Type: application/json
Authorization: <authentication>

{
    ...JSON body...
}
```

The exact authentication syntax is provider-specific.

---

# 12. JSON Body

The request body contains the actual structured information you want the API to process.

Conceptually:

```json
{
    "model": "...",
    "messages": [
        ...
    ]
}
```

The exact fields depend on the provider and endpoint.

This is where Topic 5 becomes directly useful.

You are constructing a Python representation of structured data and sending it as JSON.

---

# 13. The `messages` Array

The syllabus specifically requires:

> The `messages` array and roles

A messages-based API represents conversation history as a collection of messages.

Conceptually:

```text
messages
   │
   ├── message
   │     ├── role
   │     └── content
   │
   ├── message
   │     ├── role
   │     └── content
   │
   └── ...
```

Anthropic's Messages API, for example, accepts a `messages` array where each input message contains a `role` and `content`.

---

# 14. Roles

A role describes the function of a message in the conversation structure.

The basic conversational distinction you need at this stage is:

```text
user
assistant
```

Depending on the provider/API, there can also be system-level instructions represented separately or differently.

The important principle is:

> The role is metadata describing who/what the message represents; the content is the actual message data.

---

# 15. Conversation as Structured Data

Do not think of a conversation as something magical.

Think:

```text
conversation
    ↓
list of structured messages
```

For example:

```text
messages
    ↓
[
    user message,
    assistant message,
    user message,
    assistant message
]
```

This connects directly to Topic 4.

The API is not necessarily storing your entire conversational state for you.

Your application can construct and send the conversation history as structured messages.

Anthropic explicitly documents its Messages API as supporting stateless multi-turn conversations.

---

# 16. Single-Turn vs Multi-Turn

A single request might contain:

```text
user
  ↓
question
```

A multi-turn request can contain:

```text
user
  ↓
question

assistant
  ↓
previous answer

user
  ↓
follow-up
```

The API receives the structured history and generates the next response.

This is the practical connection between:

```text
Topic 4: Statelessness
```

and:

```text
Topic 6: API call
```

---

# 17. The Complete Request

At a conceptual level:

```text
                    YOUR PROGRAM
                         │
                         │
                    HTTP POST
                         │
             ┌───────────┴───────────┐
             │                       │
          Headers                 JSON body
             │                       │
       authentication           model
       content type              messages
             │                       │
             └───────────┬───────────┘
                         ↓
                    LLM API
                         │
                         ↓
                     response
```

You should be able to mentally reconstruct this diagram without an SDK.

---

# 18. Why Start Without an SDK?

An SDK might allow you to write something that looks like:

```text
client.some_method(...)
```

and receive a response.

That is convenient.

But it hides:

```text
HTTP method
endpoint
headers
authentication
serialization
request body
response body
status code
error handling
```

The syllabus intentionally says:

> **no SDK yet**

because you first need to understand what the SDK is doing for you.

---

# 19. Raw HTTP vs SDK

Think of the layers like this:

```text
LOW LEVEL

HTTP request
    ↓
JSON
    ↓
HTTP response


HIGHER LEVEL

SDK
    ↓
client.method(...)
    ↓
SDK constructs HTTP request
    ↓
provider
    ↓
SDK parses response
```

You will use SDKs later.

But first understand the lower layer.

---

# 20. The HTTP Response

Your program does not simply receive "the answer."

It receives an HTTP response.

Conceptually:

```text
HTTP response
│
├── status code
├── headers
└── JSON body
```

For example:

```text
200 OK
```

indicates a successful HTTP request.

The JSON body then contains the provider-specific response object.

---

# 21. Read Every Field

The syllabus specifically says:

> read every field of the response

This is an important engineering habit.

Do not just do:

```text
response → print text
```

and ignore everything else.

Instead, inspect:

```text
response
│
├── identifier
├── model information
├── output/content
├── stop reason
├── usage
└── other metadata
```

The exact response schema differs between providers and endpoints.

Your job is to understand the actual schema you received.

---

# 22. Response Content

The response contains the model-generated content.

For a messages-style API, this is not necessarily just a raw string.

For example, Anthropic's Messages API response contains a `content` array containing content blocks, including text blocks.

So don't automatically assume:

```text
response.content == "some string"
```

Instead, inspect the response structure.

Conceptually:

```text
response
   ↓
content
   ↓
content block(s)
   ↓
text
```

The exact structure depends on the provider.

---

# 23. Usage

Usage information tells you about resource consumption associated with the request.

Anthropic's current response example includes:

```text
usage
├── input_tokens
└── output_tokens
```

This connects directly to Topics 1 and 4.

Topic 1:

```text
tokens
```

Topic 4:

```text
growing conversation history
```

Topic 6:

```text
API reports usage
```

Together:

```text
conversation
    ↓
tokens
    ↓
API request
    ↓
usage
```

---

# 24. Why Usage Matters

Usage is not just informational.

It can affect:

```text
cost
rate limits
context consumption
performance
capacity planning
```

At this stage, you do not need to build a full cost calculator.

You need to develop the habit:

> **When an LLM API responds, inspect usage instead of ignoring it.**

---

# 25. Stop Reason

The model response also tells you why generation stopped.

For Anthropic's Messages API, `stop_reason` is part of a successful response. Current documented values include things such as:

```text
end_turn
max_tokens
stop_sequence
tool_use
pause_turn
refusal
model_context_window_exceeded
```

At this stage, the most important conceptual distinction is:

```text
HTTP status
      ≠
stop reason
```

---

# 26. HTTP Status vs Stop Reason

This distinction is extremely important.

Suppose you receive:

```text
HTTP 200
```

That means the HTTP request was successfully processed.

But the model may have stopped for a particular reason.

For example:

```text
HTTP 200
stop_reason = "end_turn"
```

This means the API request succeeded and generation ended normally.

An API error is different:

```text
HTTP 401
```

or:

```text
HTTP 400
```

or:

```text
HTTP 429
```

These are HTTP-level failures.

---

# 27. Two Layers of Failure/Outcome

Think in two layers:

```text
LAYER 1 — HTTP
────────────────
Did the API request succeed?

200
400
401
429
...


LAYER 2 — MODEL RESPONSE
────────────────────────
What happened during generation?

end_turn
max_tokens
...
```

This distinction will become increasingly important when you build production systems.

---

# 28. Reading Provider Documentation

The syllabus explicitly includes:

> Reading provider docs as an engineer

This is an important skill by itself.

You should not treat API documentation like a tutorial that you read from beginning to end.

Instead, learn to answer specific questions.

For example:

```text
What endpoint do I call?

What HTTP method?

What headers are required?

How is authentication supplied?

What JSON fields are required?

What does messages look like?

What does the response look like?

Where is generated content?

Where is usage?

What does stop_reason mean?

What HTTP errors can occur?
```

That is how an engineer uses documentation.

---

# 29. Documentation Is the Source of Truth for API Syntax

Do not rely on memory for provider-specific details.

For example, different providers can differ in:

```text
endpoint names
authentication headers
request fields
message structure
response schema
error schema
rate limits
```

Therefore:

```text
General knowledge
        ↓
understand concepts

Provider documentation
        ↓
implement exact API
```

Use the official documentation for the exact syntax.

---

# 30. Comparing Providers

The syllabus provides two primary sources:

* OpenAI API documentation
* Anthropic API documentation

This is useful because you can see which concepts are general and which are provider-specific.

### General concepts

```text
HTTP
endpoint
authentication
JSON
request
response
status codes
messages
usage
errors
```

### Provider-specific details

```text
exact endpoint
authentication format
request schema
response schema
model identifiers
error fields
```

The objective is not to memorize two APIs.

It is to learn how to **read an API specification and adapt to it**.

---

# 31. Error Triage

This is one of the most important parts of Topic 6.

The syllabus says:

> triage a 401 vs 400 vs 429 on sight.

You should develop an immediate mental classification.

```text
401 → authentication problem

400 → request problem

429 → rate/usage limit problem
```

That first classification should happen before you start randomly changing code.

---

# 32. 401 — Authentication Problem

A `401` means the request failed authentication.

For OpenAI, the current documentation describes 401 cases such as invalid authentication or an incorrect API key.

Anthropic similarly defines `401 authentication_error` as an issue with the API key, such as a malformed, revoked, or expired key.

Mental shortcut:

```text
401
 ↓
WHO ARE YOU?
 ↓
authentication
```

---

# 33. Typical 401 Investigation

If you see:

```text
401
```

check:

```text
Is the API key present?

Is the key correct?

Is it expired/revoked?

Is there an extra character or space?

Is the authentication header formatted correctly?

Am I using the correct provider's credential?

Am I using the credential for the correct project/account?
```

Do not start debugging your prompt first.

The request has not successfully authenticated.

---

# 34. 400 — Bad Request

A `400` means the request itself is invalid.

OpenAI documents 400 errors for malformed or invalid request parameters; Anthropic describes 400 as `invalid_request_error` when there is an issue with the format or content of the request.

Mental shortcut:

```text
400
 ↓
WHAT DID YOU SEND?
 ↓
request structure/content
```

---

# 35. Typical 400 Investigation

If you see:

```text
400
```

inspect:

```text
JSON syntax

required fields

field names

field types

model identifier

message structure

parameter values

endpoint-specific requirements
```

The error response usually contains information about what was wrong.

Read it.

Don't immediately rewrite the whole program.

---

# 36. 429 — Rate/Usage Limit

A `429` means the provider is refusing the request because a rate/usage-related limit has been reached.

OpenAI documents several 429 situations, including rate limits, exhausted credit balance, and spend/usage limits.

Anthropic documents `429 rate_limit_error` for cases including rate limits or certain spend caps.

Mental shortcut:

```text
429
 ↓
YOU ARE ASKING TOO MUCH / HAVE HIT A LIMIT
 ↓
rate / quota / usage / spend
```

The exact cause should be determined from the provider's error response.

---

# 37. 429 Is Not the Same as 401

This distinction should become automatic.

```text
401
→ credentials problem

429
→ request may be valid, but access is being limited
```

Therefore, replacing the API key is not the first response to a 429.

Likewise, slowing down requests will not fix an invalid API key.

---

# 38. 400 vs 401 vs 429

Memorize the first-level triage:

| Status  | First question                        |
| ------- | ------------------------------------- |
| **400** | What is wrong with my request?        |
| **401** | What is wrong with my authentication? |
| **429** | What limit have I hit?                |

Then investigate the provider's actual error payload.

---

# 39. Error Triage Workflow

When an API call fails:

```text
API request
    ↓
HTTP status
    ↓
┌───────────────┐
│ What status?  │
└───────┬───────┘
        │
   ┌────┼────┐
   ↓    ↓    ↓
  400  401  429
   │    │    │
   ↓    ↓    ↓
request auth  limit
problem problem problem
```

Then:

```text
read error body
      ↓
identify exact cause
      ↓
change only what is necessary
      ↓
retry
```

---

# 40. Do Not Debug Blindly

Bad debugging:

```text
API failed
 ↓
change random code
 ↓
try again
 ↓
change model
 ↓
change prompt
 ↓
change headers
 ↓
try again
```

Better debugging:

```text
HTTP status
    ↓
error body
    ↓
identify category
    ↓
identify exact field/cause
    ↓
make targeted correction
```

This is the engineering behavior the topic is trying to establish.

---

# 41. Provider Error Bodies Matter

Never look only at:

```text
401
```

Look at the complete response.

The provider may provide:

```text
error type
error code
message
parameter
request ID
```

The exact fields differ between APIs.

OpenAI's error documentation, for example, distinguishes error types and codes and provides specific explanations for authentication, bad requests, and rate-limit cases.

Anthropic likewise documents HTTP error types and response/request-ID behavior.

---

# 42. Request IDs

When debugging provider APIs, request IDs can be useful for tracing a failed request with the provider.

This is not the primary focus of Topic 6, but it is part of the broader response/error-reading habit.

The important principle:

```text
Don't throw away metadata.

Read the response.
```

---

# 43. A Raw HTTP Request Mental Model

You should be able to visualize a request like this:

```text
POST /provider-endpoint

Headers:
    authentication
    content-type

Body:
    {
        model: ...,
        messages: [...]
    }
```

Then the response:

```text
HTTP/1.1 200 OK

Headers:
    ...

Body:
    {
        content: ...,
        usage: ...,
        stop_reason: ...
    }
```

The exact fields vary by provider.

The architecture does not.

---

# 44. Topic 4 → Topic 6 Connection

Topic 4 taught:

```text
API is stateless
```

Topic 6 now makes that concrete.

Suppose the conversation is:

```text
User:
What is Java?

Assistant:
Java is...

User:
What about Spring?
```

Your application may construct:

```text
messages:
[
    user: "What is Java?",
    assistant: "...",
    user: "What about Spring?"
]
```

and send that structured history to the API.

The model receives the context you provide.

This makes the statelessness concept operational rather than theoretical.

---

# 45. Topic 5 → Topic 6 Connection

Topic 5 taught:

```text
Python
lists
dictionaries
JSON
```

Topic 6 uses exactly those concepts:

```text
Python dictionary
      ↓
JSON request
      ↓
HTTP
      ↓
JSON response
      ↓
Python dictionary
```

So Topic 6 is your first practical combination of Topics 4 and 5.

---

# 46. Topic 1 → Topic 6 Connection

Topic 1 taught tokens.

Topic 6 exposes token usage through the API response.

Conceptually:

```text
your input
    ↓
tokenization
    ↓
model processing
    ↓
output
    ↓
usage information
```

The API can expose input/output token usage depending on the provider and endpoint.

For example, Anthropic's Messages response includes `input_tokens` and `output_tokens`.

This is your first practical encounter with the token concepts you studied earlier.

---

# 47. What You Should NOT Learn Yet

Stay disciplined with the syllabus.

Do not turn Topic 6 into a course on:

```text
SDK abstractions
streaming
function/tool calling
agents
structured outputs
RAG
prompt engineering
evaluation
retry frameworks
production observability
LLMOps
```

Those topics belong later.

For Topic 6, the central skill is:

```text
RAW HTTP
    ↓
REQUEST
    ↓
RESPONSE
    ↓
ERROR TRIAGE
```

---

# 48. Engineer's Documentation Workflow

When given a new LLM provider, follow this sequence:

```text
1. Find official API documentation
        ↓
2. Identify authentication
        ↓
3. Find endpoint
        ↓
4. Identify HTTP method
        ↓
5. Identify required headers
        ↓
6. Identify required JSON fields
        ↓
7. Find request example
        ↓
8. Find response schema
        ↓
9. Find error documentation
        ↓
10. Make the smallest possible request
```

This is a transferable skill.

The provider can change.

The workflow remains useful.

---

# 49. The Smallest Possible First Call

Your first API experiment should be intentionally simple.

You want:

```text
one endpoint
+
one authentication method
+
minimal JSON
+
one message
+
one response
```

The purpose is to establish:

```text
Can I successfully communicate with the provider?
```

Do not add unnecessary complexity to the first call.

---

# 50. What You Should Inspect Manually

When the request succeeds, don't immediately move on.

Inspect the response and identify:

```text
HTTP status

response identifier

model

content

stop reason

usage

other response metadata
```

Your objective is to understand the response object rather than merely extract the generated sentence.

---

# 51. Successful Response vs Successful Generation

These are subtly different ideas.

At the HTTP level:

```text
200
```

means the API request was successfully processed.

The model's generation still has its own outcome:

```text
stop_reason
```

For example, Anthropic documents `end_turn` as the normal natural completion reason and `max_tokens` when the generation reaches its configured maximum.

Therefore:

```text
HTTP success
    ≠
"I should ignore the response metadata."
```

---

# 52. First-Level Debugging Checklist

When your call fails:

### 401

```text
[ ] API key exists
[ ] API key is correct
[ ] API key is active
[ ] authentication header is correct
[ ] correct provider credential
```

### 400

```text
[ ] endpoint is correct
[ ] JSON is valid
[ ] required fields exist
[ ] field names are correct
[ ] field types are correct
[ ] model is valid
[ ] message structure is valid
```

### 429

```text
[ ] read exact error body
[ ] determine rate vs quota/spend issue
[ ] check Retry-After if provided
[ ] check provider limits/usage
[ ] retry only when appropriate
```

OpenAI specifically recommends following `Retry-After` when present for applicable 429 rate-limit responses; Anthropic similarly documents a `retry-after` header for rate-limit responses.

---

# 53. The Three Status Codes You Must Know

A useful memory model:

```text
400
BAD REQUEST
"Your request is wrong."

401
UNAUTHORIZED
"Your credentials are wrong."

429
TOO MANY REQUESTS / LIMIT
"Your access is currently limited."
```

But remember:

> This is first-level triage, not the complete diagnosis.

Always inspect the actual provider error payload because 429, in particular, can represent different usage/limit conditions.

---

# 54. Practical Engineering Questions

After completing this topic, you should be able to answer:

### Request

**What is an endpoint?**

The HTTP destination to which your API request is sent.

**Why do we need headers?**

They carry request metadata such as authentication and content type.

**Where does the API key go?**

In the authentication mechanism specified by the provider, not in the prompt/content itself.

**Why JSON?**

It provides a structured representation for request and response data.

---

### Messages

**What is `messages`?**

A structured collection representing the conversational input sent to a messages-style API.

**What is a role?**

Metadata describing the role associated with a message.

**Why does this connect to statelessness?**

Because conversation history can be represented as structured messages supplied with the request.

---

### Response

**What is `content`?**

The generated response content, whose exact structure depends on the provider.

**What is `usage`?**

Information about resource/token usage returned by the API.

**What is `stop_reason`?**

Information explaining why generation stopped, where the provider exposes it.

---

### Errors

**401?**

Authentication.

**400?**

Invalid request.

**429?**

Rate/usage/limit condition.

---

# 55. The Most Important Distinction

Do not memorize:

```text
401 = bad
400 = bad
429 = bad
```

Instead memorize:

```text
401 → authentication layer

400 → request layer

429 → usage/rate-limit layer
```

This gives you a debugging direction.

---

# 56. Topic 6 Completion Test

The syllabus says:

> **Done when: you make a raw HTTP call (no SDK), read every field of the response, and triage a 401 vs 400 vs 429 on sight.**

Break that into four tests.

### Test 1 — Raw HTTP

Can you make an LLM API request without an SDK?

```text
HTTP
endpoint
headers
authentication
JSON
```

### Test 2 — Request understanding

Can you explain every important part of the request?

```text
Why POST?
Why this endpoint?
Why this header?
Why this JSON?
Why these messages?
```

### Test 3 — Response understanding

Can you inspect the response and identify:

```text
content
usage
stop reason
metadata
```

without blindly extracting only the text?

### Test 4 — Error triage

If you see:

```text
401
```

do you immediately investigate authentication?

If you see:

```text
400
```

do you investigate the request?

If you see:

```text
429
```

do you investigate rate/usage limits?

If yes, the topic's core objective has been achieved.

---

# 57. Final Mental Model

Remember Topic 6 as:

```text
                 YOUR PYTHON PROGRAM
                         │
                         ↓
                  BUILD HTTP REQUEST
                         │
              ┌──────────┼──────────┐
              ↓          ↓          ↓
           endpoint   headers     JSON
                         │
                   authentication
                         │
                         ↓
                    LLM PROVIDER
                         │
                         ↓
                  HTTP RESPONSE
                         │
              ┌──────────┼──────────┐
              ↓          ↓          ↓
           status      JSON       metadata
              │          │
              │      ┌───┼────┐
              │      ↓   ↓    ↓
              │   content usage stop_reason
              │
        ┌─────┼─────┐
        ↓     ↓     ↓
       400   401   429
        │     │     │
      request auth  limit
```

The core skill is:

> **Understand the HTTP layer before using the SDK layer.**

Once you can make and inspect a raw LLM API call, the SDK becomes an abstraction you understand rather than a black box you depend on.

---

# 58. Sources

The syllabus specifies:

* OpenAI API documentation — official API documentation. [OpenAI API Docs](https://developers.openai.com/api/docs?utm_source=chatgpt.com)
* Anthropic API documentation — official API documentation. [Anthropic API Docs](https://platform.claude.com/docs?utm_source=chatgpt.com)

For the specific current details used in these notes, the official documentation covers OpenAI error codes and Anthropic's Messages API, response/stop reasons, and error handling.