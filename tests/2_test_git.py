"""Test 2: Test Git repository cloning and access."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from agent.git_repo import GitRepoAnalyzer

load_dotenv()

def test_git_access():
    print("=" * 60)
    print("TEST 2: Git Repository Access")
    print("=" * 60)
    
    # Configuration
    repo_url = "https://github.com/Inadev-Data-Lab/QA_Playwright_Repo"
    github_token = os.getenv("GITHUB_TOKEN")
    
    print(f"\n📦 Repository: {repo_url}")
    print(f"🔑 Token: {'✅ Provided' if github_token else '❌ Not provided (may fail for private repos)'}")
    
    try:
        print("\n🔄 Step 1: Initializing Git Analyzer...")
        with GitRepoAnalyzer(repo_url, github_token) as git:
            print("✓ Git Analyzer initialized")
            
            print("\n🔄 Step 2: Cloning repository...")
            print(f"  → Cloning to: {git.temp_dir}")
            print("✓ Repository cloned successfully")
            
            print("\n🔄 Step 3: Resolving commits...")
            baseline_ref = "HEAD~5"
            current_ref = "HEAD"
            
            baseline_sha = git.resolve_commit(baseline_ref)
            current_sha = git.resolve_commit(current_ref)
            
            print(f"  → Baseline ({baseline_ref}): {baseline_sha}")
            print(f"  → Current ({current_ref}): {current_sha}")
            print("✓ Commits resolved")
            
            print("\n🔄 Step 4: Getting commit list...")
            commits = git.get_commits_between(baseline_ref, current_ref)
            print(f"  → Found {len(commits)} commits")
            for i, commit in enumerate(commits[:3], 1):
                print(f"    {i}. {commit['sha']} - {commit['message']}")
            if len(commits) > 3:
                print(f"    ... and {len(commits) - 3} more")
            print("✓ Commit list retrieved")
            
            print("\n🔄 Step 5: Getting file changes...")
            changes = git.get_diff(baseline_ref, current_ref)
            print(f"  → Found {len(changes)} file changes")
            for i, (path, diff, additions, deletions) in enumerate(changes[:3], 1):
                print(f"    {i}. {path} (+{additions}/-{deletions})")
            if len(changes) > 3:
                print(f"    ... and {len(changes) - 3} more files")
            print("✓ File changes retrieved")
        
        print("\n" + "=" * 60)
        print("✅ TEST PASSED: Git repository access working")
        print("   You can proceed to Test 3")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        print("\n🔧 Troubleshooting:")
        print("  1. Check if repository URL is correct")
        print("  2. If private repo, ensure GITHUB_TOKEN is set")
        print("  3. Check your internet connection")
        print("=" * 60)
        return False

if __name__ == "__main__":
    test_git_access()