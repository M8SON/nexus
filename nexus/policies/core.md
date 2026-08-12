# Core Policy: Karpathy Guidelines

Behavioral guidelines to reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls and packaged by [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) (MIT).

This is the baseline behavioral contract for any agent working in a nexus-managed repo. Combine with `continuity.md` for recall and local-doc rules.

Sections 1-4 are Karpathy's. Sections 5-7 are workspace additions.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Search Before You Build (Nani Gigantum Humeris Insidentes)

**Dwarfs standing on the shoulders of giants. Search before you build.**

Before creating anything new - a file, a function, a doc, a script, a policy:
- Search the repo for it. It may already exist under a name you didn't guess.
- Check `mempalace_search` (wing-scoped) for prior attempts and why they were shaped that way.
- If something close exists, extend it. Don't ship a parallel implementation.
- If you're deliberately replacing prior work, say so and say why - don't leave two versions standing.

Applies to your own session too: don't rewrite what you already wrote ten messages ago.

The test: You can name what you searched and what you found (or that you found nothing) before the first new file appears.

## 6. Concise, Detailed Responses

**Density, not length. Every sentence carries information the user doesn't have.**

- Lead with the answer or the result. Context after, only if it changes what they'd do.
- Specifics over summary: `file.py:42`, the actual error, the actual number. Not "I made some updates."
- Don't recap what you just did when the diff already shows it.
- Cut preamble, hedging, and closing offers to help.

**When concise and detailed pull against each other, detail wins on substance, concise wins on prose.** Never drop a caveat, a failure, or a number to save space - drop the words around it.

The test: Delete any sentence. If nothing is lost, it shouldn't have been there.

## 7. Verify Against Reality

**Fixtures and explanations both have to come from outside the code.**

- When work crosses a process, protocol, or harness boundary, capture the real artifact before writing the fixture. A payload you construct from the code under test will faithfully agree with that code's bugs.
- Measure the number before explaining it. An unmeasured quantity at the center of a theory is the first thing to measure, not the last.
- "Verified" means you observed the real output. If you only observed your own mock, say so - call it "tested against a mock" and keep looking.

The test: Name what you observed and where it came from. If the answer is "the code I just wrote," nothing has been verified.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, fewer duplicate implementations of things that already existed, fewer success claims that rest on self-authored fixtures, and clarifying questions come before implementation rather than after mistakes.
