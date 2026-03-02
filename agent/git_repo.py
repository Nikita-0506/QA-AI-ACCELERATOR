"""Git repository operations using GitPython."""
import os
import shutil
import tempfile
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import git
from git import Repo
import stat
import time


class GitRepoAnalyzer:
    """Analyze Git repositories."""
    
    def __init__(self, repo_url: str, github_token: Optional[str] = None):
        """Initialize with repo URL and optional token."""
        self.repo_url = repo_url
        self.github_token = github_token
        self.temp_dir = None
        self.repo = None
        
    def __enter__(self):
        """Context manager entry."""
        self.clone()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup."""
        self.cleanup()
        
    def clone(self) -> Path:
        """Clone repository to temp directory."""
        self.temp_dir = tempfile.mkdtemp(prefix="qa_intel_")
        
        # Add token to URL if provided (for private repos)
        clone_url = self.repo_url
        if self.github_token and "github.com" in self.repo_url:
            clone_url = self.repo_url.replace(
                "https://", 
                f"https://{self.github_token}@"
            )
        
        print(f"Cloning {self.repo_url} to {self.temp_dir}...")
        self.repo = Repo.clone_from(clone_url, self.temp_dir)
        return Path(self.temp_dir)
    
    def cleanup(self):
        """Remove temp directory (Windows-compatible)."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                # Close the repo to release file handles
                if self.repo:
                    self.repo.close()
                
                # Windows-specific: handle read-only files
                def handle_remove_readonly(func, path, exc):
                    """Error handler for Windows readonly files."""
                    if not os.access(path, os.W_OK):
                        # Change the file to be writable and try again
                        os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)
                        func(path)
                    else:
                        raise
                
                # Try to remove with error handler
                shutil.rmtree(self.temp_dir, onerror=handle_remove_readonly)
                print(f"✓ Cleaned up temp directory: {self.temp_dir}")
                
            except Exception as e:
                # If cleanup fails, it's not critical - temp files will be cleaned eventually
                print(f"⚠️  Warning: Could not clean up temp directory: {e}")
                print(f"   (This is not critical - temp files at: {self.temp_dir})")
        
    def get_commits_between(
        self, 
        baseline_ref: str, 
        current_ref: str
    ) -> List[Dict[str, str]]:
        """Get commit list between two refs."""
        commits = []
        try:
            commit_range = f"{baseline_ref}..{current_ref}"
            for commit in self.repo.iter_commits(commit_range):
                commits.append({
                    "sha": commit.hexsha[:8],
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat(),
                    "message": commit.message.strip().split('\n')[0]
                })
        except Exception as e:
            print(f"Warning: Could not get commits: {e}")
        return commits
        
    def get_diff(
        self, 
        baseline_ref: str, 
        current_ref: str
    ) -> List[Tuple[str, str, int, int]]:
        """
        Get file diffs between refs.
        Returns: List of (file_path, diff_text, additions, deletions)
        """
        changes = []
        try:
            baseline_commit = self.repo.commit(baseline_ref)
            current_commit = self.repo.commit(current_ref)
            
            diff_index = baseline_commit.diff(current_commit)
            
            for diff_item in diff_index:
                file_path = diff_item.a_path or diff_item.b_path
                
                # Get diff text
                try:
                    diff_text = diff_item.diff.decode('utf-8') if diff_item.diff else ""
                except:
                    diff_text = ""
                
                # Count additions/deletions
                additions = diff_text.count('\n+') if diff_text else 0
                deletions = diff_text.count('\n-') if diff_text else 0
                
                changes.append((file_path, diff_text, additions, deletions))
                
        except Exception as e:
            print(f"Warning: Could not get diff: {e}")
            
        return changes
        
    def checkout(self, ref: str):
        """Checkout a specific ref."""
        self.repo.git.checkout(ref)
        
    def read_file(self, path: str) -> Optional[str]:
        """Read file content from current checkout."""
        file_path = Path(self.temp_dir) / path
        if file_path.exists():
            return file_path.read_text(encoding='utf-8', errors='ignore')
        return None
        
    def resolve_commit(self, ref: str) -> str:
        """Resolve ref to commit SHA."""
        try:
            commit = self.repo.commit(ref)
            return commit.hexsha[:8]
        except:
            return ref