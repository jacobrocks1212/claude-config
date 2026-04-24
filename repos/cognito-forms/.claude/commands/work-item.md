# Implement Work Item

## Usage
`/work-item <WORK_ITEM_ID> <ADDITIONAL_CONTEXT>`

You are a senior software engineer focused on building correct, concise, and easily understood implementations for work items.

1. Use Azure DevOps MCP to fetch work item details by <WORK_ITEM_ID>
2. Run the create-branch-worktree.ps1 script to create a worktree and branch for development
   - Use branch name format: `<X>/some-relevant-name`, where <X> is the first letter of the work item's AreaPath lower-cased
     - Example: `Cognito Forms\Architecture` would use "a/"
   - Make sure you are in the new worktree directory for all subsequent steps
3. Perform any necessary research IN THE WORKTREE DIRECTORY to understand the work item and what changes to make
   - Take heed of any <ADDITIONAL_CONTEXT>
4. Create a plan for the work and write it to a markdown file: work-plan.md
   - Include a robot emoji in the header
5. Add a comment to the work item containing the plan using MCP
6. MAKE SURE YOU ARE IN THE NEW WORKTREE DIRECTORY WHEN DOING ANYTHING
7. Implement changes according to plan IN THE WORKTREE DIRECTORY.
   - Avoid trying to build or run tests
8. Commit changes and push IN THE WORKTREE DIRECTORY (do not commit work-plan.md)
   - Example commit messages:
      - fix light error messages on forms with dark backgrounds
      - track destination form ID when copying forms
9. Create a pull request into `main` using Azure DevOps MCP using this description template:
	```
**Background:**
\<Describe the problem or functionality being implemented\>

**Solution:**
\<Describe the changes made to solve the problem as well as potential impact\>
	```
	- make sure to use `markdown` format on the request
10. Add `claude` tag to work item

## Example Flow

```bash
# From any worktree (e.g., D:\cognito-wt\main)
powershell -Command "& ./.claude/scripts/create-branch-worktree.ps1 a/my-branch"
# Creates: D:\cognito-wt\scratch\a\my-branch
# Start working
```
