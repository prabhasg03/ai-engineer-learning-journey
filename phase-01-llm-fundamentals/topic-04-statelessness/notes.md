# Topic 4 — Statelessness

**Before:** Topic 3 — Context Window

## Done When

You can narrate:

> **Where conversation state actually lives, and why cost grows on every turn even when nothing new is asked.**

You should be able to explain the complete chain:

```text
Stateless API
     ↓
Application maintains conversation history
     ↓
History is sent again on each request
     ↓
Input tokens increase
     ↓
Cost and processing increase
     ↓
Long conversations require compaction / summarization / other state-management strategies
```

---

# 1. What Does "Stateless" Mean?

A system is **stateless** when one request does not automatically carry the state of previous requests into the next request.

Consider two API calls.

### Request 1

```text
User:
What is Java?

Model:
Java is a programming language...
```

Later:

### Request 2

```text
User:
What are its main advantages?
```

If the second request contains only:

```text
What are its main advantages?
```

the model does not inherently know that **"its" refers to Java**.

The API call needs enough context for the model to understand the reference.

For example, the application may send:

```text
User:
What is Java?

Assistant:
Java is a programming language...

User:
What are its main advantages?
```

The model can now use the previous conversation because **the previous conversation was included in the current request**.

The important distinction is:

> The model can use previous conversation state when that state is provided to it, but the API call itself should not be assumed to remember arbitrary previous calls.

---

# 2. The Core Mental Model

Think of an LLM API as a function:

```text
response = model(current_request)
```

The model receives the input associated with the current request and produces an output.

For a conversational application, the application effectively constructs:

```text
conversation_history
        +
new_user_message
        ↓
      model
        ↓
   new_response
```

Then the application adds the new exchange to its stored history:

```text
conversation_history
        +
new_user_message
        +
assistant_response
        ↓
updated conversation_history
```

On the next turn:

```text
updated conversation_history
        +
next_user_message
        ↓
      model
```

So the model does not need to maintain the conversation itself.

The **application maintains the conversation state** and supplies it when needed.

---

# 3. Where Does Conversation State Actually Live?

This is the most important question in this topic.

Suppose you have:

```text
User:
Explain REST APIs.

Assistant:
A REST API is...

User:
Give me an example in Spring Boot.

Assistant:
...
```

Where is this conversation stored?

There are several possible places depending on the application architecture.

It may live in:

```text
Browser / mobile application
        ↓
Backend server
        ↓
Database
        ↓
Conversation history
```

Or a simpler application might maintain:

```text
conversation = [
    user_message_1,
    assistant_message_1,
    user_message_2,
    assistant_message_2
]
```

The important point is:

> **Conversation state belongs to the surrounding application architecture, not automatically to the stateless model API call.**

The application decides:

* whether history is stored
* where it is stored
* how much history is retained
* what gets sent to the model
* whether old messages are summarized
* whether some messages are removed
* whether retrieved information is inserted into the context

---

# 4. API Call vs Conversation

Do not confuse these two concepts.

## API call

An API call is one interaction with the model.

```text
Request → Model → Response
```

## Conversation

A conversation is a sequence of interactions.

```text
Request 1 → Response 1
Request 2 → Response 2
Request 3 → Response 3
...
```

The application creates the experience of a continuous conversation by carrying information from earlier interactions into later ones.

Therefore:

```text
Conversation
≠
one API call
```

Instead:

```text
Conversation
=
sequence of requests + responses
+
application-managed state
```

---

# 5. Why Does the History Need to Be Resent?

Suppose the user starts a conversation.

### Turn 1

```text
User:
I am learning Java.
```

Application sends:

```text
I am learning Java.
```

The model responds:

```text
Great. Java is...
```

Now the user asks:

### Turn 2

```text
Explain inheritance.
```

For the model to understand the previous context, the application may send:

```text
User:
I am learning Java.

Assistant:
Great. Java is...

User:
Explain inheritance.
```

The model processes the supplied context and generates the response.

---

# 6. Third Turn

Now the user asks:

```text
Give me a simple example.
```

The application may send:

```text
User:
I am learning Java.

Assistant:
Great. Java is...

User:
Explain inheritance.

Assistant:
Inheritance allows...

User:
Give me a simple example.
```

Notice what happened.

The latest request contains not only:

```text
Give me a simple example.
```

It may also contain the previous conversation.

This is the fundamental source of the cost-growth problem.

---

# 7. History Growth = Cost Growth

Imagine a conversation with the following approximate input sizes.

### Turn 1

```text
History = 100 tokens
New message = 20 tokens

Total input = 120 tokens
```

### Turn 2

```text
Previous history = 120 tokens
New message = 20 tokens

Total input = 140 tokens
```

### Turn 3

```text
Previous history = 140 tokens
New message = 20 tokens

Total input = 160 tokens
```

### Turn 4

```text
Previous history = 160 tokens
New message = 20 tokens

Total input = 180 tokens
```

The user may only be typing:

```text
Yes.
```

or:

```text
Continue.
```

But the application may still need to send the relevant previous conversation.

Therefore:

> **A short new message does not necessarily mean a small request.**

The total input can be dominated by the accumulated conversation history.

---

# 8. The Important Distinction: New Information vs Resent Information

This is where the concept becomes intuitive.

Suppose the conversation contains:

```text
10,000 tokens of previous history
```

and the user adds:

```text
5 new tokens
```

The new information is only:

```text
5 tokens
```

But the model may receive:

```text
10,005 tokens
```

The previous 10,000 tokens are not new information.

They are **context being supplied again** so the model can use them.

This is why conversational systems need to think carefully about context management.

---

# 9. "Even When Nothing New Is Asked"

This is specifically part of your **Done When** requirement.

Suppose the user says:

```text
User:
Continue.
```

That message contains almost no information.

But imagine the conversation already contains:

```text
20,000 tokens
```

The application might send:

```text
20,000 previous tokens
+
"Continue."
```

So the model still has to process a large context.

The user added almost nothing.

But the **request context is still large**.

This explains the statement:

> **Cost can grow even when the user's new message remains small.**

The growth comes from the accumulated history.

---

# 10. A Simple Cost Model

A simplified way to think about request cost is:

```text
Request cost ≈ input tokens + output tokens
```

If conversation history is included:

```text
Input tokens
=
history tokens
+
new user tokens
+
system/developer instructions
+
other supplied context
```

As history grows:

```text
history ↑
   ↓
input tokens ↑
   ↓
processing ↑
   ↓
potential cost ↑
```

The exact pricing and implementation details depend on the model/API, so this is a conceptual model rather than a universal billing formula.

---

# 11. Why Long Conversations Become an Engineering Problem

Imagine a conversation that grows like this:

```text
Turn 1    → 500 tokens
Turn 2    → 1,000 tokens
Turn 3    → 1,500 tokens
Turn 4    → 2,000 tokens
...
Turn 20   → 10,000 tokens
...
Turn 50   → 25,000 tokens
```

Eventually you encounter several problems.

### Problem 1 — Context window

The model has a maximum context capacity.

```text
history + new input + output
```

must fit within the applicable context limits.

### Problem 2 — Cost

More input tokens can mean more token usage.

### Problem 3 — Latency

Larger requests can require more processing.

### Problem 4 — Context quality

A very large history may contain information that is no longer relevant.

### Problem 5 — State management

The application needs strategies for deciding what to retain.

This leads directly to:

> **Compaction**

---

# 12. What Is Compaction?

Compaction means reducing the amount of conversation history that needs to be carried forward while attempting to preserve the information that matters.

For example, instead of keeping:

```text
User:
I am building a Spring Boot application.

Assistant:
Great...

User:
I am using MySQL.

Assistant:
...

User:
The application has three services.

Assistant:
...

User:
I want JWT authentication.

Assistant:
...
```

the application might create a summary:

```text
Project:
- Spring Boot application
- MySQL database
- Three microservices
- JWT authentication
```

Then future requests can use the compact representation.

Conceptually:

```text
Long history
     ↓
Summarization / compaction
     ↓
Smaller state representation
     ↓
Future requests
```

The exact compaction strategy is an engineering choice.

---

# 13. Why Compaction Is Necessary

Without some form of state management, a long-running conversation can become increasingly expensive and eventually run into context limits.

The chain is:

```text
Conversation continues
        ↓
History grows
        ↓
More history needs to be supplied
        ↓
Input token count grows
        ↓
Cost / processing can grow
        ↓
Context window becomes a constraint
        ↓
Application needs state management
```

That is why conversation state is an **engineering concern**, not merely a UI feature.

---

# 14. Things That Look Like Memory but Aren't

This is one of the most important parts of the topic.

Users often see a chatbot continue a conversation and conclude:

> "The model remembers everything."

That conclusion is too simplistic.

Several different mechanisms can create the appearance of memory.

---

# 15. Chat Products

A chat product may display:

```text
Conversation history
```

and automatically include relevant previous messages in later requests.

From the user's perspective:

```text
I said this yesterday.
The chatbot remembers it.
```

But internally, the product may be maintaining conversation state and supplying appropriate context.

The UI experience should not be treated as proof that the underlying model API is itself maintaining arbitrary persistent memory.

---

# 16. Stored Threads

An application may store conversations in a database.

For example:

```text
Database

conversation_id: 123

messages:
    user → ...
    assistant → ...
    user → ...
    assistant → ...
```

When the user returns, the application retrieves the stored conversation.

Then:

```text
Database
   ↓
Retrieve relevant state
   ↓
Construct request
   ↓
Model
```

From the user's perspective, it looks like:

> "The model remembered me."

Architecturally, the important fact is:

> **The application retrieved stored state and supplied it to the model.**

---

# 17. Cached Prefixes

Caching is another thing that can look like memory.

Suppose every request starts with a large common prefix:

```text
System instructions
+
large conversation history
+
new user message
```

An infrastructure layer may cache or reuse some computation associated with a repeated prefix.

This can reduce repeated computational work or affect billing/latency depending on the specific API and caching mechanism.

But:

```text
Caching ≠ memory
```

A cache is an optimization for previously processed information.

It does not mean:

> "The model independently remembers the conversation."

The conceptual distinction is:

```text
Memory/state:
"What information should be available?"

Caching:
"Can previously processed information be reused efficiently?"
```

These are different engineering concerns.

---

# 18. Stored Threads ≠ Model Memory

Consider:

```text
User
 ↓
Chat application
 ↓
Database
 ↓
Conversation history
 ↓
Request construction
 ↓
LLM
```

The database may preserve the conversation for days or years.

The model does not necessarily need to have retained the conversation internally.

The application can simply retrieve the information again.

Therefore:

```text
Persistence
≠
Model memory
```

A database is persistent storage.

A model inference call is a computation over supplied context.

---

# 19. Three Different Concepts

Keep these separate:

| Concept              | Purpose                                             |
| -------------------- | --------------------------------------------------- |
| Conversation history | Previous messages supplied as context               |
| Persistent storage   | Keeps information between sessions                  |
| Caching              | Reuses previously processed information efficiently |

All three can contribute to a product that **appears** to remember.

But they are not the same thing.

---

# 20. The API Boundary

Think of the architecture like this:

```text
                 APPLICATION
        ┌───────────────────────────┐
        │                           │
User →  │ conversation state        │
        │ database                  │
        │ retrieval                 │
        │ summarization             │
        │ context construction      │
        │                           │
        └─────────────┬─────────────┘
                      │
                      ↓
                 LLM API
                      │
                      ↓
                    Model
                      │
                      ↓
                  Response
                      │
                      ↓
              Application stores
                  new state
```

This makes the boundary clear.

The application is responsible for deciding what context reaches the model.

---

# 21. Statelessness Does Not Mean "No State Anywhere"

This is an important distinction.

**Stateless API** does not mean:

```text
There is no state in the entire system.
```

It means:

```text
The individual model request does not inherently carry
the state of previous independent requests.
```

The overall application can be highly stateful.

For example:

```text
Application:
stateful

Database:
stateful

Conversation:
stateful

Individual model invocation:
stateless
```

That combination is perfectly possible.

---

# 22. Why This Architecture Is Useful

Stateless inference has an important engineering property:

Any request can be reconstructed from the context supplied to it.

Conceptually:

```text
same model
+
same request/context
≈
same underlying inference conditions
```

The application can therefore control:

* what the model sees
* what previous information is included
* what instructions are included
* what retrieved documents are included
* what user preferences are included
* what information is omitted

This makes **context construction** a major part of AI application engineering.

---

# 23. Conversation History Is Not Necessarily the Best Context

Suppose a user has a 100-message conversation.

Not every message is still relevant.

For example:

```text
Turn 1:
What is Python?

Turn 2:
Explain variables.

Turn 3:
Explain lists.

...

Turn 80:
My current project uses FastAPI.

Turn 81:
I have PostgreSQL.

Turn 82:
How should I structure authentication?
```

For Turn 82, sending every historical message may be unnecessary.

The application might instead construct:

```text
Relevant project facts
+
recent conversation
+
current question
```

This is an important transition toward later concepts such as:

* context engineering
* retrieval
* summarization
* memory systems
* RAG

But do not go deeply into those here.

---

# 24. Statelessness → Client-Side History

Your syllabus gives this exact implication chain.

Let's derive it step by step.

## Step 1 — Statelessness

The model call does not automatically know previous independent calls.

```text
Request 1
Request 2
Request 3
```

are separate requests.

---

## Step 2 — Somebody must preserve history

If the application wants conversational behavior:

```text
previous messages
```

must be stored somewhere.

That responsibility belongs to the surrounding application/system.

---

## Step 3 — History is included in future requests

The application constructs:

```text
history
+
new message
```

and sends that context to the model.

---

## Step 4 — History grows

Every conversation turn can add:

```text
user message
+
assistant response
```

to the history.

Therefore:

```text
history length ↑
```

---

## Step 5 — Request size grows

Future requests may contain more historical context:

```text
request size ↑
```

---

## Step 6 — Cost curve grows

More input tokens can mean:

```text
more token usage
+
more processing
```

and potentially greater cost.

---

## Step 7 — Compaction becomes necessary

Eventually the application needs to decide:

```text
What should we keep?
What can we remove?
What can we summarize?
What should be retrieved only when needed?
```

That is the beginning of **state management**.

---

# 25. A Concrete Example

Imagine a customer-support chatbot.

### Turn 1

```text
User:
My order number is 12345.
```

The application stores:

```text
order = 12345
```

### Turn 2

```text
User:
It hasn't arrived.
```

The application needs to understand:

```text
"It" → order 12345
```

It could provide the relevant previous context.

### Turn 3

```text
User:
Where is it now?
```

Again, relevant state must be available.

But imagine the conversation now contains 100 unrelated messages.

Sending everything may be inefficient.

A better state representation might be:

```text
Customer:
User

Current order:
12345

Issue:
Order has not arrived

Relevant conversation:
recent messages
```

This is much smaller than the entire transcript.

---

# 26. Why "The Model Remembers" Is Often an Incomplete Explanation

Consider this statement:

> "The chatbot remembers that I told it my project uses Spring Boot."

That observation may be true from the user's perspective.

But there are multiple possible implementations:

```text
1. Full conversation history
2. Stored conversation + retrieval
3. Summarized conversation
4. Explicit user profile/state
5. Retrieved external information
6. Some combination of these
```

Therefore, "the model remembers" does not tell you **where the state lives**.

As an AI engineer, you should ask:

```text
Where is the state stored?
When is it retrieved?
How is it represented?
How much of it is sent to the model?
When is it compacted?
```

---

# 27. Statelessness and Context Windows

Topic 3 introduced the context window.

Topic 4 connects that concept to real applications.

The model has a finite amount of context it can process for a request.

Therefore:

```text
conversation history
+
system instructions
+
retrieved context
+
current user message
+
requested output
```

must fit within the applicable limits.

As history grows:

```text
available space for new context/output
```

can decrease.

So statelessness and context windows are closely connected:

```text
Stateless API
      ↓
Application resends relevant state
      ↓
Context grows
      ↓
Context window becomes a constraint
```

---

# 28. Statelessness and Cost Are Different From Context Limits

Do not merge these concepts.

### Cost problem

Large context can increase token usage.

### Context-window problem

Too much context can exceed the model's applicable limit.

### Quality problem

Too much irrelevant history can make context less useful.

### Latency problem

Larger requests can require more processing.

So:

```text
Growing history
```

can create several different engineering problems simultaneously.

---

# 29. Why the Application Controls the Cost Curve

Suppose two applications use the same model.

### Application A

Sends:

```text
entire conversation
```

every turn.

### Application B

Sends:

```text
compact summary
+
relevant facts
+
recent messages
```

The applications may therefore create very different token usage patterns even though they use the same underlying model.

This demonstrates an important AI engineering principle:

> **Model choice is only one part of system efficiency; context construction also matters.**

---

# 30. Statelessness Does Not Mean Every Request Must Resend Everything

Be careful here.

The syllabus says:

> "conversation is a list you resend each turn"

This is the core conceptual model for understanding stateless conversational APIs.

In real systems, however, an application may use:

* summaries
* retrieval
* structured state
* cached prefixes
* server-side conversation abstractions
* other context-management mechanisms

Therefore the deeper principle is:

> **The application must provide the model with whatever state/context is required for the current request.**

It does not necessarily mean the literal full transcript must always be transmitted unchanged.

---

# 31. The Difference Between State and Context

These terms are related but not identical.

### State

Information that persists across interactions.

Example:

```text
user prefers Java
current project = Spring Boot API
order ID = 12345
```

### Context

Information actually supplied to the model for a particular inference.

Example:

```text
Current project:
Spring Boot API

User:
How should I implement authentication?
```

A piece of state may exist in the application but not be included in a particular model request.

Therefore:

```text
Stored state
≠
model context
```

The application chooses what state becomes context.

This distinction becomes increasingly important later in context engineering.

---

# 32. The "Memory" Illusion

From the user's perspective:

```text
I told the system something earlier.
        ↓
Later I ask about it.
        ↓
System knows it.
```

It feels like:

```text
model memory
```

But the architecture may actually be:

```text
User
 ↓
Application
 ↓
Retrieve stored state
 ↓
Construct context
 ↓
LLM
 ↓
Answer
```

The important engineering question is not:

> "Does the model remember?"

Instead ask:

> **"What mechanism makes the information available to the model at inference time?"**

That is the better question.

---

# 33. Conversation State Lifecycle

A useful mental model is:

```text
USER MESSAGE
     ↓
APPLICATION
     ↓
STORE / UPDATE STATE
     ↓
SELECT RELEVANT STATE
     ↓
BUILD CONTEXT
     ↓
LLM API
     ↓
MODEL
     ↓
RESPONSE
     ↓
APPLICATION
     ↓
STORE / UPDATE STATE
     ↓
NEXT TURN
```

Notice the loop.

The model sits inside a larger state-management system.

---

# 34. What Happens When History Becomes Too Large?

The application has several conceptual options.

### Option 1 — Keep everything

```text
Full history
```

Simple, but history continues growing.

### Option 2 — Truncate

Remove old messages.

```text
recent history only
```

Cheap, but potentially loses important information.

### Option 3 — Summarize

Convert old conversation into a compact representation.

```text
old history
   ↓
summary
```

### Option 4 — Retrieve selectively

Keep information in storage and retrieve only relevant pieces.

```text
stored information
      ↓
relevance selection
      ↓
context
```

### Option 5 — Structured state

Store important facts separately:

```text
user_name
project
preferences
current_task
constraints
```

Real systems can combine these strategies.

You will study the deeper design of these approaches later. For Topic 4, understand **why they become necessary**.

---

# 35. Common Misconceptions

## Misconception 1

> "The model remembers every previous API call."

Better understanding:

```text
Previous state must be available through the system's
conversation/state-management mechanism.
```

---

## Misconception 2

> "If my new message is only two words, the request is tiny."

Not necessarily.

If the conversation history is large:

```text
large history
+
two-word message
=
large request context
```

---

## Misconception 3

> "Chat history displayed in the UI proves model memory."

Not necessarily.

The UI can be backed by:

```text
database
+
retrieval
+
context construction
```

---

## Misconception 4

> "Caching means the model remembers."

No.

```text
Caching → reuse/optimization
Memory/state → information persistence/availability
```

---

## Misconception 5

> "Stateless means the whole application has no state."

No.

The application can be highly stateful while individual inference calls remain stateless.

---

# 36. Interview-Level Explanation

If an interviewer asks:

> **"How does conversation memory work with an LLM API?"**

A strong answer is:

> "An individual LLM API invocation should be treated as stateless with respect to previous independent calls. A conversational application maintains the conversation state externally and supplies the relevant history or other state as context for subsequent requests. As the conversation grows, repeatedly carrying that history increases input-token usage and can eventually create cost, latency, context-window, and relevance problems. Applications therefore use techniques such as truncation, summarization, retrieval, structured state, or caching to manage the context."

That answer demonstrates that you understand the architecture rather than simply saying:

> "ChatGPT remembers previous messages."

---

# 37. Interview Follow-Up: Where Is the Memory?

If asked:

> "So where is the memory?"

Answer conceptually:

```text
It depends on the application architecture.

It may be stored in:
- application memory
- a database
- a conversation store
- a cache
- external storage

The application then decides what information to provide
to the model as context.
```

The critical idea is:

```text
storage/state
      ↓
context construction
      ↓
model
```

---

# 38. Interview Follow-Up: Why Does Cost Grow?

Answer:

> "Because conversational applications often include previous history in subsequent requests. Even if the new user message is tiny, the accumulated history can make the total input large. Since token usage is associated with the request's input and output, growing history can increase token usage and therefore potentially increase cost."

---

# 39. Interview Follow-Up: Why Not Just Keep Everything?

Because:

```text
history ↑
```

can cause:

```text
cost ↑
latency ↑
context pressure ↑
irrelevant information ↑
```

and eventually the application needs to manage the context deliberately.

---

# 40. Connection to Future Topics

Do not study these deeply yet, but understand the direction.

### Statelessness

```text
How does state get carried between requests?
```

### Context Engineering

```text
What information should actually be given to the model?
```

### RAG

```text
What external information should be retrieved?
```

### Agents

```text
How should state evolve across multiple tool interactions?
```

### Evaluation

```text
How do we determine whether the system preserved the right information?
```

### LLMOps

```text
How do we monitor token usage, latency, cost, and system behavior?
```

Topic 4 is therefore a foundational engineering concept.

---

# 41. The Complete Implication Chain

Memorize this:

```text
LLM API call is stateless
            ↓
Previous state isn't automatically available
            ↓
Application must maintain state
            ↓
Conversation history/state is stored somewhere
            ↓
Relevant state must be supplied to future requests
            ↓
History/context can grow over time
            ↓
Input token usage can grow
            ↓
Cost and processing can grow
            ↓
Context limits can become a constraint
            ↓
Application needs state/context management
            ↓
Compaction / summarization / retrieval / truncation
```

This is the core of Topic 4.

---

# 42. One Important Mental Model

Think of the LLM as a function:

```text
              CONTEXT
                 ↓
           ┌───────────┐
           │    LLM    │
           └───────────┘
                 ↓
              OUTPUT
```

The surrounding application creates the context:

```text
                    APPLICATION
                         │
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
  conversation       stored state      retrieved data
     history
        │                │                │
        └────────────────┼────────────────┘
                         ↓
                    CONTEXT
                         ↓
                       LLM
                         ↓
                      OUTPUT
```

So the LLM is one component inside the larger system.

---

# 43. What You Should Be Able to Explain Without Notes

You should be able to answer these from memory:

### 1. What does stateless mean?

An individual API invocation does not automatically carry arbitrary state from previous independent calls.

### 2. Where does conversation state live?

In the surrounding application/system, such as its memory, database, conversation store, or other state-management mechanism.

### 3. Why does history increase cost?

Because relevant previous context may be included in subsequent requests, increasing input-token usage.

### 4. Why can a tiny new message still be expensive?

Because the accumulated history can be much larger than the new message.

### 5. Is a chat product itself proof that the model has persistent memory?

No. The product can store and retrieve conversation state and provide it as context.

### 6. Is caching the same as memory?

No. Caching is primarily an optimization for reusing previously processed information.

### 7. Why does compaction become necessary?

Because unbounded history can increase token usage, processing, context pressure, and irrelevant information.

---

# 44. Topic 4 Summary

The central idea is:

> **The model does not need to independently remember previous API calls for a conversational application to appear stateful. The application can store conversation state and provide relevant state as context on later requests.**

The resulting engineering chain is:

```text
STATELESS API
      ↓
APPLICATION-MANAGED STATE
      ↓
HISTORY / STATE PROVIDED AS CONTEXT
      ↓
HISTORY GROWS
      ↓
TOKEN USAGE GROWS
      ↓
COST / PROCESSING / CONTEXT PRESSURE
      ↓
STATE & CONTEXT MANAGEMENT
      ↓
COMPACTION / SUMMARIZATION / RETRIEVAL / TRUNCATION
```

The most important distinction to remember:

```text
MODEL
  ≠
CONVERSATION SYSTEM
```

A conversational AI product is a **system built around the model**.

The system is responsible for maintaining and constructing the state/context that allows the model to respond coherently across turns.

---

# 45. Final Mental Model

```text
              USER
               │
               ▼
        ┌──────────────┐
        │ APPLICATION  │
        │              │
        │ Store state  │
        │ Retrieve     │
        │ Select       │
        │ Compact      │
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │   CONTEXT    │
        │              │
        │ History      │
        │ State        │
        │ Instructions │
        │ Other data   │
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │     LLM      │
        │              │
        │  Inference   │
        └──────┬───────┘
               │
               ▼
            RESPONSE
               │
               ▼
        APPLICATION
               │
               ▼
          UPDATE STATE
               │
               └──────────────→ NEXT TURN
```

**One sentence to remember:**

> **Statelessness means the application, not the individual API call, is responsible for carrying the relevant conversation state forward—and as that state grows, repeatedly supplying it can increase token usage, cost, processing, and context pressure.**
