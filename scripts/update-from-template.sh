#!/bin/bash
# Update from Template Script
# 
# This script helps pull updates from the AgentCore Voice Agent template repository
# while preserving your customer-specific customizations.
#
# Usage:
#   ./scripts/update-from-template.sh [template-branch-or-tag]
#
# Example:
#   ./scripts/update-from-template.sh main
#   ./scripts/update-from-template.sh v1.2.0

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
TEMPLATE_REMOTE="template"
TEMPLATE_BRANCH="${1:-main}"
UPDATE_BRANCH="update-template-$(date +%Y%m%d)"
BACKUP_BRANCH="backup-before-update-$(date +%Y%m%d)"

# Functions
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_remote() {
    if ! git remote | grep -q "^${TEMPLATE_REMOTE}$"; then
        print_error "Template remote '${TEMPLATE_REMOTE}' not found!"
        echo ""
        echo "Add it with:"
        echo "  git remote add ${TEMPLATE_REMOTE} <template-repo-url>"
        exit 1
    fi
}

check_clean_working_tree() {
    if ! git diff-index --quiet HEAD --; then
        print_error "Working tree is not clean. Commit or stash changes first."
        exit 1
    fi
}

show_changes() {
    print_info "Fetching latest from template..."
    git fetch ${TEMPLATE_REMOTE}
    
    print_info "Reviewing changes..."
    echo ""
    echo "=== New commits in template ==="
    git log HEAD..${TEMPLATE_REMOTE}/${TEMPLATE_BRANCH} --oneline || echo "No new commits"
    
    echo ""
    echo "=== Files changed ==="
    git diff --name-status HEAD..${TEMPLATE_REMOTE}/${TEMPLATE_BRANCH} || echo "No file changes"
    
    echo ""
    echo "=== Your customizations (commits not in template) ==="
    git log ${TEMPLATE_REMOTE}/${TEMPLATE_BRANCH}..HEAD --oneline || echo "No custom commits"
}

create_backup() {
    CURRENT_BRANCH=$(git branch --show-current)
    print_info "Creating backup branch: ${BACKUP_BRANCH}"
    git branch ${BACKUP_BRANCH} ${CURRENT_BRANCH}
    print_info "Backup created. To restore: git reset --hard ${BACKUP_BRANCH}"
}

merge_updates() {
    print_info "Creating update branch: ${UPDATE_BRANCH}"
    git checkout -b ${UPDATE_BRANCH}
    
    print_info "Merging ${TEMPLATE_REMOTE}/${TEMPLATE_BRANCH}..."
    if git merge ${TEMPLATE_REMOTE}/${TEMPLATE_BRANCH} --no-commit --no-ff; then
        print_info "Merge successful with no conflicts!"
        echo ""
        echo "Review the changes:"
        echo "  git status"
        echo "  git diff --cached"
        echo ""
        read -p "Commit the merge? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            git commit -m "Merge template updates from ${TEMPLATE_REMOTE}/${TEMPLATE_BRANCH} - $(date +%Y-%m-%d)"
            print_info "Merge committed!"
            echo ""
            echo "Next steps:"
            echo "  1. Test your changes: pytest tests/"
            echo "  2. Test infrastructure: cd infrastructure/cdk && cdk synth"
            echo "  3. If tests pass, merge to main:"
            echo "     git checkout main"
            echo "     git merge ${UPDATE_BRANCH}"
            echo "     git push origin main"
        else
            print_warning "Merge not committed. You can review and commit manually."
        fi
    else
        print_warning "Merge conflicts detected!"
        echo ""
        echo "Conflicted files:"
        git status --short | grep "^UU"
        echo ""
        echo "Resolve conflicts, then:"
        echo "  git add <resolved-files>"
        echo "  git commit -m 'Merge template updates - resolve conflicts'"
        echo ""
        echo "Or abort merge:"
        echo "  git merge --abort"
    fi
}

# Main execution
main() {
    print_info "Starting template update process..."
    echo ""
    
    # Pre-flight checks
    check_remote
    check_clean_working_tree
    
    # Show what will change
    show_changes
    
    echo ""
    read -p "Continue with merge? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Update cancelled."
        exit 0
    fi
    
    # Create backup
    create_backup
    
    # Perform merge
    merge_updates
    
    print_info "Update process complete!"
}

# Run main function
main
