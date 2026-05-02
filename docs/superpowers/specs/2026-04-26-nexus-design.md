# Nexus Design

Date: 2026-04-26
Status: Draft for review

## Overview

`nexus` is a shared local framework for coding assistants across repositories
under `/home/daedalus/linux`.

It combines:

- automatic session recall
- automatic local-document recall
- shared behavior policies
- reusable skills and prompts
- thin Claude and Codex adapters

`nexus` is local-first, agent-agnostic, and designed to become the common
behavior layer for both Claude and Codex when working inside the user's Linux
workspace.

## Goals

- Provide better continuity across sessions and repos without requiring the user
  to manually invoke recall.
- Reuse one shared instruction and skill system for both Claude and Codex.
- Preserve local, private, deterministic behavior.
- Absorb the existing `claude-recall` functionality into a larger shared
  assistant framework.
- Support broader future memory behavior without forcing that complexity into
  phase 1.

## Non-Goals

- Hosted or networked memory services.
- A vendor-specific framework tied only to Claude or only to Codex.
- Replacing repo-specific docs such as `README.md`, `CLAUDE.md`, or
  `WORKING_MEMORY.md`.
- Building phase 2 active-memory automation in the first implementation pass.

## Scope

Phase 1 includes:

- a new repo at `/home/daedalus/linux/nexus`
- migration of `claude-recall` into `nexus`
- automatic session recall
- automatic local-doc recall
- shared agent-agnostic policies and skills/prompts
- thin Claude and Codex adapters
- global activation for repos under `/home/daedalus/linux`

Phase 2 is deferred but explicitly designed for:

- proactive mid-task recall
- smarter memory escalation behavior
- unified token budget visibility and reminders
- better session compaction and handoff behavior

## Architecture

Recommended layout:

- `nexus/recall/`
  - migrated BM25/sqlite transcript recall engine from `claude-recall`
  - incremental indexing of session transcripts
  - search and filtering APIs
- `nexus/project_context/`
  - local-doc discovery
  - ranking and summarization helpers
  - project-state context assembly
- `nexus/policies/`
  - portable markdown policy layers
  - shared coding, review, debugging, planning, and verification rules
- `nexus/skills/`
  - reusable agent-agnostic prompt and workflow documents
- `nexus/adapters/claude/`
  - Claude-facing entry files and references
- `nexus/adapters/codex/`
  - Codex-facing entry files and references
- `nexus/cli/` or `nexus/bin/`
  - user and adapter-facing commands such as `nexus recall`, `nexus index`,
    `nexus context`, and `nexus doctor`
- `docs/`
  - specs, plans, migration notes, and operating documentation

## Recall Model

Phase 1 automatic recall has two sources:

1. Session recall
- Uses the migrated `claude-recall` engine.
- Searches prior Claude-style session transcripts using BM25 over sqlite/FTS5.
- Keeps incremental indexing and lightweight local storage.

2. Local-doc recall
- Searches project documents such as:
  - `README.md`
  - `WORKING_MEMORY.md`
  - `CLAUDE.md`
  - specs under `docs/superpowers/specs/`
  - plans under `docs/superpowers/plans/`
- Produces compact context summaries instead of dumping raw file contents.

The output of recall is a compact working-context summary for the agent, not a
verbatim transcript dump.

## Recall Policy

Recall is automatic for substantive work.

The default policy is tiered:

- light recall for straightforward tasks
- broader recall when the task looks like:
  - follow-up work
  - debugging
  - design continuation
  - repo-history-sensitive changes
  - work that references prior decisions

This keeps continuity high without paying broad-context cost for every trivial
request.

## Activation Model

`nexus` is globally active for repositories under `/home/daedalus/linux`.

Behavioral rule:

- if the active repo is under `/home/daedalus/linux`, agents should use
  `nexus`
- if the task is substantive, automatic recall should run
- if the task is small or trivial, heavy recall may be skipped unless prior
  context likely matters

Activation happens through thin agent-specific adapters:

- Claude adapter
  - references shared `nexus` policies, recall workflow, and skills
- Codex adapter
  - references the same shared framework in Codex-compatible form

The adapters should remain thin. Shared logic belongs in `nexus`, not in
duplicated agent-specific files.

## Policies and Skills

`nexus` includes shared behavior layers inspired by the
`forrestchang/andrej-karpathy-skills` idea, but adapted for a local multi-agent
workflow.

Core policy themes:

- think before coding
- prefer simple solutions
- make surgical changes
- verify before claiming success
- surface assumptions and tradeoffs clearly
- treat recall as a normal part of good continuation, not an optional extra

Skill/prompt areas should include:

- planning
- debugging
- code review
- implementation hygiene
- verification discipline
- continuity and recall usage

These should be authored to be reusable by both Claude and Codex rather than
hard-coded to one tool's format.

## Migration of `claude-recall`

`claude-recall` should be absorbed into `nexus`, not remain as a permanent
separate dependency.

Migration intent:

- move or port the existing BM25/sqlite indexing and query functionality into
  `nexus/recall/`
- preserve its practical strengths:
  - no daemon
  - stdlib-friendly implementation
  - incremental indexing
  - cheap local recall
- extend it with local-doc recall and adapter-facing context assembly

The old `claude-recall` repo should only be deleted after:

- `nexus` is functional
- references are repointed
- the replacement flow has been validated

## Agent Transparency

Agents should not use `nexus` invisibly in ways that confuse the user.

When recall materially shapes the current task, the agent should briefly say so.
This should stay concise and operational, not verbose.

Examples:

- "I pulled prior session context before making this change."
- "I checked project docs and prior design notes because this looks like a continuation."

## Phase 2: Future Active Memory and Agent Telemetry

This section is deferred, but must be preserved as intentional future scope.

Future capabilities:

- proactive recall
  - agents query `nexus` mid-task when they detect ambiguity, missing context,
    likely prior work, or follow-up risk
- memory escalation policy
  - start with light recall, broaden only when confidence is low or continuity
    matters
- token visibility
  - normalize token-budget reporting for both Claude and Codex
  - show estimated remaining context budget and warning thresholds where
    possible
- reminder hooks
  - proactively warn the user before context pressure becomes severe
- session compaction support
  - produce better carry-forward summaries when sessions get large
- user-facing transparency
  - when proactive recall or token warnings trigger, agents should mention it
    briefly

Phase 2 should improve behavior, but it should not block phase 1 from shipping.

## Testing Strategy

Phase 1 should be validated with:

- unit tests for migrated recall/index/query behavior
- unit tests for local-doc discovery and ranking
- tests for context assembly output shape
- tests for activation-policy decisions
- manual validation in at least one Claude-driven repo and one Codex-driven repo

Migration safety checks:

- verify the new recall engine returns equivalent or better results than
  `claude-recall` for representative queries
- verify repo-local docs are included without excessive noise
- verify adapters do not duplicate policy content

## Risks

- too much automatic recall can waste tokens or blur focus
- too little recall defeats the purpose of shared continuity
- agent-specific adapters may drift if shared logic leaks out of `nexus`
- local-doc recall can become noisy if ranking is not constrained
- deleting `claude-recall` too early could break trust in the migration

Mitigations:

- tiered recall policy
- thin adapters
- explicit migration validation
- preserve phase separation between baseline recall and future active memory

## Recommended Implementation Order

1. Create the `nexus` repo skeleton.
2. Import the `claude-recall` engine into `nexus/recall/`.
3. Add local-doc discovery and context assembly.
4. Add shared policies and reusable skills/prompts.
5. Add Claude and Codex adapters.
6. Validate on selected repos under `/home/daedalus/linux`.
7. Repoint references from Claude/Codex-facing files.
8. Remove the old `claude-recall` repo only after the replacement is proven.

