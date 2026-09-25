# Topic 5 — Python Unassisted #1: Functions, Dicts, JSON

## 1. Purpose of This Topic

This topic is about becoming **independently productive in Python**.

The emphasis is not on learning every feature of Python. It is on being able to sit down with a problem involving:

* functions
* lists
* dictionaries
* JSON
* basic file handling
* tests

and write the solution yourself **without Copilot or autocomplete**.

The final standard is:

> **Your dict/JSON-munging functions should pass a pytest suite that you wrote yourself, with zero autocomplete.**

This is an important transition point in the curriculum because later AI Engineering work will repeatedly involve manipulating structured data:

```text
API response
    ↓
JSON
    ↓
Python dictionaries/lists
    ↓
transformation
    ↓
another dictionary/list
    ↓
JSON output
```

You need to be comfortable with this before moving deeper into AI engineering.

---

# 2. What You Are Expected to Learn

The syllabus gives four concrete areas:

1. Writing Python without Copilot
2. pytest basics
3. venv + pip hygiene
4. A strict policy: no autocomplete; tests prove correctness

The core Python capabilities are:

```text
functions
    ↓
lists
    ↓
dictionaries
    ↓
nested dictionaries/lists
    ↓
JSON loading
    ↓
data manipulation
    ↓
JSON dumping
    ↓
tests
```

This is deliberately narrower than "learn Python."

---

# 3. Functions

A function packages a piece of logic behind a name.

Basic structure:

```python
def function_name(parameter):
    # logic
    return result
```

For example, conceptually:

```text
input
  ↓
function
  ↓
output
```

A function allows you to separate **what a piece of logic does** from the rest of your program.

## Parameters

Parameters are the inputs a function expects.

```python
def add(a, b):
    return a + b
```

Here:

```text
a → first input
b → second input
```

Calling:

```python
add(2, 3)
```

produces:

```text
5
```

## Return values

A function can return a value:

```python
def square(x):
    return x * x
```

The important distinction is:

```text
print()
```

displays something.

```text
return
```

gives a value back to the caller.

For the exercises in this topic, your data-munging functions should generally produce values that can be tested.

---

# 4. Why Functions Matter for This Curriculum

You will eventually write functions that transform data.

For example:

```text
JSON data
    ↓
function
    ↓
filtered data
```

or:

```text
API response
    ↓
function
    ↓
selected fields
```

or:

```text
list of records
    ↓
function
    ↓
dictionary indexed by ID
```

The important skill is not memorizing syntax.

It is being able to look at a data-transformation problem and independently construct:

```python
def transform(data):
    ...
```

without relying on autocomplete.

---

# 5. Lists

A list stores an ordered collection of values.

Conceptually:

```text
[
    item1,
    item2,
    item3
]
```

Example:

```python
numbers = [10, 20, 30]
```

You should be comfortable with the basic operations needed to manipulate lists.

## Accessing elements

Python uses zero-based indexing.

```text
numbers[0] → first element
numbers[1] → second element
numbers[2] → third element
```

So:

```python
numbers[0]
```

returns:

```text
10
```

## Iterating

A common operation is processing every element:

```python
for number in numbers:
    ...
```

This pattern will appear constantly when working with structured data.

---

# 6. Dictionaries

A dictionary stores values associated with keys.

Conceptually:

```text
key → value
```

Example:

```python
user = {
    "name": "Alice",
    "age": 25
}
```

The dictionary contains:

```text
"name" → "Alice"
"age"  → 25
```

You access values through their keys.

```python
user["name"]
```

gives:

```text
Alice
```

---

# 7. Why Dictionaries Matter So Much

Dictionaries are one of the most important Python structures for AI Engineering.

A huge amount of application data eventually looks like:

```python
{
    "id": 123,
    "name": "Alice",
    "status": "active"
}
```

For example, API responses, configuration objects, model outputs, metadata, and application state can all contain dictionary-like structures.

Therefore, you should become comfortable with:

```text
creating dictionaries
reading values
changing values
adding keys
iterating over keys/values
checking whether keys exist
combining nested structures
```

---

# 8. Dictionary + List Combinations

Real data is rarely a single flat dictionary.

You will commonly encounter structures such as:

```python
[
    {
        "id": 1,
        "name": "Alice"
    },
    {
        "id": 2,
        "name": "Bob"
    }
]
```

This is:

```text
list
 ├── dictionary
 └── dictionary
```

You may also encounter:

```python
{
    "user": {
        "name": "Alice",
        "roles": ["admin", "developer"]
    }
}
```

This is:

```text
dictionary
 └── dictionary
      ├── string
      └── list
```

Understanding the **shape of the data** is therefore extremely important.

Before manipulating data, ask:

```text
What is the outer structure?

List?
Dictionary?

What is inside it?

What are the keys?

What are the value types?
```

---

# 9. Data Munging

The syllabus specifically uses the term **dict/JSON-munging functions**.

"Munging" here means transforming data from one useful structure into another.

For example:

```text
input data
    ↓
select fields
    ↓
filter records
    ↓
transform values
    ↓
produce output data
```

A function might conceptually perform:

```text
raw records
    ↓
keep only active records
    ↓
extract IDs and names
    ↓
return simplified records
```

The important skill is being able to manipulate nested lists and dictionaries deliberately.

---

# 10. JSON

JSON stands for **JavaScript Object Notation**.

It is a text-based format commonly used for structured data exchange.

A JSON object can look like:

```json
{
    "name": "Alice",
    "age": 25
}
```

A JSON array can look like:

```json
[
    {
        "id": 1,
        "name": "Alice"
    },
    {
        "id": 2,
        "name": "Bob"
    }
]
```

JSON is extremely important for AI engineering because APIs commonly exchange structured information using JSON.

---

# 11. JSON vs Python Dictionary

A common mistake is to think:

> "JSON is just a Python dictionary."

It isn't.

They are related representations, but they are not the same thing.

Conceptually:

```text
JSON
 ↓
text representation

Python dict
 ↓
Python object in memory
```

For example, this is Python:

```python
{
    "name": "Alice"
}
```

while this is JSON text:

```json
{
    "name": "Alice"
}
```

The syntax can look almost identical, but their roles are different.

A Python program can load JSON text into Python objects and later serialize Python objects back into JSON.

---

# 12. `json.load`

`json.load` is used to read JSON from a file.

Conceptually:

```text
JSON file
    ↓
json.load()
    ↓
Python object
```

For example:

```text
data.json
    ↓
Python program
    ↓
dictionary/list
```

Once loaded, you manipulate the resulting Python data using normal Python operations.

The important idea is:

> `json.load` crosses the boundary from JSON stored in a file into Python data structures.

---

# 13. `json.dump`

`json.dump` performs the reverse operation.

Conceptually:

```text
Python object
    ↓
json.dump()
    ↓
JSON file
```

So the overall workflow is:

```text
JSON file
   │
   │ json.load
   ↓
Python data
   │
   │ manipulate
   ↓
Python data
   │
   │ json.dump
   ↓
JSON file
```

You should be able to perform this cycle without autocomplete.

---

# 14. The Core JSON Workflow

A typical exercise should make you practice this entire pipeline:

```text
1. Open input JSON
        ↓
2. Load JSON
        ↓
3. Inspect its structure
        ↓
4. Manipulate dictionaries/lists
        ↓
5. Produce transformed data
        ↓
6. Write output JSON
        ↓
7. Test the transformation
```

The important part is not merely knowing:

```python
json.load
json.dump
```

It is being able to combine them with functions and data manipulation.

---

# 15. Functions + Dicts + JSON

This is the central combination of Topic 5.

A useful mental model is:

```text
                 JSON file
                    ↓
                json.load
                    ↓
             Python list/dict
                    ↓
              your function
                    ↓
            transformed data
                    ↓
                json.dump
                    ↓
                 JSON file
```

Your function should contain the transformation logic.

The file-handling layer should deal with loading and saving.

This separation makes the code easier to test.

---

# 16. Why Testing Matters

The syllabus explicitly says:

> tests prove correctness, not vibes

This is one of the most important principles in this topic.

Writing:

```python
print(result)
```

and seeing something that looks correct is not the same as proving your function works.

A test gives you an explicit expectation:

```text
Given X
I expect Y
```

The program either satisfies that expectation or it doesn't.

---

# 17. pytest

The syllabus uses **pytest** for testing.

pytest allows you to write tests using ordinary Python assertions.

The basic conceptual structure is:

```text
test input
    ↓
function
    ↓
actual result
    ↓
compare with expected result
```

For example, conceptually:

```python
assert actual == expected
```

The assertion either succeeds or fails.

---

# 18. Plain `assert`

The syllabus specifically requires understanding plain asserts.

An assertion expresses an expectation.

Conceptually:

```python
assert result == expected
```

If the condition is true:

```text
test passes
```

If false:

```text
test fails
```

This makes assertions useful for checking your data-munging functions.

---

# 19. What a Good Test Should Establish

Suppose you write a function that transforms a dictionary.

Don't only test the "happy path."

Think about what behavior you actually expect.

For example:

```text
input
  ↓
function
  ↓
expected output
```

Your test should make that expectation explicit.

For data transformation, useful questions include:

```text
Does the expected field exist?

Does the value have the expected value?

Are unwanted fields removed?

Are records transformed correctly?

Does the function handle an empty input?

What happens when expected data is missing?
```

Only test behavior that your function is actually supposed to support.

---

# 20. Running Tests

You should know how to run your pytest suite from the command line.

The important workflow is:

```text
write code
    ↓
write tests
    ↓
run pytest
    ↓
read result
    ↓
fix code
    ↓
run pytest again
```

The goal is to become comfortable with this loop.

Testing should not be something you do only after finishing everything.

---

# 21. Reading Failure Output

A major part of the syllabus is:

> reading failure output

A failing test is information.

When pytest reports a failure, you should identify:

```text
Which test failed?
        ↓
What assertion failed?
        ↓
What was expected?
        ↓
What was actually returned?
        ↓
Where did the failure originate?
```

For example, conceptually:

```text
Expected:
{"name": "Alice"}

Actual:
{"name": "Bob"}
```

The useful information is the difference between those two states.

Don't treat test output as something to blindly paste into an AI tool.

Read it.

Understand it.

Fix the underlying logic.

---

# 22. pytest Is Not the Functionality

Keep these responsibilities separate:

```text
Your function
    ↓
does the actual work

pytest
    ↓
checks whether the work is correct
```

pytest does not make the function correct.

It gives you evidence about whether the behavior matches your expectations.

This is why the syllabus says:

> tests prove correctness, not vibes.

---

# 23. venv

A virtual environment (`venv`) gives a project its own isolated Python environment.

Conceptually:

```text
System Python
     │
     ├── Project A environment
     │
     ├── Project B environment
     │
     └── Project C environment
```

Instead of treating every Python package as globally installed, a project can maintain its own environment.

This prevents unrelated projects from unnecessarily sharing the same installed dependencies.

---

# 24. Why venv Matters

Imagine:

```text
Project A
needs package version X

Project B
needs package version Y
```

A shared global environment can create dependency conflicts.

A project-specific environment gives you isolation.

The important mental model is:

```text
project
  ↓
virtual environment
  ↓
project dependencies
```

---

# 25. pip

`pip` is Python's package installer.

You use it to install Python packages into the environment you're working in.

For this topic, the important thing is not memorizing every pip command.

It is understanding the hygiene principle:

```text
activate project environment
        ↓
install required dependency
        ↓
use dependency
        ↓
keep project environment isolated
```

For example, pytest is an external Python package that belongs in the project's environment.

---

# 26. venv + pip Hygiene

The phrase **hygiene** is important.

Good project hygiene means knowing:

```text
Which Python environment am I using?

Where was this package installed?

Is this dependency project-specific?

Can another developer reproduce this environment?
```

You should avoid the mental model:

> "I installed something once, so Python has it."

Instead:

```text
This project
    ↓
uses this environment
    ↓
which contains these dependencies
```

---

# 27. The No-Autocomplete Policy

This is not an optional suggestion.

The syllabus explicitly states:

> **Policy: no autocomplete; tests prove correctness, not vibes.**

For this topic, you should deliberately work without:

* Copilot
* autocomplete
* AI-generated implementation
* blindly copying generated snippets

The purpose is to expose what you actually know.

---

# 28. Why No Autocomplete?

Autocomplete can hide gaps in basic Python fluency.

For example, if you cannot remember how to:

```text
iterate through a dictionary
access nested data
write a function
load JSON
write JSON
write an assertion
```

and autocomplete supplies the syntax every time, you may produce working code without actually being able to construct it independently.

This topic is specifically designed to remove that dependency.

---

# 29. What "Unassisted" Means

Unassisted does **not** mean:

> never look anything up in your entire life.

The syllabus specifically gives documentation and books as sources.

The important distinction is:

```text
Learning/reference:
"What does json.dump do?"
        ↓
consult documentation
```

versus:

```text
Implementation:
"Write this entire function for me."
        ↓
not allowed for this exercise
```

You should understand the difference between **looking up documentation** and **outsourcing your implementation**.

---

# 30. A Useful Working Rule

For Topic 5:

```text
Try yourself first
        ↓
Think through the data structure
        ↓
Write the function
        ↓
Write the test
        ↓
Run pytest
        ↓
Read the failure
        ↓
Debug yourself
```

Only use documentation when you genuinely need to verify Python/library behavior.

The implementation itself should come from you.

---

# 31. The Complete Topic 5 Mental Model

The entire topic can be represented as:

```text
                    Python
                      │
             ┌────────┴────────┐
             ↓                 ↓
          Functions        Data structures
                              │
                         ┌────┴────┐
                         ↓         ↓
                       Lists    Dictionaries
                                   │
                                   ↓
                                  JSON
                                   │
                    ┌──────────────┴──────────────┐
                    ↓                             ↓
               json.load                     json.dump
                    ↓                             ↑
                    └── Python transformation ────┘
                                   │
                                   ↓
                                pytest
                                   │
                           assert expected result
                                   │
                                   ↓
                              correctness
```

The key loop is:

```text
LOAD → TRANSFORM → TEST → FIX → TEST → SAVE
```

---

# 32. What You Should Be Able to Do Without Help

Before marking Topic 5 complete, you should be able to sit down with a fresh Python file and independently:

### Functions

* Define a function.
* Accept parameters.
* Return a value.
* Call your function.
* Break a transformation into sensible functions.

### Lists

* Create lists.
* Access elements.
* Iterate through lists.
* Transform/filter list contents when required.

### Dictionaries

* Create dictionaries.
* Access values by key.
* Add/change values.
* Iterate through dictionary data.
* Work with nested dictionaries.

### JSON

* Understand JSON as structured text.
* Load JSON from a file with `json.load`.
* Manipulate the resulting Python data.
* Write Python data to JSON with `json.dump`.

### pytest

* Create a basic test.
* Use plain `assert`.
* Run pytest.
* Identify a failing test.
* Read expected vs actual output.
* Fix the underlying implementation.

### Environment

* Create/use a virtual environment.
* Install project dependencies with pip.
* Understand that dependencies belong to the project environment.

### Discipline

* Write the implementation without Copilot/autocomplete.
* Use tests as evidence of correctness.

---

# 33. What Is NOT the Goal

Do not expand this topic unnecessarily.

The syllabus does **not** ask you to become a Python expert here.

Do not turn Topic 5 into a giant Python course covering every language feature.

The source specifically focuses on:

```text
functions
lists/dicts
JSON
pytest
venv
pip
unassisted implementation
```

Anything beyond that should only be introduced when another topic requires it.

---

# 34. Interview Perspective

The practical interview-level question behind this topic is not:

> "Do you know Python?"

It is closer to:

> "Can you take structured data, transform it correctly, and verify the behavior?"

You should eventually be able to explain a transformation like:

```text
"I receive structured JSON,
load it into Python,
transform the dictionaries/lists,
return the required structure,
and use pytest assertions to verify the behavior."
```

That is much more useful than simply memorizing Python syntax.

---

# 35. Common Failure Modes

### 1. Relying on autocomplete

You type half a statement and let the editor finish it.

**Problem:** you don't know whether you could reproduce the code independently.

---

### 2. Using `print()` instead of tests

You print the output and decide:

> "Looks correct."

**Problem:** visual inspection is not a reliable test.

---

### 3. Writing tests after everything is finished

You write a large function and only then think about testing.

**Problem:** failures become harder to localize.

---

### 4. Not understanding the data shape

You start manipulating a nested structure without first determining:

```text
list?
dict?
list of dicts?
dict containing lists?
```

**Problem:** most transformation errors originate from misunderstanding the structure.

---

### 5. Confusing JSON and Python objects

You treat JSON text and Python dictionaries as literally the same thing.

**Problem:** they are different representations connected through serialization/deserialization.

---

### 6. Installing packages globally without thinking

You install packages into whatever Python environment happens to be active.

**Problem:** project environments become difficult to reproduce and dependency conflicts become more likely.

---

# 36. How This Connects to AI Engineering

This topic may look basic compared with LLMs, RAG, and agents.

It is not disconnected from them.

Later you will encounter:

```text
LLM API response
       ↓
JSON
       ↓
Python dictionary
       ↓
extract information
       ↓
validate data
       ↓
store/use result
```

RAG systems:

```text
documents
    ↓
metadata dictionaries
    ↓
retrieval results
    ↓
JSON/API responses
```

Agent systems:

```text
tool call
    ↓
JSON arguments
    ↓
Python function
    ↓
tool result
    ↓
structured response
```

Evaluation:

```text
model output
    ↓
Python data
    ↓
evaluation function
    ↓
assertions/tests
```

LLMOps:

```text
configuration
    ↓
JSON/YAML-like structured data
    ↓
Python application
    ↓
validation/testing
```

So the skill being developed here is foundational:

> **You need to be able to manipulate the data flowing through AI systems without relying on an assistant to write the Python for you.**

---

# 37. Topic 5 Completion Test

Do not mark the topic complete because you watched a tutorial.

Mark it complete when you can satisfy the syllabus's actual condition:

> **Your dict/JSON-munging functions pass your own pytest suite, written with zero autocomplete.**

A useful final test is:

```text
Can I receive an unfamiliar JSON structure?

        ↓

Can I understand its shape myself?

        ↓

Can I write a function that transforms it?

        ↓

Can I write tests for that function?

        ↓

Can I run pytest?

        ↓

Can I understand a failure without asking AI?

        ↓

Can I fix the function?

        ↓

Can I serialize the result back to JSON?
```

If the answer is consistently **yes**, Topic 5 has achieved its purpose.

---

# 38. Source Material

The syllabus specifies these sources:

1. **pytest — Get Started**
   https://docs.pytest.org/en/stable/getting-started.html

2. **Composing Programs** — selective use
   https://www.composingprograms.com/

3. **Fluent Python, 2nd Edition** — paid reference
   https://www.oreilly.com/library/view/fluent-python-2nd/9781492056348/

Use these as references rather than trying to consume them cover-to-cover for this topic.

---

# 39. Final Mental Model

Remember Topic 5 as:

```text
I can write Python myself.

        ↓

I can manipulate lists and dictionaries.

        ↓

I can move between JSON files
and Python data.

        ↓

I can package transformations
inside functions.

        ↓

I can write tests for those functions.

        ↓

I can run pytest and understand failures.

        ↓

I can work inside an isolated
Python environment.

        ↓

I don't need autocomplete to do basic work.
```