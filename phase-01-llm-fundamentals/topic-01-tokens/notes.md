# Topic 1 — Tokens

## Overview

A token is the basic unit of text processed by a language model. A token may represent a complete word, part of a word, punctuation, whitespace, or another frequently occurring piece of text.

Before a language model processes text, the text is converted into tokens and those tokens are mapped to integer IDs from the model's vocabulary.

```text
Text
  ↓
Tokenization
  ↓
Tokens
  ↓
Token IDs
  ↓
Language Model
```

Understanding tokens is important because tokenization directly affects:

* Context-window limits
* Input and output costs
* Model latency
* Prompt size
* Text processing behavior
* Why apparently similar strings can consume different numbers of tokens

---

## 1. What Is a Token?

A token is **not necessarily a word or a character**.

For example, a tokenizer might represent:

```text
"hello"
```

as one token, while another string may be divided into multiple tokens.

A word can also be split into several tokens when the tokenizer does not contain the complete word as a single vocabulary entry.

The exact tokenization depends on the tokenizer and model family.

---

## 2. From Text to Token IDs

A simplified tokenization pipeline is:

```text
Raw Text
   ↓
Bytes / Text Representation
   ↓
BPE Tokenization
   ↓
Vocabulary Tokens
   ↓
Integer Token IDs
```

The model ultimately operates on token IDs rather than directly operating on human-readable text.

For example:

```text
"Hello world"
       ↓
["Hello", " world"]
       ↓
[Token_ID_1, Token_ID_2]
```

The exact IDs depend on the tokenizer being used.

---

## 3. Byte Pair Encoding (BPE)

Byte Pair Encoding is a commonly used tokenization approach.

The basic idea is to start from smaller units and repeatedly merge frequently occurring pairs.

Frequent patterns can therefore become single tokens, while uncommon text may require more tokens.

Conceptually:

```text
characters / bytes
       ↓
frequent pair
       ↓
merged unit
       ↓
larger token
```

This allows common patterns to be represented efficiently while still allowing the tokenizer to represent arbitrary text.

---

## 4. Vocabulary

A model's vocabulary is the fixed collection of tokens that its tokenizer can map to integer IDs.

Conceptually:

```text
Token              ID
----------------------
"hello"            15339
" world"           ...
"ing"              ...
"."                ...
```

The actual token IDs and vocabulary depend on the specific tokenizer.

Therefore, token counts should always be interpreted relative to the tokenizer being used.

---

## 5. Why Token Count Matters

### Context Windows

Models operate within a finite context window measured in tokens.

```text
Input tokens + Output tokens
              ↓
       Context limit
```

More tokens means less remaining space for the model's output or additional context.

### Cost

LLM APIs commonly measure usage in input and output tokens.

Therefore:

```text
More input tokens
        ↓
Higher input usage
        ↓
Potentially higher cost
```

Output tokens are also usage and may be priced separately.

### Latency

Processing more tokens generally means more computation, which can affect response latency.

---

## 6. Why Similar Text Can Have Different Token Counts

Tokenizers do not count words.

For example, these may have different tokenization:

```text
hello
Hello
HELLO
hellohello
hello-world
```

Differences can occur because tokenizers learn and store frequently occurring patterns.

Rare words, unusual formatting, identifiers, source code, URLs, and arbitrary strings can therefore behave differently from ordinary natural-language text.

---

## 7. Tokenization Is Model-Specific

There is no universal tokenization rule shared by every language model.

Different model families can use different:

* Tokenizers
* Vocabularies
* Token IDs
* Encoding schemes

Therefore, when token count matters, use the tokenizer associated with the model or API being used.

---

## 8. Verifying Token Counts

Token counts should be measured rather than guessed when accuracy matters.

For OpenAI-compatible tokenization, tools such as `tiktoken` can be used to inspect tokenization programmatically.

Example workflow:

```text
Input text
    ↓
Tokenizer
    ↓
Token IDs
    ↓
Count tokens
    ↓
Inspect individual tokens when necessary
```

A useful experiment is to compare the tokenization of:

```text
"hello"
"Hello"
"hello world"
"hello-world"
"a very long unusual identifier"
```

and investigate why their token counts differ.

---

## 9. Practical Consequences

Understanding tokenization helps explain several practical LLM behaviors.

### Cost

Longer prompts generally contain more tokens and can therefore increase usage.

### Context Limits

A conversation can exceed the model's context window even when it does not appear particularly long to a human.

### Prompt Design

Reducing unnecessary text can reduce token usage while preserving the information needed by the model.

### Code and Identifiers

Code, long identifiers, URLs, and unusual strings may tokenize less efficiently than ordinary language.

### Multilingual Text

Different languages and writing systems can have substantially different tokenization efficiency depending on the tokenizer.

---

## Key Takeaways

1. A token is a model-specific unit of text representation.
2. Tokens are mapped to integer IDs before being processed by the model.
3. Tokenization is performed on both input text and generated output.
4. BPE-based tokenizers represent frequent patterns efficiently.
5. Token count affects context usage, cost, and potentially latency.
6. Tokenization depends on the tokenizer and model family.
7. Token count should be measured with the appropriate tokenizer when precision matters.

---

## References

* [OpenAI Tokenizer](https://platform.openai.com/tokenizer)
* [OpenAI — What are tokens and how to count them](https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them)
* [OpenAI tiktoken](https://github.com/openai/tiktoken)
* [Andrej Karpathy — Intro to Large Language Models](https://www.youtube.com/watch?v=zjkBMFhNj_g)
* [Andrej Karpathy — Let's build the GPT Tokenizer](https://www.youtube.com/watch?v=zduSFxRajkE)

---

## Related Topics

This topic provides the foundation for understanding:

* Next-token prediction
* Context windows
* Token costs
* LLM API usage
* Prompt engineering
* Context engineering