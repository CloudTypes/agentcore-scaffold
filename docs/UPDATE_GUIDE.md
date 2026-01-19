# Template Update Guide

This guide explains how to pull updates from the AgentCore Voice Agent template repository into your customer-specific implementation while preserving your customizations.

## Overview

If you created your repository from the AgentCore Voice Agent template, you can pull in upstream updates to get:
- New features and improvements
- Bug fixes
- Infrastructure updates
- Security patches

This guide shows you how to merge template updates while keeping your customer-specific customizations intact.

## Prerequisites

- Git installed and configured
- Access to the template repository
- Understanding of your customizations (what you've changed)

## Initial Setup

### 1. Add Template as Remote

Add the template repository as a remote named `template`:

```bash
# From your customer repository root
git remote add template https://github.com/your-org/agentcore-scaffold.git

# Verify it was added
git remote -v
```

You should see:
```
origin    https://github.com/customer-org/customer-voice-agent.git (fetch)
origin    https://github.com/customer-org/customer-voice-agent.git (push)
template  https://github.com/your-org/agentcore-scaffold.git (fetch)
template  https://github.com/your-org/agentcore-scaffold.git (push)
```

### 2. Fetch Template Updates

Fetch the latest changes from the template:

```bash
git fetch template
```

This downloads all branches and tags from the template without modifying your local branches.

## Reviewing Updates

### 1. See What's New in Template

Compare your current branch with the template's main branch:

```bash
# See commits in template that you don't have
git log HEAD..template/main --oneline

# See detailed changes
git log HEAD..template/main

# See what files changed
git diff --name-status HEAD..template/main
```

### 2. See Your Customizations

Compare your changes with the template:

```bash
# See commits you have that template doesn't
git log template/main..HEAD --oneline

# See files you've modified
git diff --name-status template/main..HEAD
```

### 3. Identify Potential Conflicts

Check which files might conflict:

```bash
# Files that exist in both but differ
git diff --name-only template/main...HEAD

# More detailed conflict preview
git merge-tree $(git merge-base HEAD template/main) HEAD template/main
```

## Merging Updates

### Strategy 1: Merge (Recommended for Most Cases)

Merge template updates into your branch:

```bash
# Ensure you're on your main branch
git checkout main

# Create a backup branch (safety first!)
git branch backup-before-merge-$(date +%Y%m%d)

# Merge template updates
git merge template/main --no-commit --no-ff

# Review the merge
git status
git diff --cached

# If everything looks good, commit
git commit -m "Merge template updates from template/main"
```

### Strategy 2: Rebase (For Linear History)

Rebase your changes on top of template updates:

```bash
# Create backup
git branch backup-before-rebase-$(date +%Y%m%d)

# Rebase onto template
git rebase template/main

# If conflicts occur, resolve them and continue
git add <resolved-files>
git rebase --continue
```

**Warning**: Only use rebase if you haven't pushed your branch yet, or if you're the only one working on it.

### Strategy 3: Cherry-Pick (Selective Updates)

Pull in only specific commits from the template:

```bash
# See commits you want
git log template/main --oneline

# Cherry-pick specific commits
git cherry-pick <commit-hash>

# Or cherry-pick a range
git cherry-pick <start-commit>^..<end-commit>
```

## Resolving Conflicts

When merging, you may encounter conflicts. Here's how to handle them:

### 1. Identify Conflicted Files

```bash
git status
```

Files listed under "Unmerged paths" have conflicts.

### 2. Understand Conflict Markers

Conflicted files contain markers:

```python
<<<<<<< HEAD
# Your customer-specific code
customer_custom_function()
=======
# Template code
template_function()
>>>>>>> template/main
```

### 3. Resolve Conflicts

For each conflicted file:

**Option A: Keep Your Customization**
```python
# Delete template code, keep yours
customer_custom_function()
```

**Option B: Use Template Code**
```python
# Delete your code, use template
template_function()
```

**Option C: Merge Both**
```python
# Combine both approaches
customer_custom_function()
template_function()  # Also include template version
```

**Option D: Create Hybrid**
```python
# Best of both worlds
if customer_specific_condition:
    customer_custom_function()
else:
    template_function()
```

### 4. Mark as Resolved

After editing conflicted files:

```bash
git add <resolved-file>
git commit -m "Resolve merge conflicts with template updates"
```

## Common Conflict Areas

### Infrastructure Files

**File**: `infrastructure/cdk/app.py`, `infrastructure/cdk/*_stack.py`

**Strategy**: 
- Keep your customer-specific stack configurations
- Merge new stack additions from template
- Update base stack references if needed

**Example**:
```python
# Your customization
customer_stack = CustomerStack(
    app, "CustomerStack",
    customer_specific_config=True
)

# Template addition (merge this in)
codebuild_stack = CodeBuildStack(...)
```

### Environment Variables

**File**: `env.example`

**Strategy**:
- Keep your customer-specific variables
- Add new template variables
- Document which are customer-specific

### Agent Implementations

**File**: `agents/*/agent.py`, `agents/*/app.py`

**Strategy**:
- If you've customized agent logic, keep your version
- If template adds new features, merge them in
- Consider creating customer-specific agent variants

### Buildspecs

**File**: `buildspecs/buildspec-*.yml`

**Strategy**:
- Keep customer-specific build steps
- Merge template build improvements
- Update ECR repository names if customized

## Best Practices

### 1. Document Your Customizations

Create a `CUSTOMIZATIONS.md` file:

```markdown
# Customer Customizations

## Modified Files
- `agents/orchestrator/agent.py` - Added customer-specific routing
- `infrastructure/cdk/customer_stack.py` - Customer-specific infrastructure
- `env.example` - Customer-specific environment variables

## Added Files
- `customer/` - Customer-specific code
- `agents/custom/` - Custom agents

## Configuration Changes
- ECR repository names: `customer-voice-agent-*`
- SSM parameter paths: `/customer/voice-agent/*`
```

### 2. Use Feature Branches for Updates

```bash
# Create branch for template update
git checkout -b update-from-template-$(date +%Y%m%d)

# Merge template
git merge template/main

# Resolve conflicts
# Test thoroughly

# Merge back to main
git checkout main
git merge update-from-template-*
```

### 3. Test After Merging

```bash
# Run tests
pytest tests/

# Test infrastructure
cd infrastructure/cdk
cdk synth

# Test builds locally
docker build -t test-agent -f agents/orchestrator/Dockerfile .
```

### 4. Version Your Updates

Tag your repository after successful template updates:

```bash
git tag -a v1.2.0-template-update -m "Updated from template v1.2.0"
git push origin v1.2.0-template-update
```

## Update Workflow Example

Complete workflow for pulling template updates:

```bash
# 1. Ensure you're on main and up to date
git checkout main
git pull origin main

# 2. Fetch latest template
git fetch template

# 3. Review what's new
git log HEAD..template/main --oneline
git diff --stat HEAD..template/main

# 4. Create update branch
git checkout -b update-template-$(date +%Y%m%d)

# 5. Merge template
git merge template/main --no-commit

# 6. Review changes
git status
git diff --cached

# 7. Resolve any conflicts
# (Edit conflicted files, then:)
git add <resolved-files>

# 8. Commit merge
git commit -m "Merge template updates - $(date +%Y-%m-%d)"

# 9. Test thoroughly
pytest tests/
cd infrastructure/cdk && cdk synth

# 10. If tests pass, merge to main
git checkout main
git merge update-template-*

# 11. Push updates
git push origin main

# 12. Clean up
git branch -d update-template-*
```

## Handling Breaking Changes

If the template introduces breaking changes:

### 1. Check Release Notes

Look for `CHANGELOG.md` or release notes in the template repository.

### 2. Review Migration Guides

Template may include migration guides for major updates.

### 3. Update Incrementally

```bash
# Update to intermediate version first
git fetch template
git checkout template/v1.1.0  # Previous stable version
git checkout -b update-to-v1.1.0
git checkout main
git merge update-to-v1.1.0

# Then update to latest
git merge template/main
```

### 4. Test Migration

```bash
# Test in dev environment first
cdk deploy --all --context environment=dev

# Verify everything works
# Then deploy to production
```

## Selective Updates

If you only want specific features:

### Update Specific Files

```bash
# Checkout specific file from template
git checkout template/main -- path/to/file

# Review changes
git diff HEAD path/to/file

# Commit if acceptable
git commit -m "Update file from template"
```

### Update Specific Directories

```bash
# Update infrastructure only
git checkout template/main -- infrastructure/

# Update buildspecs only
git checkout template/main -- buildspecs/

# Review and commit
git commit -m "Update infrastructure from template"
```

## Troubleshooting

### Merge Conflicts Too Complex

If conflicts are overwhelming:

```bash
# Abort merge
git merge --abort

# Use merge tool
git mergetool

# Or manually resolve with three-way merge
git show :1:file.py > file.common.py
git show :2:file.py > file.ours.py
git show :3:file.py > file.theirs.py
# Compare and merge manually
```

### Lost Customizations

If you accidentally overwrote customizations:

```bash
# Find when you lost it
git log --all --full-history -- path/to/file

# Restore from backup branch
git checkout backup-before-merge-*/ -- path/to/file

# Or restore from reflog
git reflog
git checkout <commit-hash> -- path/to/file
```

### Template Has Diverged Too Much

If template has changed significantly:

```bash
# Create fresh branch from template
git checkout -b fresh-from-template template/main

# Cherry-pick your customizations
git cherry-pick <your-commit-hash>

# Or manually port your changes
```

## Automation Script

Create a script to automate updates:

```bash
#!/bin/bash
# scripts/update-from-template.sh

set -e

echo "Fetching template updates..."
git fetch template

echo "Reviewing changes..."
echo "=== New commits in template ==="
git log HEAD..template/main --oneline

echo ""
echo "=== Files changed ==="
git diff --name-status HEAD..template/main

read -p "Continue with merge? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

BRANCH="update-template-$(date +%Y%m%d)"
git checkout -b $BRANCH

echo "Merging template..."
git merge template/main --no-commit

echo "Review status:"
git status

read -p "Resolve conflicts, then press Enter to continue..."

git commit -m "Merge template updates - $(date +%Y-%m-%d)"

echo "Update complete! Test and merge to main when ready."
```

Save as `scripts/update-from-template.sh` and make executable:
```bash
chmod +x scripts/update-from-template.sh
```

## Version-Based Updates

If template uses version tags:

```bash
# List available template versions
git fetch template --tags
git tag -l

# Update to specific version
git merge template/v1.2.0

# Or checkout specific version to review
git checkout template/v1.2.0
git checkout -b review-v1.2.0
```

## Maintaining Customizations

### Keep Custom Code Separate

Structure your code to minimize conflicts:

```
customer-voice-agent/
├── core/              # Link/symlink to template core
├── agents/
│   ├── shared/        # From template
│   └── custom/        # Your custom agents
├── infrastructure/
│   ├── cdk/
│   │   ├── base/      # From template
│   │   └── customer/  # Your custom stacks
└── customer/          # All customer-specific code
```

### Use Configuration Overrides

Instead of modifying template files, use overrides:

```python
# customer/config_overrides.py
CUSTOM_AGENT_CONFIG = {
    "model": "customer-specific-model",
    "custom_prompt": "..."
}

# agents/orchestrator/agent.py
from customer.config_overrides import CUSTOM_AGENT_CONFIG
# Use CUSTOM_AGENT_CONFIG instead of hardcoding
```

## Getting Help

If you encounter issues:

1. **Check Template Issues**: Look for similar issues in template repository
2. **Review Documentation**: Check template's docs for update notes
3. **Create Backup**: Always create backup branches before major updates
4. **Test Incrementally**: Update and test in small increments

## Summary

1. **Setup**: Add template as remote
2. **Review**: Check what's new before merging
3. **Merge**: Use merge strategy that fits your workflow
4. **Resolve**: Handle conflicts by keeping customizations
5. **Test**: Verify everything works after update
6. **Document**: Keep track of your customizations

Remember: When in doubt, create a backup branch and test thoroughly before merging to main!
