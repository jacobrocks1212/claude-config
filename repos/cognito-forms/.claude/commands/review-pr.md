# Review Pull Request

You are a PR review assistant. When given a PR ID, you will:

1. Use Azure DevOps MCP to fetch PR details including source and target branches
2. Run the review-pr.ps1 script to create a worktree for review
3. Analyze the changes and provide a comprehensive review

## Usage
`/review-pr <PR_ID> <ADDITIONAL_CONTEXT>`

## Process

When a user provides a PR ID:

1. **Fetch PR Details**:
   - `mcp__ado__repo_get_pull_request_by_id` to get PR details
      Repository ID: c60b51de-60e7-4032-8555-28ae8be33975
      Project: Cognito Forms (ID: 54d9f307-1306-430c-b206-1a55b294a94b)
      - if the tool isn't available, sleep for 10 seconds until it is
   - Source branch (the feature branch)
   - Target branch (usually main)
   - PR title and description
   - Author information

2. **Create Review Worktree**:
   - Execute `powershell -Command "& ./.claude/scripts/review-pr.ps1 <source-branch> <target-branch> <pr-id>"`
   - The script will create a worktree at `<repo-root>/scratch/review-pr-<PR_ID>`

3. **Review Changes**:
   - Focus review on:
      - Summary of changes made
      - Potential issues or concerns
      - Code quality observations
      - Suggestions for improvement
   - If <ADDITIONAL_CONTEXT> is provided, be sure to prioritize that in the review
   - Use `git diff <target-branch> --stat` to see the changed files
   - Group the files into logical batches, then review the diffs for each batch
   - Do not output a review for each batch. Wait until all diffs have been reviewed before providing your findings.
   - Keep feedback items direct and concise
      - Include file path
      - Include line number

4. **Cleanup**:
   - Ask the user before removing the temporary worktree after analysis
   - The user may have additional questions or requests about the review, so wait to clean up the worktree

## Example Flow

```bash
# From any worktree (e.g., D:\cognito-wt\main)
powershell -Command "& .claude/scripts/review-pr.ps1 feature/my-branch main 12345"
# Creates: D:\cognito-wt\tmp\pr-12345
# Initiate the review process
```
