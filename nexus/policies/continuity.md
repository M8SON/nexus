# Continuity Policy

Memory is a tool you reach for, not a passive store. These rules govern when to recall and when to save.

## Recall

At session start, the SessionStart hook injects `mempalace wake-up --wing <wing>` for the active repo, plus local-doc snippets. You start every substantive session with that context in front of you. Read it before you act.

When the user references prior work, when you are about to make a design decision, when the task looks like a continuation, or when you find yourself stuck or repeating yourself: call `mempalace_search` scoped to the active wing first. Do this before re-reading files you have read this session, and before asking the user a question that prior context might already answer.

If a search returns nothing useful, broaden once: drop the wing scope or rephrase the query. Do not loop indefinitely.

## Save

The Save hook auto-mines transcripts and asks you to confirm topics, decisions, and direct quotes every 15 messages. Comply. The PreCompact hook fires the same path right before context compaction; comply there too without arguing about it being unnecessary.

Save durable facts: decisions made and their reasons, constraints the user cares about, user preferences expressed firmly, project state changes that outlast this session. Do not save ephemeral state: which files you just edited, what tests passed, the current cwd.

If you discover a fact mid-task that meets the durable bar — call the appropriate save tool yourself rather than waiting for the next hook fire.

## Wing scoping

Always pass the active repo's wing in `mempalace_search` and `mempalace_wake_up` calls unless you are explicitly broadening. Cross-wing search is for when the user names another project, or when you suspect prior context lives elsewhere.
