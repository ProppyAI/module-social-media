---
name: fix-pr-reviews
description: Autonomous PR review fix loop — reads bot reviews, fixes real issues, pushes, loops until clean. Uses mempalace KG to learn noise patterns across sessions.
---

# Fix PR Reviews

Autonomous loop that fixes bot PR review findings until the PR is clean or the circuit breaker trips.

## Arguments

`$ARGUMENTS` is the PR number (required). Optional flags parsed from the argument string:
- `--repo <owner/repo>` — target repo (default: current repo)
- `--max-rounds <N>` — override circuit breaker (default: 6)

## Instructions

Parse the PR number and optional flags from: $ARGUMENTS

### Phase 0: Setup

1. Determine the repo: if `--repo` was provided, use it. Otherwise run `gh repo view --json nameWithOwner -q .nameWithOwner`.
2. Run `gh pr view $PR_NUMBER --json title,body,headRefName,baseRefName` to get PR context. The **title and body describe the original intent** of the PR. Every fix must preserve this intent. Save this for reference throughout the loop.
3. Checkout the PR branch: `git fetch origin <headRefName> && git checkout <headRefName> && git pull origin <headRefName>`
4. Note the current timestamp as `LOOP_START_TIME`.

### Phase 1: The Loop

For each round (1 to max_rounds, default 6):

**Step 1 — READ the latest review:**

```bash
# Get the most recent review
gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews --jq '.[-1]'

# Get review comments (inline comments on code)
gh api repos/{owner}/{repo}/pulls/{pr_number}/comments --jq 'sort_by(.created_at)'

# Get general PR comments (top-level discussion)
gh api repos/{owner}/{repo}/issues/{pr_number}/comments --jq 'sort_by(.created_at)'
```

For rounds 2+, only look at comments created AFTER the last push timestamp. If no new review comments exist after the last push, the PR is clean — exit the loop.

**Step 2 — RECALL from mempalace:**

Query mempalace for known patterns. Use the MCP tools if available, otherwise fall back to CLI:

```bash
# Search for noise patterns
mempalace search "review noise patterns" --wing harness

# If MCP tools are available, also query:
# mempalace_kg_query entity="bot-reviewer"
# mempalace_kg_query entity="review-noise"
```

Use the results to inform classification. If a finding matches a known noise pattern from the KG (e.g., "theoretical-injection-in-heredocs", "cosmetic-style-issues"), lean toward classifying it as NOISE — but still verify against the actual code.

**Step 3 — CLASSIFY each finding:**

For each review comment, classify as:

**REAL** (will fix):
- Breaks functionality or causes runtime errors
- Actual bugs — logic errors, off-by-one, null dereference
- Missing error handling that would cause crashes in production
- Type errors or interface mismatches
- Security issues that are actually exploitable in context
- Violations of the project's own CLAUDE.md standards

**NOISE** (will skip):
- Cosmetic style preferences not in CLAUDE.md
- Repeated bot fixations on the same pattern across rounds
- LOW/INFO severity findings (except security — see below)
- Suggestions that would add unnecessary complexity (YAGNI)
- Suggestions that would change the PR's original intent
- Findings that match known KG noise patterns (except security — see below)

**SECURITY findings require extra scrutiny.** Never auto-dismiss a security finding solely because it matches a KG noise pattern. For each security finding, verify independently that the mitigation the KG claims exists actually exists in the current code. Only skip security findings when you can point to the specific line that mitigates the issue. When writing security skips to the KG, tag them as `security_skip` so they don't self-reinforce into permanent blindness.

Print the classification clearly:
```
=== Round N Classification ===
REAL (fixing):
  - [file:line] description
  - [file:line] description
NOISE (skipping):
  - [file:line] description — reason: [why this is noise]
```

**Step 4 — CIRCUIT BREAKER CHECK:**

Apply these rules in order:
1. If no REAL findings exist → exit loop, recommend merge
2. If round > 3 AND only MEDIUM/LOW/theoretical findings remain → exit loop, recommend merge
3. If round >= max_rounds → hard stop, print what's left, let user decide
4. Otherwise → continue to fix

**Step 5 — FIX real findings:**

Use the `receiving-code-review` skill pattern:
- Fix each REAL finding
- After fixing, verify: run any available tests, lint, type-check for the project
- Do NOT fix NOISE findings — do not touch them
- Do NOT introduce changes beyond what the finding requires
- Do NOT add docstrings, comments, or refactoring beyond the fix
- After every fix, compare against the PR title/body from Phase 0 — if a fix would drift from the original intent, flag it and skip

**Step 6 — PUSH:**

```bash
PUSH_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
git add <specific files that were changed>
git commit -m "fix: address round-$N review — $(brief comma-separated list of fixes)"
git push origin HEAD
```

Note `PUSH_TIME` was captured **before** the push to avoid missing fast bot reviews.

**Step 7 — RECORD to mempalace:**

Write to the knowledge graph after each round. Use MCP tools if available, otherwise note for manual entry:

For each REAL finding that was fixed:
```
KG add: subject="PR-{number}" predicate="round_{N}_fixed" object="{brief description}" valid_from="{today}"
```

For each NOISE finding that was skipped:
```
KG add: subject="PR-{number}" predicate="round_{N}_skipped" object="{brief description}: {reason}" valid_from="{today}"
```

**Step 8 — POLL for new review:**

Wait for the bot to re-review after push:

```bash
# Poll every 30 seconds for up to 10 minutes
# Use the PUSH_TIME captured before git push in Step 6
TIMED_OUT=1
for i in $(seq 1 20); do
  sleep 30
  NEW_REVIEWS=$(gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews \
    --jq "[.[] | select(.submitted_at > \"$PUSH_TIME\")] | length")
  NEW_COMMENTS=$(gh api repos/{owner}/{repo}/pulls/{pr_number}/comments \
    --jq "[.[] | select(.created_at > \"$PUSH_TIME\")] | length")
  NEW_ISSUE_COMMENTS=$(gh api repos/{owner}/{repo}/issues/{pr_number}/comments \
    --jq "[.[] | select(.created_at > \"$PUSH_TIME\")] | length")
  TOTAL=$((NEW_REVIEWS + NEW_COMMENTS + NEW_ISSUE_COMMENTS))
  if [ "$TOTAL" -gt "0" ]; then
    echo "New review activity detected after $((i * 30)) seconds ($NEW_REVIEWS reviews, $NEW_COMMENTS inline, $NEW_ISSUE_COMMENTS top-level)"
    TIMED_OUT=0
    break
  fi
  echo "Waiting for review... ($((i * 30))s)"
done
if [ "$TIMED_OUT" -eq 1 ]; then
  echo "Bot did not re-review within 10 minutes — stopping"
  # Exit the outer round loop
fi
```

- If new review appears → continue to next round
- If 10 minute timeout → exit loop, report "bot did not re-review within 10 minutes"

### Phase 2: Post-Loop

After exiting the loop (for any reason):

1. **Record final outcome to KG:**
```
KG add: subject="PR-{number}" predicate="resolved_in" object="{N} rounds" valid_from="{today}"
KG add: subject="PR-{number}" predicate="outcome" object="{clean|circuit_breaker|timeout|needs_human}" valid_from="{today}"
```

2. **File a mempalace drawer with the full narrative:**

Use `mempalace_add_drawer` MCP tool if available, otherwise fall back to CLI. File a drawer in the `harness` wing / `general` room containing:
- PR number and title
- Number of rounds
- For each round: what was fixed, what was skipped and why
- Final outcome and recommendation
- Any patterns worth remembering for future runs

This narrative is the long-term memory — KG triples capture facts, the drawer captures context.

3. **Write a reviewer diary entry:**

Use `mempalace_diary_write` MCP tool if available, otherwise fall back to Python:
```
diary_write agent="reviewer" entry="PR-{number}:{title}|{N}rounds|fixed:{fixed_count}|skipped:{skipped_count}|outcome:{outcome}" topic="pr-review"
```

This builds the reviewer agent's long-term memory of review patterns — richer than KG triples, queryable by future sessions.

4. **Print summary:**
```
====================================
PR #{number}: {title}
====================================
Outcome: {clean / circuit breaker at round N / timeout / needs human}
Rounds:  {N}
Fixed:   {count} findings
Skipped: {count} findings (noise)

Recommendation: {MERGE — all real issues resolved / REVIEW — remaining findings listed below / WAIT — bot did not re-review}

{If remaining findings exist, list them here}
====================================
```

## Key Rules

1. **Intent preservation is sacred.** The PR exists for a reason. Every fix must serve that reason, not the reviewer's tangential suggestions.
2. **NOISE stays unfixed.** Do not touch it. Do not acknowledge it. The KG remembers it so future runs skip it faster.
3. **Convergence over completeness.** A PR with only cosmetic findings is ready to merge. Don't let perfect be the enemy of shipped.
4. **Record everything.** Every fix, every skip, every reason. The KG is how this system gets smarter.
