# Agent Instructions for LinearManager

## Duplicate Issue Detection

When working with LinearManager tasks, if you encounter duplicate issues or issues that seem like they might be duplicates:

**ALWAYS ask the user which issue should be kept.**

Do not automatically:
- Delete duplicates
- Merge duplicates
- Assume which one should be preserved

Instead:
1. Identify the potentially duplicate issues
2. Present them to the user with their key details (title, description, status, assignee)
3. Ask which should be kept and what should happen to the others (delete, merge, keep both, etc.)

This ensures important context or subtle differences aren't lost without user review.

## Syncing Best Practices

**IMPORTANT: Only sync specific subsets of files at any given time.**

When using `manager sync`, avoid syncing the entire tasks directory at once. Instead:

### ✅ Recommended Approach:
```bash
# Sync specific files or small groups
manager sync ~/LinearManager/tasks/specific_file.yaml
manager sync ~/LinearManager/tasks/archived/cancellations_*.yaml

# Sync a specific subdirectory
manager sync ~/LinearManager/tasks/archived/

# Sync recently modified files only
find ~/LinearManager/tasks -name "*.yaml" -mtime -1 -exec manager sync {} \;
```

### ❌ Avoid:
```bash
# Syncing all files at once can cause:
# - API rate limiting (400 errors)
# - Duplicate issue creation
# - Unintended updates to unrelated issues
manager sync ~/LinearManager/tasks  # Too broad!
```

### Why This Matters:
1. **Rate Limiting**: Linear API has rate limits. Bulk syncs can hit these limits and fail partway through
2. **Duplicate Prevention**: Mass syncs of similar tasks can create duplicate issues in Linear
3. **Controlled Updates**: Smaller, targeted syncs let you verify changes incrementally
4. **Error Recovery**: If something fails, it's easier to identify and retry specific files

### Best Practice Workflow:
1. Create/update task YAML files
2. Sync individual files or small groups with delays: `manager sync file1.yaml && sleep 2 && manager sync file2.yaml`
3. Verify the sync worked before proceeding to the next batch
4. Use `--dry-run` flag to preview changes before syncing: `manager sync --dry-run file.yaml`
