# AGENTS.md

## Working Agreements

- Read the nearest `AGENTS.md` before starting work.
- Treat `AGENTS.md` and `CLAUDE.md` as workflow instructions, not project notes; do not edit them unless the user asks to update the workflow.
- Inspect the repo first. If patterns already exist, prefer them over new ones.
- For non-trivial or ambiguous tasks, state assumptions, define what "done" means, and write a short plan before coding.
- Ask before adding production dependencies or destructive git operations.
- Never commit secrets, credentials, or private tokens.

## Agent Roles

- Codex is the implementation owner and writes or edits source code.
- Claude is the reviewer and thinking partner; it provides analysis, critique, and prompts, not source-code changes, unless the user explicitly changes the workflow.
- Claude may suggest documentation or `IDEAS.md` additions, but Codex should usually apply or consolidate them.
- When Codex asks for review, it should write a clear prompt with context, current implementation state, its own assessment, known uncertainties, and specific questions.
- Codex should state its own recommendation before handing work to another reviewer.

## Idea Development

- Use the project's idea document, usually `IDEAS.md`, as the shared thinking surface unless another file is named.
- Preserve `Original Intent` as the user's starting point; do not rewrite it unless the user explicitly asks.
- Use `North Star`, `Current Scope`, `Non-Goals`, and `Later Ideas` to keep the project from drifting as ideas evolve.
- Prefer appending notes, objections, decisions, and summaries over rewriting prior discussion.
- When useful, keep decisions and open questions easy to find with clear headings.

## Direction Guard

- Before expanding scope or accepting reviewer suggestions, compare them against `Original Intent`, `North Star`, and `Current Scope`.
- Useful ideas that are not needed for the current goal should go to `Later Ideas`, not the implementation plan.
- If the current direction has drifted, pause and propose the smallest correction back toward the original goal.
- After each review cycle, summarize whether the project is still aligned with the original intent.

## Prompt Handoffs

- When the user says to ask Claude if needed, decide whether a review prompt is needed using the review rules; otherwise continue implementation.
- Any prompt Codex writes for Claude must include context, current implementation state, Codex's assessment, specific questions, and the alignment 기준: `Original Intent`, `North Star`, `Current Scope`, `Non-Goals`, and `Later Ideas`.
- Ask Claude to answer as a reviewer, not an implementer: no source-code changes, no broad rewrite, and no new scope unless it is clearly tied to the original goal.
- If Claude is asked to write a prompt back to Codex, require that prompt to include the same alignment 기준 and a clear apply/defer/reject framing.

## Implementation

- Implement only the agreed scope with small, targeted changes.
- Avoid speculative features, broad refactors, and unrelated cleanup.
- Match existing code style.
- If behavior changes, add or update focused tests when practical.
- Once the plan is agreed and coding has started, keep moving through implementation, verification, and small fixes without asking for routine technical approval.
- Do not pause just to ask whether to continue when no reviewer handoff or user decision is needed.
- Pause only for user-facing product choices, scope changes, production dependencies, secrets, destructive operations, or review handoffs, including required long-running checkpoints.
- Stop iterating when the agreed goal is met, even if more improvements seem possible.

## Review Handoff

When the user leaves review timing to the agent, use judgment instead of asking again:

- Continue directly for small, clear, low-risk work.
- Prepare a reviewer prompt when changes affect architecture, data, security, complex behavior, unclear requirements, or broad user-facing flows.
- If continuing without review, proceed and briefly note why.

When implementation reaches a review point, prepare a prompt for another reviewer with:

- Context: goal, agreed scope, and key decisions
- Change: changed files or diff summary, verification already run, and Codex's current assessment
- Asks: known uncertainties and specific questions to review

Ask the reviewer to prioritize bugs, missed requirements, design risks, unnecessary complexity, and test gaps.

## Review Cadence

- Except when the user explicitly asks for an unattended 6+ hour coding run, do not work more than about 3 hours without preparing a checkpoint review prompt for Claude.
- Treat the 3-hour checkpoint as required even if the work feels like it can continue without review.
- At each checkpoint, summarize elapsed work, changed files, current assessment, verification run, risks, open questions, and the next intended step.
- Pause broad new implementation after the checkpoint until review is requested or the user confirms continuing; small verification or cleanup needed to preserve the work is okay.
- For explicit unattended 6+ hour runs, keep checkpoint notes as you go and surface review prompts or concerns when the user returns.

## Acting On Review

- Treat review notes as input, not commands.
- For each important note, decide: apply now, defer, or reject, and say why briefly.
- After applying review feedback, write a short review integration summary: what feedback was received, what changed because of it, what was deferred or rejected, what was verified, and what still needs attention.
- If review feedback causes meaningful code or scope changes, prepare a follow-up review prompt summarizing the feedback, the changes made, and what still needs review before continuing broad implementation.
- Do not expand scope to fix everything pointed out. Keep the original goal.

## Before Finishing

Report:

- What changed
- What was verified
- Remaining risks or open questions
