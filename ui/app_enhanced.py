"""Enhanced Streamlit UI with detailed analysis display."""
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import os
from pathlib import Path
import sys
import json
from io import StringIO
from datetime import datetime
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.git_repo import GitRepoAnalyzer
from agent.parsers import CucumberJsonParser
from agent.report_builder_enhanced import EnhancedReportBuilder
from agent.analyzers.compare_runs import RunComparator
from agent.analyzers.llm_analyzer import LLMAnalyzer
from dotenv import load_dotenv

load_dotenv()

# ── Authentication ──────────────────────────────────────────
config_path = Path(__file__).parent.parent / "config.yaml"
with open(config_path, "r", encoding="utf-8") as f:
    auth_config = yaml.load(f, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    auth_config["credentials"],
    auth_config["cookie"]["name"],
    auth_config["cookie"]["key"],
    auth_config["cookie"]["expiry_days"],
)

st.set_page_config(
    page_title="Testing Engine - QA Intelligence",
    page_icon="🧪",
    layout="wide"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .metric-card {
        background-color: #1e1e1e;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 20px;
        text-align: center;
    }
    .metric-value {
        font-size: 48px;
        font-weight: bold;
        color: #fff;
    }
    .metric-label {
        font-size: 14px;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .status-badge {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: bold;
    }
    .status-ready {
        background-color: #1a472a;
        color: #4ade80;
    }
    .timeout-badge {
        background-color: #854d0e;
        color: #fbbf24;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: bold;
        margin-left: 8px;
    }
    .timeout-alert {
        background-color: #451a03;
        border-left: 4px solid #f59e0b;
        padding: 12px;
        margin: 10px 0;
        border-radius: 4px;
    }
    .summary-box {
        background-color: #1a1a2e;
        border-left: 4px solid #3b82f6;
        padding: 12px;
        margin: 10px 0;
        border-radius: 4px;
    }
    .summary-text {
        font-weight: 600;
        color: #3b82f6;
        margin-bottom: 8px;
    }
    .report-frame {
        width: 100%;
        height: 600px;
        border: 1px solid #333;
        border-radius: 8px;
        background: white;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to detect timeout issues
def detect_timeout_issue(error_message, explanation=""):
    """Detect if the failure is related to timeout/session timeout."""
    if not error_message and not explanation:
        return False
    
    combined_text = f"{error_message} {explanation}".lower()
    
    timeout_keywords = [
        'timeout',
        'timed out',
        'session timeout',
        'session expired',
        'connection timeout',
        'read timeout',
        'element not found within',
        'waiting for element',
        'expected condition failed',
        'not completing within',
        'exceeded timeout',
        'wait timeout'
    ]
    
    return any(keyword in combined_text for keyword in timeout_keywords)

# Initialize session state
if 'analysis_timestamp' not in st.session_state:
    st.session_state.analysis_timestamp = None
if 'dataset_name' not in st.session_state:
    st.session_state.dataset_name = None
if 'metrics' not in st.session_state:
    st.session_state.metrics = None
if 'commits_cache' not in st.session_state:
    st.session_state.commits_cache = {}
if 'total_commits' not in st.session_state:
    st.session_state.total_commits = None
if 'repo_branches' not in st.session_state:
    st.session_state.repo_branches = []
if 'selected_branch' not in st.session_state:
    st.session_state.selected_branch = None
if 'branch_commit_counts' not in st.session_state:
    st.session_state.branch_commit_counts = {}
if 's3_report_folders' not in st.session_state:
    st.session_state.s3_report_folders = []

# Fixed LLM settings (hidden from UI)
MAX_TOKENS = 5000
MAX_WORKERS = 10
MAX_DETAILED_ANALYSIS = 20
TEMPERATURE = 0.10

# S3 configuration from environment
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "qa-accelerator-inadev")
S3_REPORTS_PREFIX = os.getenv("S3_REPORTS_PREFIX", "all_reports/")

# Local reports directory (fallback when S3 is not configured)
LOCAL_REPORTS_DIR = Path(__file__).parent.parent / "html-reports"


# ── Local Reports Helper ─────────────────────────────────────

def load_local_reports():
    """Load JSON report files from the local html-reports directory."""
    result = {"json_reports": [], "html_reports": []}
    if not LOCAL_REPORTS_DIR.exists():
        return result
    for f in sorted(LOCAL_REPORTS_DIR.iterdir()):
        if f.suffix.lower() == ".json":
            try:
                result["json_reports"].append((f.name, f.read_text(encoding="utf-8")))
            except Exception:
                pass
        elif f.suffix.lower() in (".html", ".htm"):
            try:
                result["html_reports"].append((f.name, f.read_bytes()))
            except Exception:
                pass
    return result


# ── S3 Helper Functions ─────────────────────────────────────

def get_s3_client():
    """Get a boto3 S3 client. Uses IAM role on EC2 or local AWS credentials."""
    try:
        return boto3.client("s3")
    except NoCredentialsError:
        return None  # S3 not configured — silently fall back to local reports


def list_s3_report_folders():
    """List all report folders under the S3 prefix (e.g. all_reports/)."""
    cache_key = f"s3_folders|{S3_BUCKET_NAME}|{S3_REPORTS_PREFIX}"
    if cache_key in st.session_state.commits_cache:
        return st.session_state.commits_cache[cache_key]

    s3 = get_s3_client()
    if not s3:
        return []

    try:
        # List "subdirectories" under the prefix
        paginator = s3.get_paginator("list_objects_v2")
        folders = []
        for page in paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=S3_REPORTS_PREFIX, Delimiter="/"):
            for prefix_obj in page.get("CommonPrefixes", []):
                folder_path = prefix_obj["Prefix"]
                # Extract just the folder name (e.g. "demo_reports_folder_1")
                folder_name = folder_path[len(S3_REPORTS_PREFIX):].rstrip("/")
                if folder_name:
                    folders.append(folder_name)

        st.session_state.commits_cache[cache_key] = folders
        return folders
    except NoCredentialsError:
        return []  # S3 not configured — silently fall back to local reports
    except (ClientError, Exception) as e:
        st.warning(f"Could not list S3 folders: {e}")
        return []


def download_s3_reports(folder_name):
    """Download all files from a specific S3 report folder.

    Returns a dict with keys:
        'json_reports': list of (filename, content_str) for .json files
        'html_reports': list of (filename, content_bytes) for .html files
    """
    cache_key = f"s3_report|{S3_BUCKET_NAME}|{S3_REPORTS_PREFIX}{folder_name}"
    if cache_key in st.session_state.commits_cache:
        return st.session_state.commits_cache[cache_key]

    s3 = get_s3_client()
    if not s3:
        return {"json_reports": [], "html_reports": []}

    prefix = f"{S3_REPORTS_PREFIX}{folder_name}/"
    result = {"json_reports": [], "html_reports": []}

    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                filename = key.split("/")[-1]
                if not filename:
                    continue

                response = s3.get_object(Bucket=S3_BUCKET_NAME, Key=key)
                body = response["Body"].read()

                if filename.lower().endswith(".json"):
                    result["json_reports"].append((filename, body.decode("utf-8")))
                elif filename.lower().endswith(".html") or filename.lower().endswith(".htm"):
                    # Pull HTML for future use but don't display
                    result["html_reports"].append((filename, body))

        st.session_state.commits_cache[cache_key] = result
        return result
    except NoCredentialsError:
        return {"json_reports": [], "html_reports": []}  # S3 not configured
    except (ClientError, Exception) as e:
        st.warning(f"Could not download reports from S3: {e}")
        return {"json_reports": [], "html_reports": []}

# Helper function to load reports from dataset - IMPROVED
def load_reports_from_dataset(dataset_path=None):
    """Load baseline and current reports from multiple possible locations"""
    
    # Priority 1: Check project root html-reports folder
    base_dir = Path(__file__).parent.parent
    reports_dir = base_dir / "html-reports"
    
    if reports_dir.exists():
        report_files = sorted(list(reports_dir.glob("*.json")))
        if len(report_files) >= 2:
            with open(report_files[0], 'r', encoding='utf-8') as f:
                baseline_content = f.read()
            with open(report_files[1], 'r', encoding='utf-8') as f:
                current_content = f.read()
            return baseline_content, current_content
    
    # Priority 2: Check if dataset_path provided, look in dataset folder
    if dataset_path:
        dataset_reports = Path(dataset_path) / "reports"
        if dataset_reports.exists():
            report_files = sorted(list(dataset_reports.glob("*.json")))
            if len(report_files) >= 2:
                with open(report_files[0], 'r', encoding='utf-8') as f:
                    baseline_content = f.read()
                with open(report_files[1], 'r', encoding='utf-8') as f:
                    current_content = f.read()
                return baseline_content, current_content
    
    # No reports found
    return None, None

# Helper function to fetch all branches from the repo
def get_repo_branches(repo_url, github_token=None):
    """Fetch all branch names and their commit counts from the repository."""
    cache_key = f"branches|{repo_url}"

    # Check cache
    if cache_key in st.session_state.commits_cache:
        return st.session_state.commits_cache[cache_key]

    try:
        with GitRepoAnalyzer(repo_url, github_token) as git:
            branches = []
            commit_counts = {}
            seen = set()

            # Use remote().refs to get only remote tracking branches
            try:
                for ref in git.repo.remote().refs:
                    branch_name = ref.remote_head
                    if branch_name == 'HEAD' or branch_name in seen:
                        continue
                    seen.add(branch_name)
                    count = sum(1 for _ in git.repo.iter_commits(ref))
                    branches.append(branch_name)
                    commit_counts[branch_name] = count
            except (ValueError, Exception):
                pass

            # Fallback: if no remote refs found, use local branches
            if not branches:
                for head in git.repo.heads:
                    branch_name = head.name
                    if branch_name in seen:
                        continue
                    seen.add(branch_name)
                    count = sum(1 for _ in git.repo.iter_commits(head))
                    branches.append(branch_name)
                    commit_counts[branch_name] = count

            result = {"branches": branches, "commit_counts": commit_counts}
            st.session_state.commits_cache[cache_key] = result
            return result
    except Exception as e:
        st.warning(f"Could not fetch branches: {e}")
        return {"branches": ["main"], "commit_counts": {"main": 100}}


# Helper function to get total commits from repo
def get_total_commits(repo_url, github_token=None, branch='HEAD'):
    """Get total number of commits on a specific branch."""
    cache_key = f"total_commits|{repo_url}|{branch}"
    
    # Check cache
    if cache_key in st.session_state.commits_cache:
        return st.session_state.commits_cache[cache_key]
    
    try:
        with GitRepoAnalyzer(repo_url, github_token) as git:
            # Resolve the branch ref to use
            ref = branch if branch == 'HEAD' else f'origin/{branch}'
            total = sum(1 for _ in git.repo.iter_commits(ref))
            
            # Cache the result
            st.session_state.commits_cache[cache_key] = total
            return total
    except Exception as e:
        st.warning(f"Could not get total commits: {e}")
        return 100  # Default fallback

# Helper function to extract commits between refs - FIXED
def extract_commits_between_refs(repo_url, baseline_ref, current_ref, github_token=None):
    """Extract commits between two specific refs with proper data structure"""
    cache_key = f"{repo_url}|{baseline_ref}|{current_ref}"
    
    # Check cache
    if cache_key in st.session_state.commits_cache:
        return st.session_state.commits_cache[cache_key]
    
    try:
        commits = []
        
        with GitRepoAnalyzer(repo_url, github_token) as git:
            # Get commits in range using GitPython
            commit_range = f"{baseline_ref}..{current_ref}"
            
            for commit in git.repo.iter_commits(commit_range):
                # Get changed files with stats
                changed_files = []
                for file, stats in commit.stats.files.items():
                    changed_files.append({
                        'file': file,
                        'insertions': stats['insertions'],
                        'deletions': stats['deletions'],
                        'lines': stats['lines']
                    })
                
                # Get diffs (optional, for detailed analysis)
                diffs = []
                if commit.parents:
                    parent = commit.parents[0]
                    for diff in parent.diff(commit, create_patch=True):
                        diff_data = {
                            'change_type': diff.change_type,
                            'old_path': diff.a_path,
                            'new_path': diff.b_path,
                        }
                        
                        if diff.diff:
                            try:
                                diff_text = diff.diff.decode('utf-8', errors='ignore')
                                if len(diff_text) > 10000:
                                    diff_data['diff'] = diff_text[:10000] + "\n... [truncated]"
                                else:
                                    diff_data['diff'] = diff_text
                            except:
                                diff_data['diff'] = None
                        
                        diffs.append(diff_data)
                
                # Build properly structured commit dict
                commit_data = {
                    'sha': commit.hexsha,
                    'author': {
                        'name': commit.author.name,
                        'email': commit.author.email
                    },
                    'date': commit.committed_datetime.isoformat(),
                    'message': commit.message.strip(),
                    'changed_files': changed_files,
                    'diffs': diffs,
                    'stats': {
                        'total_files': len(changed_files),
                        'total_insertions': commit.stats.total['insertions'],
                        'total_deletions': commit.stats.total['deletions'],
                        'total_lines': commit.stats.total['lines']
                    }
                }
                
                commits.append(commit_data)
        
        # Cache the result
        st.session_state.commits_cache[cache_key] = commits
        
        return commits
        
    except Exception as e:
        st.error(f"Failed to extract commits: {e}")
        import traceback
        st.code(traceback.format_exc())
        return []

# Helper function to extract commits by range
def extract_commits_by_range(repo_url, start_index, end_index, github_token=None, branch='HEAD'):
    """Extract commits by index range on a specific branch."""
    cache_key = f"{repo_url}|range|{start_index}|{end_index}|{branch}"
    
    # Check cache
    if cache_key in st.session_state.commits_cache:
        return st.session_state.commits_cache[cache_key]
    
    try:
        commits = []
        
        with GitRepoAnalyzer(repo_url, github_token) as git:
            # Resolve the branch ref
            ref = branch if branch == 'HEAD' else f'origin/{branch}'
            skip = start_index - 1
            count = end_index - start_index + 1
            
            all_commits_iter = git.repo.iter_commits(ref, skip=skip, max_count=count)
            
            for commit in all_commits_iter:
                changed_files = []
                for file, stats in commit.stats.files.items():
                    changed_files.append({
                        'file': file,
                        'insertions': stats['insertions'],
                        'deletions': stats['deletions'],
                        'lines': stats['lines']
                    })
                
                # Get diffs (for detailed line-by-line analysis)
                diffs = []
                if commit.parents:
                    parent = commit.parents[0]
                    for diff in parent.diff(commit, create_patch=True):
                        diff_data = {
                            'change_type': diff.change_type,
                            'old_path': diff.a_path,
                            'new_path': diff.b_path,
                        }
                        
                        if diff.diff:
                            try:
                                diff_text = diff.diff.decode('utf-8', errors='ignore')
                                if len(diff_text) > 10000:
                                    diff_data['diff'] = diff_text[:10000] + "\n... [truncated]"
                                else:
                                    diff_data['diff'] = diff_text
                            except:
                                diff_data['diff'] = None
                        
                        diffs.append(diff_data)
                
                commits.append({
                    'sha': commit.hexsha,
                    'author': {
                        'name': commit.author.name,
                        'email': commit.author.email
                    },
                    'date': commit.committed_datetime.isoformat(),
                    'message': commit.message.strip(),
                    'changed_files': changed_files,
                    'diffs': diffs,
                    'stats': {
                        'total_files': len(changed_files),
                        'total_insertions': commit.stats.total['insertions'],
                        'total_deletions': commit.stats.total['deletions'],
                        'total_lines': commit.stats.total['lines']
                    }
                })
        
        # Cache the result
        st.session_state.commits_cache[cache_key] = commits
        
        return commits
        
    except Exception as e:
        st.error(f"Failed to extract commits: {e}")
        return []


# Calculate total impact from commits
def calculate_commit_impact(commits):
    """Calculate overall impact stats from a list of commits."""
    total_commits = len(commits)
    total_insertions = 0
    total_deletions = 0
    total_files = 0
    
    for commit in commits:
        if isinstance(commit, dict) and 'stats' in commit:
            stats = commit['stats']
            total_insertions += stats.get('total_insertions', 0)
            total_deletions += stats.get('total_deletions', 0)
            total_files += stats.get('total_files', 0)
    
    return {
        'total_commits': total_commits,
        'total_insertions': total_insertions,
        'total_deletions': total_deletions,
        'total_files': total_files,
    }


# ── Pairwise commit inference helpers ──────────────────────────

def get_pairwise_diffs(repo_url, commits_list, github_token=None):
    """
    Given an ordered list of commits (newest-first from GitPython),
    return a list of dicts describing what changed between each
    consecutive pair (older → newer).
    """
    if len(commits_list) < 2:
        return []

    # commits_list is newest-first; reverse so pairs go old→new
    ordered = list(reversed(commits_list))
    pairs = []

    try:
        with GitRepoAnalyzer(repo_url, github_token) as git_analyzer:
            for i in range(len(ordered) - 1):
                older = ordered[i]
                newer = ordered[i + 1]

                older_sha = older['sha']
                newer_sha = newer['sha']

                # Get diff between the two commits
                changed_files = []
                diff_texts = []
                try:
                    older_commit = git_analyzer.repo.commit(older_sha)
                    newer_commit = git_analyzer.repo.commit(newer_sha)

                    for diff_item in older_commit.diff(newer_commit, create_patch=True):
                        file_path = diff_item.b_path or diff_item.a_path
                        diff_text = ""
                        if diff_item.diff:
                            try:
                                diff_text = diff_item.diff.decode('utf-8', errors='ignore')
                                if len(diff_text) > 5000:
                                    diff_text = diff_text[:5000] + "\n... [truncated]"
                            except Exception:
                                diff_text = ""

                        changed_files.append(file_path)
                        diff_texts.append({"file": file_path, "diff": diff_text})
                except Exception as e:
                    changed_files = []
                    diff_texts = []

                pairs.append({
                    "older": older,
                    "newer": newer,
                    "changed_files": changed_files,
                    "diffs": diff_texts,
                })

    except Exception as e:
        st.error(f"Failed to get pairwise diffs: {e}")
        return []

    return pairs


def generate_commit_pair_inference(llm, pair):
    """Use the LLM to summarise what changed between two commits."""
    older = pair["older"]
    newer = pair["newer"]
    diffs = pair["diffs"]

    # Build a concise prompt
    diff_summary_parts = []
    for d in diffs[:10]:  # cap at 10 files
        snippet = d["diff"][:1500] if d["diff"] else "(binary or empty)"
        diff_summary_parts.append(f"### {d['file']}\n```\n{snippet}\n```")

    diff_block = "\n\n".join(diff_summary_parts) if diff_summary_parts else "No file diffs available."

    prompt = f"""You are a senior software engineer reviewing commits.

**Older Commit:** {older['sha'][:8]} — {older['message']}
**Newer Commit:** {newer['sha'][:8]} — {newer['message']}
**Author:** {newer['author']['name']}
**Files Changed:** {', '.join(pair['changed_files'][:15]) or 'none detected'}

### Diffs
{diff_block}

Provide a concise inference (3-6 bullet points) covering:
1. **What changed** — summarise the code changes in plain English.
2. **Why it likely changed** — infer the intent (bug fix, feature, refactor, config, etc.).
3. **Potential impact** — what parts of the system could be affected.
4. **Risk level** — Low / Medium / High and a one-line justification.

Be specific: reference file names and line-level details where possible."""

    if not llm or not llm.client:
        # Fallback: rule-based summary when no LLM is available
        files_str = ", ".join(pair["changed_files"][:5]) or "unknown"
        return (
            f"- **Files changed:** {files_str}\n"
            f"- **Commit message:** {newer['message']}\n"
            f"- *LLM not configured — showing basic summary only.*"
        )

    try:
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert code reviewer. Provide concise, "
                        "actionable commit-pair analysis in Markdown bullet points."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=800,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ LLM inference failed: {e}"


# ── Login gate ──────────────────────────────────────────────
authenticator.login("main")

if st.session_state.get("authentication_status") is None:
    st.info("Please enter your credentials to continue.")
    st.stop()
elif st.session_state.get("authentication_status") is False:
    st.error("Username or password is incorrect.")
    st.stop()

# ── User is authenticated beyond this point ─────────────────

# Sidebar
with st.sidebar:
    st.markdown(f"👤 Logged in as **{st.session_state.get('name', '')}**")
    authenticator.logout("Logout", "sidebar")
    st.divider()

    # ═══════════════════════════════════════════════════════
    # Repository Configuration - ALWAYS VISIBLE
    # ═══════════════════════════════════════════════════════
    st.header("📂 Repository Configuration")
    
    repo_url = st.text_input(
        "Git Repository URL",
        value="https://github.com/Nikita-0506/QA-AI-ACCELERATOR",
        help="GitHub repository URL"
    )
    
    github_token = st.text_input(
        "GitHub Token (optional)",
        type="password",
        value=os.getenv("GITHUB_TOKEN", ""),
        help="Required for private repositories"
    )
    
    # Fetch branches and commit counts when repo URL changes
    if repo_url:
        if st.session_state.get('last_repo_url') != repo_url or not st.session_state.repo_branches:
            with st.spinner("Fetching repository info..."):
                branch_info = get_repo_branches(repo_url, github_token or None)
                st.session_state.repo_branches = branch_info["branches"]
                st.session_state.branch_commit_counts = branch_info["commit_counts"]
                st.session_state.last_repo_url = repo_url
                # Default to the first branch (usually main/master)
                if st.session_state.repo_branches:
                    st.session_state.selected_branch = st.session_state.repo_branches[0]
    
    st.divider()
    
    # ═══════════════════════════════════════════════════════
    # Compute branch data inside sidebar for caption display
    # ═══════════════════════════════════════════════════════
    _sb_selected_branch = st.session_state.selected_branch if st.session_state.selected_branch else "main"
    _sb_total = st.session_state.branch_commit_counts.get(_sb_selected_branch, 100) if st.session_state.branch_commit_counts else 100
    st.session_state.total_commits = _sb_total
    
    st.divider()
    
    # Azure OpenAI Status
    st.header("🔑 Azure OpenAI")
    
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    azure_key = os.getenv("AZURE_OPENAI_KEY")
    openai_key_env = os.getenv("OPENAI_API_KEY")
    
    if azure_endpoint and azure_deployment and azure_key:
        st.success("✅ Credentials loaded from .env")
        with st.expander("View Configuration", expanded=False):
            st.caption(f"**Endpoint:** {azure_endpoint[:50]}...")
            st.caption(f"**Deployment:** {azure_deployment}")
    elif openai_key_env:
        st.success("✅ OpenAI Credentials loaded from .env")
    else:
        st.warning("⚠️ No AI credentials configured")
        st.caption("Add credentials to .env file")
    
    # Optional override
    openai_key_override = st.text_input(
        "API Key Override (optional)",
        type="password",
        value="",
        help="Override .env configuration"
    )
    
    # Caching option
    st.divider()
    st.header("⚙️ Settings")
    
    enable_cache = st.checkbox(
        "Enable Caching",
        value=True,
        help="Cache LLM results for faster repeat analysis"
    )
    
    cache_dir = ".llm_cache" if enable_cache else None
    

# ── Branch data (module scope for use in all tabs) ────────
available_branches = st.session_state.repo_branches if st.session_state.repo_branches else ["main"]
branch_commit_counts = st.session_state.branch_commit_counts if st.session_state.branch_commit_counts else {"main": 100}

# Main content area
st.title("🧪 Testing Engine")
st.markdown("**AI-Powered Test Failure Analysis — Commits × Reports > Actionable Intelligence**")

# ── Fetch S3 report folders (cached) ──────────────────────
s3_folders = list_s3_report_folders()
st.session_state.s3_report_folders = s3_folders

# ── Report loading is deferred until the user picks an S3 folder ──
baseline_content = None
current_content = None
ready_status = False

# Show metrics if we have report data
if 'report' in st.session_state and st.session_state.metrics:
    metrics = st.session_state.metrics
    
    # Metrics cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['commits']}</div>
            <div class="metric-label">COMMITS</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['test_reports']}</div>
            <div class="metric-label">TEST REPORTS</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['report_size_kb']}</div>
            <div class="metric-label">REPORT SIZE (KB)</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['contributors']}</div>
            <div class="metric-label">CONTRIBUTORS</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🤖 AI Analysis",
    "📦 Commits",
    "🔧 Code Changes",
    "🔍 Commit Inference",
    "📊 Test Reports",
    "📜 History"
])

with tab1:
    st.header("Run AI Analysis")
    st.markdown("Send commit history and test reports to Azure OpenAI for intelligent root cause analysis.")

    # ── Branch, Commit Range & S3 folder selectors ─────────────
    sel_col1, sel_col2 = st.columns(2)

    with sel_col1:
        analysis_branch = st.selectbox(
            "🌿 Git Branch",
            options=available_branches,
            index=0,
            format_func=lambda b: f"{b} ({branch_commit_counts.get(b, '?')} commits)",
            key="analysis_branch_select",
            help="Branch to pull commits from for analysis",
        )

    with sel_col2:
        if s3_folders:
            selected_s3_folder = st.selectbox(
                "📂 S3 Report Folder",
                options=s3_folders,
                index=0,
                key="s3_folder_select",
                help=f"Report folders in s3://{S3_BUCKET_NAME}/{S3_REPORTS_PREFIX}",
            )
        else:
            selected_s3_folder = None
            local_json_files = [f.name for f in LOCAL_REPORTS_DIR.iterdir() if f.suffix.lower() == ".json"] if LOCAL_REPORTS_DIR.exists() else []
            if local_json_files:
                st.info(f"📁 Using local reports from `html-reports/`: {', '.join(local_json_files)}")
            else:
                st.warning("No report folders found in S3 and no local JSON reports in `html-reports/`.")

    # Commit range slider — adjusts to the selected branch
    branch_total = branch_commit_counts.get(analysis_branch, 100)
    if branch_total > 1:
        commit_range = st.slider(
            "📦 Commit Range (newest → oldest)",
            min_value=1,
            max_value=branch_total,
            value=(1, min(30, branch_total)),
            help="Select range of commits to analyze (1 = newest commit)",
        )
        start_commit, end_commit = commit_range
    else:
        start_commit, end_commit = 1, 1
        st.info("📦 Commit Range: only 1 commit available on this branch.")
    st.caption(f"Analyzing commits **{start_commit}** to **{end_commit}** ({end_commit - start_commit + 1} commits) on **{analysis_branch}**")

    # Load reports: prefer S3 folder, fall back to local html-reports/
    if selected_s3_folder:
        report_data = download_s3_reports(selected_s3_folder)
    else:
        report_data = load_local_reports()

    json_reports = report_data.get("json_reports", [])
    if len(json_reports) >= 2:
        baseline_content = json_reports[0][1]
        current_content = json_reports[1][1]
        ready_status = True
    elif len(json_reports) == 1:
        # Single report mode — duplicate as both baseline and current
        baseline_content = json_reports[0][1]
        current_content = json_reports[0][1]
        ready_status = True
    else:
        if selected_s3_folder:
            st.warning(f"No JSON reports found in folder **{selected_s3_folder}**.")
        else:
            st.warning("No JSON reports found. Add `.json` files to the `html-reports/` folder.")

    # ── Analyze button + status ─────────────────────────────────
    col1, col2 = st.columns([1, 2])

    with col1:
        analyze_button = st.button("🔬 Analyze Now", type="primary", use_container_width=True, disabled=not ready_status)

    with col2:
        if ready_status:
            num_commits = end_commit - start_commit + 1
            folder_label = selected_s3_folder or "—"
            st.markdown(f"""
            <div class="status-badge status-ready">
                ✅ Ready — Branch: {analysis_branch} | Commits {start_commit}-{end_commit} ({num_commits}) | Reports: {folder_label}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.error("❌ Select an S3 report folder with JSON reports")

    # Analysis logic
    if analyze_button:
        if not ready_status:
            st.error("❌ Select an S3 report folder with JSON reports")
            st.stop()
        
        # Progress tracking
        progress_container = st.container()
        progress_bar = st.progress(0)
        output_container = st.expander("📊 Analysis Progress", expanded=True)
        
        with st.spinner("🔎 Analyzing repository and generating AI insights..."):
            try:
                with output_container:
                    status_placeholder = st.empty()
                    
                    # Parse reports
                    status_placeholder.info("📖 Parsing test reports...")
                    progress_bar.progress(10)
                    
                    baseline_summary = CucumberJsonParser.parse(baseline_content)
                    current_summary = CucumberJsonParser.parse(current_content)
                    
                    status_placeholder.success(f"✓ Parsed: {baseline_summary.total} baseline, {current_summary.total} current tests")
                    
                    # Git analysis — commit range on selected branch
                    status_placeholder.info(f"🔍 Extracting commits {start_commit} to {end_commit} on branch '{analysis_branch}'...")
                    progress_bar.progress(20)
                    
                    commits = extract_commits_by_range(repo_url, start_commit, end_commit, github_token or None, branch=analysis_branch)
                    
                    if not commits:
                        st.error("❌ Failed to extract commits.")
                        st.stop()
                    
                    raw_changes = []
                    
                    status_placeholder.success(f"✓ Extracted {len(commits)} commits")
                    
                    progress_bar.progress(30)
                    
                    # Calculate metrics
                    contributors = len(set(c['author']['name'] for c in commits if isinstance(c, dict) and 'author' in c))
                    report_size_kb = round((len(baseline_content) + len(current_content)) / 1024, 1)
                    
                    st.session_state.metrics = {
                        'commits': len(commits),
                        'test_reports': 2,
                        'report_size_kb': report_size_kb,
                        'contributors': contributors
                    }
                    
                    # Build report
                    status_placeholder.info("🤖 Initializing AI analyzer...")
                    
                    report_builder = EnhancedReportBuilder(
                        openai_api_key=openai_key_override or None,
                        max_workers=MAX_WORKERS,
                        cache_dir=cache_dir,
                        max_detailed_analysis=MAX_DETAILED_ANALYSIS
                    )
                    
                    progress_bar.progress(40)
                    
                    # Find regressions
                    status_placeholder.info("🔬 Comparing test runs...")
                    regressions = RunComparator.find_regressions(baseline_summary, current_summary)
                    improvements = RunComparator.find_improvements(baseline_summary, current_summary)
                    duration_regressions = RunComparator.find_duration_regressions(baseline_summary, current_summary)
                    
                    status_placeholder.success(f"✓ Found {len(regressions)} regressions, {len(improvements)} improvements")
                    progress_bar.progress(50)
                    
                    # AI Analysis
                    status_placeholder.info("🧠 Running AI analysis...")
                    
                    old_stdout = sys.stdout
                    sys.stdout = captured_output = StringIO()
                    
                    try:
                        report = report_builder.build_detailed_report(
                            repo_url=repo_url,
                            baseline_commit=f"HEAD~{end_commit}",
                            current_commit=f"HEAD~{start_commit-1}",
                            baseline_summary=baseline_summary,
                            current_summary=current_summary,
                            commits=commits,
                            raw_file_changes=raw_changes,
                            regressions=regressions,
                            improvements=improvements,
                            duration_regressions=duration_regressions
                        )
                        
                        output_text = captured_output.getvalue()
                        if output_text:
                            st.code(output_text, language="text")
                        
                    finally:
                        sys.stdout = old_stdout
                    
                    progress_bar.progress(100)
                    status_placeholder.success("✅ Analysis complete!")
                    
                    st.session_state.report = report
                    st.session_state.commits = commits
                    st.session_state.analysis_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    st.rerun()
                    
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.exception(e)
    
    # Display results
    if 'report' in st.session_state:
        st.divider()
        st.header("📋 Analysis Results")
        
        if st.session_state.analysis_timestamp:
            st.caption(f"Generated: {st.session_state.analysis_timestamp}")
        
        report = st.session_state.report
        
        # Executive Summary
        st.subheader("📊 Executive Summary")
        st.info(report["executive_summary"])
        
        # Test Impact Analysis - Regressions
        st.divider()
        st.subheader("❌ Tests That Failed (Previously Passed)")
        
        detailed_regressions = [r for r in report["regressions"] 
                                if "Not analyzed in detail" not in str(r.get("analysis", {}).get("root_cause", ""))]
        
        if detailed_regressions:
            # Count timeout-related failures
            timeout_failures = []
            non_timeout_failures = []
            
            for regression in detailed_regressions:
                error_msg = regression.get("error_message", "")
                explanation = regression.get("analysis", {}).get("detailed_explanation", "")
                
                if detect_timeout_issue(error_msg, explanation):
                    timeout_failures.append(regression)
                else:
                    non_timeout_failures.append(regression)
            
            # Display summary with timeout count
            if timeout_failures:
                st.warning(f"**{len(detailed_regressions)} test(s) regressed** - Previously passing tests now failing ({len(timeout_failures)} timeout-related)")
            else:
                st.warning(f"**{len(detailed_regressions)} test(s) regressed** - Previously passing tests now failing")
            
            # Display timeout failures first with special highlighting
            if timeout_failures:
                st.markdown("### ⏱️ Timeout-Related Failures (High Priority)")
                
                for i, regression in enumerate(timeout_failures):
                    analysis = regression.get("analysis", {})
                    
                    st.markdown(f"""
                    <div style="background-color: #451a03; border-left: 4px solid #f59e0b; padding: 15px; margin: 10px 0; border-radius: 4px;">
                        <h4 style="color: #f59e0b; margin: 0;">⏱️ {regression['scenario_name']} <span class="timeout-badge">⚠️ TIMEOUT</span></h4>
                        <p style="color: #999; font-size: 14px; margin: 5px 0;">Feature: {regression['feature']}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    with st.expander("📖 View Detailed Root Cause Analysis", expanded=False):
                        # Timeout-specific alert
                        st.markdown("""
                        <div class="timeout-alert">
                            <h4 style="color: #f59e0b; margin-top: 0;">⏱️ Session Timeout Detected</h4>
                            <p style="color: #fbbf24; margin-bottom: 0;">
                                This test failed due to a <strong>timeout/session timeout issue</strong>. 
                                The application did not respond within the expected time window, which may indicate:
                            </p>
                            <ul style="color: #fcd34d;">
                                <li>Session expired before test completion</li>
                                <li>Authentication service delay or unavailability</li>
                                <li>Page loading performance degradation</li>
                                <li>Network latency or connection issues</li>
                                <li>Element not becoming available within timeout period</li>
                            </ul>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.markdown("---")
                        
                        # Root Cause Section
                        st.markdown("### 🎯 Root Cause Analysis")
                        
                        if analysis.get("analysis_type") == "llm_powered":
                            provider = analysis.get("provider", "AI")
                            st.success(f"🤖 Powered by {provider}")
                        
                        explanation = analysis.get("detailed_explanation", "No analysis available")
                        
                        # Parse and format the explanation into sections
                        st.markdown(explanation)
                        
                        # Show exact line changes if available
                        st.markdown("---")
                        st.markdown("### 📝 Exact Changes That Caused This Failure")
                        
                        # Try to extract specific changes from detailed_file_changes
                        relevant_changes = []
                        for file_change in report.get("detailed_file_changes", []):
                            if any(keyword in file_change['file_path'].lower() 
                                   for keyword in ['feature', 'step', 'page', 'locator', 'timeout', 'wait']):
                                relevant_changes.append(file_change)
                        
                        if relevant_changes:
                            for file_change in relevant_changes[:3]:
                                st.markdown(f"**📄 {file_change['file_path']}**")
                                st.caption(file_change['summary'])
                                
                                for line_change in file_change["line_changes"][:5]:
                                    if line_change['change_type'] == 'modified':
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.markdown(f"**❌ Line {line_change['line_number']} (Before)**")
                                            st.code(line_change.get('old_content', ''), language="text")
                                        with col2:
                                            st.markdown(f"**✅ Line {line_change['line_number']} (After)**")
                                            st.code(line_change.get('new_content', ''), language="text")
                                        
                                        st.markdown("**💡 Impact:** This change directly affected test behavior and timing")
                                        st.markdown("---")
                                    
                                    elif line_change['change_type'] == 'added':
                                        st.markdown(f"**➕ Line {line_change['line_number']} (Added)**")
                                        st.code(line_change.get('new_content', ''), language="text")
                                        st.markdown("**💡 Impact:** New code introduced")
                                        st.markdown("---")
                                    
                                    elif line_change['change_type'] == 'removed':
                                        st.markdown(f"**➖ Line {line_change['line_number']} (Removed)**")
                                        st.code(line_change.get('old_content', ''), language="text")
                                        st.markdown("**💡 Impact:** Code removed")
                                        st.markdown("---")
                        else:
                            st.info("No specific line changes identified. Check commit details in the Commits tab.")
                        
                        # Error details
                        st.markdown("---")
                        st.markdown("### 🐛 Error Details")
                        
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            error_msg = regression.get("error_message", "No error message")
                            st.code(error_msg, language="text")
                        
                        with col2:
                            st.metric(
                                "Duration Change",
                                f"{regression['current_duration_ms']:.0f}ms",
                                f"+{regression['current_duration_ms'] - regression['baseline_duration_ms']:.0f}ms"
                            )
                        
                        # Timeout-specific recommendations
                        st.markdown("---")
                        st.markdown("### 💡 Recommended Actions for Timeout Issues")
                        st.markdown("""
                        - **Increase timeout values** if the application legitimately needs more time
                        - **Check session management** - verify session timeout configuration matches test duration
                        - **Investigate authentication service** - ensure auth endpoints are responsive
                        - **Review page load performance** - check for recent changes affecting load times
                        - **Verify environment stability** - confirm network connectivity and service availability
                        - **Check wait conditions** - ensure explicit waits are properly configured
                        - **Review test data** - confirm test credentials and data are valid
                        """)
                        
                        # Key Points Summary
                        st.markdown("---")
                        st.markdown("### 📌 Key Points")
                        
                        lines = explanation.split('\n')
                        key_points = []
                        for line in lines:
                            line = line.strip()
                            if line.startswith('- ') or line.startswith('* ') or line.startswith('1.') or line.startswith('2.') or line.startswith('3.'):
                                key_points.append(line)
                        
                        if key_points:
                            for point in key_points[:5]:
                                st.markdown(point)
                        else:
                            st.markdown("- Test failed due to timeout/session timeout")
                            st.markdown("- Application did not respond within expected time")
                            st.markdown("- Review recent code changes affecting timing")
                            st.markdown("- Check session configuration and authentication flow")
            
            # Display non-timeout failures
            if non_timeout_failures:
                if timeout_failures:
                    st.markdown("---")
                    st.markdown("### 🔴 Other Failures")
                
                for i, regression in enumerate(non_timeout_failures):
                    analysis = regression.get("analysis", {})
                    
                    st.markdown(f"""
                    <div style="background-color: #2d1e1e; border-left: 4px solid #ef4444; padding: 15px; margin: 10px 0; border-radius: 4px;">
                        <h4 style="color: #ef4444; margin: 0;">🔴 {regression['scenario_name']}</h4>
                        <p style="color: #999; font-size: 14px; margin: 5px 0;">Feature: {regression['feature']}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    with st.expander("📖 View Detailed Root Cause Analysis", expanded=False):
                        # Root Cause Section
                        st.markdown("### 🎯 Root Cause Analysis")
                        
                        if analysis.get("analysis_type") == "llm_powered":
                            provider = analysis.get("provider", "AI")
                            st.success(f"🤖 Powered by {provider}")
                        
                        explanation = analysis.get("detailed_explanation", "No analysis available")
                        st.markdown(explanation)
                        
                        # Show exact line changes
                        st.markdown("---")
                        st.markdown("### 📝 Exact Changes That Caused This Failure")
                        
                        relevant_changes = []
                        for file_change in report.get("detailed_file_changes", []):
                            if any(keyword in file_change['file_path'].lower() 
                                   for keyword in ['feature', 'step', 'page', 'locator']):
                                relevant_changes.append(file_change)
                        
                        if relevant_changes:
                            for file_change in relevant_changes[:3]:
                                st.markdown(f"**📄 {file_change['file_path']}**")
                                st.caption(file_change['summary'])
                                
                                for line_change in file_change["line_changes"][:5]:
                                    if line_change['change_type'] == 'modified':
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.markdown(f"**❌ Line {line_change['line_number']} (Before)**")
                                            st.code(line_change.get('old_content', ''), language="text")
                                        with col2:
                                            st.markdown(f"**✅ Line {line_change['line_number']} (After)**")
                                            st.code(line_change.get('new_content', ''), language="text")
                                        
                                        st.markdown("**💡 Impact:** This change directly affected test behavior")
                                        st.markdown("---")
                                    
                                    elif line_change['change_type'] == 'added':
                                        st.markdown(f"**➕ Line {line_change['line_number']} (Added)**")
                                        st.code(line_change.get('new_content', ''), language="text")
                                        st.markdown("**💡 Impact:** New code introduced")
                                        st.markdown("---")
                                    
                                    elif line_change['change_type'] == 'removed':
                                        st.markdown(f"**➖ Line {line_change['line_number']} (Removed)**")
                                        st.code(line_change.get('old_content', ''), language="text")
                                        st.markdown("**💡 Impact:** Code removed")
                                        st.markdown("---")
                        else:
                            st.info("No specific line changes identified. Check commit details in the Commits tab.")
                        
                        # Error details
                        st.markdown("---")
                        st.markdown("### 🐛 Error Details")
                        
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            error_msg = regression.get("error_message", "No error message")
                            st.code(error_msg, language="text")
                        
                        with col2:
                            st.metric(
                                "Duration Change",
                                f"{regression['current_duration_ms']:.0f}ms",
                                f"+{regression['current_duration_ms'] - regression['baseline_duration_ms']:.0f}ms"
                            )
                        
                        # Key Points
                        st.markdown("---")
                        st.markdown("### 📌 Key Points")
                        
                        lines = explanation.split('\n')
                        key_points = []
                        for line in lines:
                            line = line.strip()
                            if line.startswith('- ') or line.startswith('* ') or line.startswith('1.') or line.startswith('2.') or line.startswith('3.'):
                                key_points.append(line)
                        
                        if key_points:
                            for point in key_points[:5]:
                                st.markdown(point)
                        else:
                            st.markdown("- Test failed due to code changes")
                            st.markdown("- Review the detailed explanation above")
                            st.markdown("- Check exact line changes in the previous section")
        else:
            st.success("✅ No regressions found - all previously passing tests still pass!")
        
        # Test Improvements - Tests that now pass
        st.divider()
        st.subheader("✅ Tests That Passed (Previously Failed)")
        
        improvements = report.get("improvements", [])
        
        if improvements:
            st.success(f"**{len(improvements)} test(s) improved** - Previously failing tests now passing!")
            
            with st.expander(f"View All Improvements ({len(improvements)})", expanded=True):
                st.markdown("### 🎉 What Changed to Fix These Tests?")
                
                for improvement in improvements:
                    st.markdown(f"""
                    <div style="background-color: #1e2d1e; border-left: 4px solid #22c55e; padding: 15px; margin: 10px 0; border-radius: 4px;">
                        <h4 style="color: #22c55e; margin: 0;">✅ {improvement}</h4>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("---")
                st.markdown("### 📝 Code Changes That Fixed Issues")
                
                # Show relevant positive changes
                if st.session_state.get('commits'):
                    st.markdown("**Recent commits that may have fixed these tests:**")
                    for commit in st.session_state.commits[:5]:
                        # Extract commit message first line outside f-string
                        commit_msg_first_line = commit['message'].split('\n')[0] if '\n' in commit['message'] else commit['message']
                        commit_author = commit['author']['name']
                        commit_sha = commit['sha'][:8]
                        commit_insertions = commit['stats']['total_insertions']
                        commit_deletions = commit['stats']['total_deletions']
                        
                        st.markdown(f"""
                        **🔑 `{commit_sha}`** - {commit_msg_first_line}  
                        👤 {commit_author} | {commit_insertions} additions, {commit_deletions} deletions
                        """)
                
                st.info("💡 **Analysis:** These tests now pass because the code changes corrected previous issues. Review the commits above to understand what was fixed.")
        else:
            st.info("ℹ️ No improvements detected - no previously failing tests have been fixed in this run.")
        
        # Quick Summary for other regressions
        quick_regressions = [r for r in report["regressions"] 
                            if "Not analyzed in detail" in str(r.get("analysis", {}).get("root_cause", ""))]
        
        if quick_regressions:
            st.divider()
            st.markdown(f"### ⚠️ Other Regressions ({len(quick_regressions)} lower priority)")
            
            with st.expander("View Other Regressions"):
                for regression in quick_regressions:
                    st.markdown(f"**{regression['scenario_name']}** ({regression['feature']})")
                    if regression.get('error_message'):
                        st.code(regression['error_message'][:200], language="text")
                    st.markdown("---")
        
        # Key Findings
        if report.get("key_findings"):
            st.divider()
            st.subheader("🔍 Key Findings")
            for finding in report["key_findings"]:
                st.warning(finding)

with tab2:
    st.header("📦 Commit History")
    
    if 'commits' in st.session_state and st.session_state.commits:
        commits = st.session_state.commits
        
        st.markdown(f"**Repository:** {repo_url.split('/')[-1]} | **Commits:** {start_commit} to {end_commit} ({len(commits)} total)")
        
        st.divider()
        
        st.subheader("�� Search commits")
        search_query = st.text_input(
            "Search by message, author, or hash...",
            placeholder="Search by message, author, or hash...",
            label_visibility="collapsed"
        )
        
        filtered_commits = commits
        if search_query:
            filtered_commits = [c for c in commits 
                               if search_query.lower() in c['message'].lower() 
                               or search_query.lower() in c['author']['name'].lower()
                               or search_query.lower() in c['sha'].lower()]
        
        for commit in filtered_commits:
            sha = commit['sha'][:8]
            author = commit['author']['name']
            date = commit['date']
            message = commit['message']
            
            with st.expander(f"**{sha}** — {message[:80]}", expanded=False):
                st.markdown(f"**Author:** {author}")
                st.markdown(f"**Date:** {date}")
                st.markdown(f"**Message:** {message}")
                
                if 'changed_files' in commit and commit['changed_files']:
                    st.markdown(f"**Files Changed:** {len(commit['changed_files'])}")
                    for file in commit['changed_files'][:5]:
                        st.markdown(f"- `{file['file']}`")
    else:
        st.info("Run analysis first to see commit history")
with tab3:
    st.header("🔧 Code Changes ")
    st.markdown("All commit changes with specific file modifications and line-by-line code diffs")
    
    if 'commits' in st.session_state and st.session_state.commits:
        commits = st.session_state.commits
        
        # Calculate and display impact summary
        impact = calculate_commit_impact(commits)
        
        # Impact summary card
        st.markdown(f"""
        <div class="changes-summary-card">
            <div class="changes-summary-title">📊 Overall Commit Impact</div>
            <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px;">
                <div style="text-align: center;">
                    <div style="font-size: 24px; font-weight: 600; color: #c9d1d9;">📦 {impact['total_commits']}</div>
                    <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">Total Commits</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 24px; font-weight: 600; color: #7ee787;">+ {impact['total_insertions']}</div>
                    <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">Lines Added</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 24px; font-weight: 600; color: #f85149;">- {impact['total_deletions']}</div>
                    <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">Lines Deleted</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 24px; font-weight: 600; color: #79c0ff;">📄 {impact['total_files']}</div>
                    <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">Files Modified</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.divider()
        
        # Select commit to view
        st.subheader("💻 Select Commit to View Changes")
        
        commits_with_changes = [c for c in commits if c.get('changed_files') and len(c.get('changed_files', [])) > 0]
        
        if commits_with_changes:
            selected_commit_idx = st.selectbox(
                "Choose a commit",
                range(len(commits_with_changes)),
                format_func=lambda i: f"{commits_with_changes[i]['sha'][:8]} — {commits_with_changes[i]['message'].split(chr(10))[0][:70]}"
            )
            
            selected_commit = commits_with_changes[selected_commit_idx]
            
            # Commit metadata
            st.markdown(f"""
            <div class="dark-code-container" style="margin-bottom: 16px;">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <div>
                        <div style="color: #8b949e; font-size: 12px;">COMMIT SHA</div>
                        <div style="color: #79c0ff; font-family: monospace; margin-top: 4px;">{selected_commit['sha']}</div>
                    </div>
                    <div>
                        <div style="color: #8b949e; font-size: 12px;">AUTHOR</div>
                        <div style="color: #c9d1d9; margin-top: 4px;">{selected_commit['author']['name']}</div>
                    </div>
                    <div style="grid-column: 1 / -1;">
                        <div style="color: #8b949e; font-size: 12px;">DATE</div>
                        <div style="color: #c9d1d9; margin-top: 4px;">{selected_commit['date']}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Commit message
            st.markdown(f"""
            <div class="dark-code-container" style="margin-bottom: 16px; border-left: 3px solid #79c0ff;">
                <div style="color: #79c0ff; font-weight: 600; margin-bottom: 8px;">COMMIT MESSAGE</div>
                <div style="color: #c9d1d9; white-space: pre-wrap; font-family: monospace;">{selected_commit['message']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Files changed summary
            changed_files = selected_commit.get('changed_files', [])
            if changed_files:
                st.divider()
                
                # Show all diffs for this commit
                diffs = selected_commit.get('diffs', [])
                
                # ============ SHOW IMPACT ANALYSIS FOR DETAILED VIEW ============
                st.markdown("### 📈 Impact Summary for Code Changes")
                
                # Get commit stats
                commit_stats = selected_commit.get('stats', {})
                total_files = commit_stats.get('total_files', len(changed_files))
                total_insertions = commit_stats.get('total_insertions', 0)
                total_deletions = commit_stats.get('total_deletions', 0)
                
                # Calculate potential impact on tests
                report = st.session_state.get('report', {})
                all_regressions = report.get('regressions', [])
                
                # For each changed file, try to find related regressions
                changed_file_paths = [f.get('file', '').lower() for f in changed_files]
                
                # Identify potentially affected tests
                related_regressions = []
                for regression in all_regressions:
                    regression_feature = regression.get('feature', '').lower()
                    for changed_file in changed_file_paths:
                        if regression_feature and regression_feature in changed_file or changed_file in regression_feature:
                            if regression not in related_regressions:
                                related_regressions.append(regression)
                            break
                
                # Display impact metrics in a row
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("📁 Files Changed", total_files)
                
                with col2:
                    st.metric("➕ Added", total_insertions, delta=f"+{total_insertions}")
                
                with col3:
                    st.metric("➖ Deleted", total_deletions, delta=f"-{total_deletions}")
                
                with col4:
                    st.metric("🧪 Related Tests", len(related_regressions))
                
                # Show compact view of related failures
                if related_regressions:
                    with st.expander("🔴 View Related Test Failures", expanded=False):
                        for i, regression in enumerate(related_regressions[:3]):
                            analysis = regression.get('analysis', {})
                            explanation = analysis.get('detailed_explanation', '')
                            summary_line = explanation.split('\n')[0] if explanation else "Test failure"
                            if len(summary_line) > 100:
                                summary_line = summary_line[:100] + "..."
                            
                            st.markdown(f"""
                            <div class="summary-box">
                                <div class="summary-text">❌ {regression['scenario_name']}</div>
                                <div style="color: #888; font-size: 12px;">Feature: {regression.get('feature', 'N/A')}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        if len(related_regressions) > 3:
                            st.caption(f"and {len(related_regressions) - 3} more failures")
                
                st.divider()
                
                # Always show section header
                st.markdown("### 🔍 Detailed Code Changes — Line by Line")
                
                if diffs:
                    diffs_with_content = [d for d in diffs if d.get('diff')]
                    
                    if diffs_with_content:
                        # Show each file as expandable/collapsible section
                        for idx, diff_item in enumerate(diffs_with_content):
                            file_path = diff_item.get('new_path') or diff_item.get('old_path') or 'unknown'
                            change_type = (diff_item.get('change_type') or 'modified').upper()
                            
                            # Get stats for this file
                            file_stats = next(
                                (f for f in changed_files if f['file'] == file_path),
                                {'insertions': 0, 'deletions': 0}
                            )
                            
                            insertions = file_stats.get('insertions', 0)
                            deletions = file_stats.get('deletions', 0)
                            
                            # Display file as expandable with badge
                            expander_label = f"📄 {file_path} — {change_type} (+{insertions} -{deletions})"
                            
                            with st.expander(expander_label, expanded=False):
                                # Display GitHub-style diff
                                diff_text = diff_item.get('diff', '')
                                if diff_text:
                                    # Parse and display diff with enhanced GitHub styling
                                    diff_lines = diff_text.split('\n')
                                    
                                    html_diff = '<div style="background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px; overflow-x: auto; padding: 0; margin: 8px 0;">'
                                    line_num_old = 0
                                    line_num_new = 0
                                    
                                    for line in diff_lines:
                                        # Escape HTML special characters
                                        line_escaped = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                                        
                                        if line.startswith('@@'):
                                            # Hunk header - location info
                                            html_diff += f'<div style="background-color: #1c2128; color: #58a6ff; padding: 6px 12px; font-family: \'Consolas\', \'Courier New\', monospace; font-size: 12px; border-top: 1px solid #30363d; font-weight: 600;">{line_escaped}</div>'
                                        elif line.startswith('+') and not line.startswith('+++'):
                                            # Added line - GREEN
                                            content = line_escaped[1:]  # Remove the + from line content
                                            html_diff += f'<div style="background-color: #1a3626; padding: 4px 8px; font-family: \'Consolas\', \'Courier New\', monospace; font-size: 13px; line-height: 1.5;"><span style="color: #4ade80; font-weight: bold; margin-right: 12px;">+</span><span style="color: #aff5b4;">{content}</span></div>'
                                            line_num_new += 1
                                        elif line.startswith('-') and not line.startswith('---'):
                                            # Removed line - RED
                                            content = line_escaped[1:]  # Remove the - from line content
                                            html_diff += f'<div style="background-color: #3b1819; padding: 4px 8px; font-family: \'Consolas\', \'Courier New\', monospace; font-size: 13px; line-height: 1.5;"><span style="color: #f85149; font-weight: bold; margin-right: 12px;">-</span><span style="color: #ffdcd7;">{content}</span></div>'
                                            line_num_old += 1
                                        elif line.startswith(' '):
                                            # Context line - unchanged
                                            content = line_escaped[1:]
                                            html_diff += f'<div style="background-color: #0d1117; padding: 4px 8px; font-family: \'Consolas\', \'Courier New\', monospace; font-size: 13px; line-height: 1.5;"><span style="color: #484f58; margin-right: 12px;"> </span><span style="color: #c9d1d9;">{content}</span></div>'
                                            line_num_old += 1
                                            line_num_new += 1
                                        elif line.startswith('---') or line.startswith('+++'):
                                            # File header
                                            html_diff += f'<div style="background-color: #161b22; color: #8b949e; padding: 6px 12px; font-family: \'Consolas\', \'Courier New\', monospace; font-size: 12px; font-weight: 600;">{line_escaped}</div>'
                                        elif line.strip():
                                            # Other content
                                            html_diff += f'<div style="background-color: #0d1117; color: #8b949e; padding: 4px 8px; font-family: \'Consolas\', \'Courier New\', monospace; font-size: 13px;">{line_escaped}</div>'
                                    
                                    html_diff += '</div>'
                                    st.markdown(html_diff, unsafe_allow_html=True)
                                else:
                                    st.markdown(f"""
                                    <div class="dark-code-container">
                                        <div style="color: #8b949e;">No diff content available</div>
                                    </div>
                                    """, unsafe_allow_html=True)
                    else:
                        st.markdown("""
                        <div class="dark-code-container">
                            <div style="color: #f59e0b;">⚠️ No detailed diffs available for this commit</div>
                            <div style="color: #8b949e; margin-top: 8px; font-size: 14px;">
                                File changes are recorded above, but line-by-line diffs were not captured during analysis.
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="dark-code-container">
                        <div style="color: #f59e0b;">⚠️ No diff data available for this commit</div>
                        <div style="color: #8b949e; margin-top: 8px; font-size: 14px;">
                            This may happen if the commit analysis didn't include detailed diffs. Try re-running the analysis or selecting a different commit.
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("No commits with file changes available")
    else:
        st.info("Run analysis first to see code changes")

with tab4:
    st.header("� Commit-by-Commit Inference")
    st.markdown(
        "Select a commit range and get an AI-powered summary of "
        "**what changed between each consecutive pair** of commits."
    )

    # ── Controls ──────────────────────────────────────────
    inf_col1, inf_col2 = st.columns([3, 1])

    with inf_col1:
        # Branch selector for inference
        inf_branch = st.selectbox(
            "Branch",
            options=available_branches,
            index=available_branches.index(analysis_branch) if analysis_branch in available_branches else 0,
            format_func=lambda b: f"{b}  ({branch_commit_counts.get(b, '?')} commits)",
            key="inf_branch_select",
            help="Choose the branch for commit inference",
        )
        inf_branch_total = branch_commit_counts.get(inf_branch, 100)

        # Compute a safe default upper bound for the slider
        inf_default_end = min(end_commit, inf_branch_total)

        if inf_branch_total > 1:
            inf_range = st.slider(
                "Commit range for inference",
                min_value=1,
                max_value=inf_branch_total,
                value=(1, max(inf_default_end, 2)),
                key="inf_range_slider",
                help="Pick the range of commits (1 = newest)",
            )
            inf_start, inf_end = inf_range
        else:
            inf_start, inf_end = 1, 1
            st.info("Only 1 commit available on this branch for inference.")

    with inf_col2:
        run_inference = st.button(
            "⚡ Run Inference", type="primary", use_container_width=True, key="run_inf"
        )

    # ── Execution ─────────────────────────────────────────
    if run_inference:
        with st.spinner(f"Cloning repo & computing pairwise diffs on '{inf_branch}'…"):
            # Fetch commits from the selected branch
            inf_commits = extract_commits_by_range(
                repo_url, inf_start, inf_end, github_token or None, branch=inf_branch
            )

            if len(inf_commits) < 2:
                st.warning("Need at least 2 commits to produce pairwise inference.")
            else:
                st.success(f"Fetched **{len(inf_commits)}** commits — generating **{len(inf_commits)-1}** pairwise inferences.")

                pairs = get_pairwise_diffs(repo_url, inf_commits, github_token or None)

                if not pairs:
                    st.error("Could not compute diffs between commits.")
                else:
                    # Initialise LLM (reuses existing Azure / OpenAI config)
                    llm = LLMAnalyzer(api_key=openai_key_override or None)

                    progress = st.progress(0)
                    status_msg = st.empty()
                    total_pairs = len(pairs)

                    # Run LLM inference in parallel (up to 10 concurrent calls)
                    INFERENCE_TIMEOUT = 220  # seconds per call
                    indexed_results = {}  # index -> (pair, text)
                    completed_count = 0

                    def _infer(idx_pair):
                        idx, pair = idx_pair
                        return idx, pair, generate_commit_pair_inference(llm, pair)

                    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                        futures = {
                            executor.submit(_infer, (i, p)): i
                            for i, p in enumerate(pairs)
                        }

                        for future in as_completed(futures):
                            try:
                                idx, pair, text = future.result(timeout=INFERENCE_TIMEOUT)
                                indexed_results[idx] = (pair, text)
                            except TimeoutError:
                                idx = futures[future]
                                indexed_results[idx] = (
                                    pairs[idx],
                                    "⚠️ Inference timed out for this commit pair."
                                )
                            except Exception as e:
                                idx = futures[future]
                                indexed_results[idx] = (
                                    pairs[idx],
                                    f"⚠️ Inference failed: {e}"
                                )

                            completed_count += 1
                            progress.progress(completed_count / total_pairs)
                            status_msg.caption(f"Completed {completed_count}/{total_pairs} inferences")

                    # Reassemble in original order
                    results = [indexed_results[i] for i in range(total_pairs)]
                    status_msg.empty()

                    # Store in session for persistence across reruns
                    st.session_state["inference_results"] = results

    # ── Display results ───────────────────────────────────
    if "inference_results" in st.session_state and st.session_state["inference_results"]:
        results = st.session_state["inference_results"]
        st.divider()
        st.subheader(f"📋 Pairwise Inference  ({len(results)} pairs)")

        for idx, (pair, inference_text) in enumerate(results):
            older = pair["older"]
            newer = pair["newer"]
            label = (
                f"**{older['sha'][:8]}** → **{newer['sha'][:8]}**  ·  "
                f"{newer['message'][:70]}"
            )

            with st.expander(label, expanded=(idx == 0)):
                meta_col1, meta_col2, meta_col3 = st.columns([2, 2, 1])
                with meta_col1:
                    st.caption(f"**Author:** {newer['author']['name']}")
                with meta_col2:
                    st.caption(f"**Date:** {newer['date'][:10]}")
                with meta_col3:
                    st.caption(f"**Files:** {len(pair['changed_files'])}")

                # Show changed file list
                if pair["changed_files"]:
                    st.markdown("**📂 Changed files:**")
                    for f in pair["changed_files"]:
                        st.markdown(f"- `{f}`")

                st.markdown("---")
                st.markdown(inference_text)
    else:
        if not run_inference if 'run_inference' in dir() else True:
            st.info("Select a commit range above and click **⚡ Run Inference** to begin.")

with tab5:
    st.header("�📊 Test Reports")
    
    if ready_status and baseline_content and current_content:
        st.markdown("### 📄 Test Reports Preview")
        
        with st.expander("📊 Report Preview", expanded=True):
            if 'report' in st.session_state:
                report = st.session_state.report
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("#### Baseline")
                    baseline_metrics = report["test_summary"]["baseline"]
                    st.metric("Total", baseline_metrics["total"])
                    st.metric("Passed", baseline_metrics["passed"])
                    st.metric("Failed", baseline_metrics["failed"])
                
                with col2:
                    st.markdown("#### Current")
                    current_metrics = report["test_summary"]["current"]
                    baseline_metrics = report["test_summary"]["baseline"]
                    st.metric("Total", current_metrics["total"])
                    st.metric("Passed", current_metrics["passed"], 
                             delta=current_metrics["passed"] - baseline_metrics["passed"])
                    st.metric("Failed", current_metrics["failed"], 
                             delta=current_metrics["failed"] - baseline_metrics["failed"], 
                             delta_color="inverse")
            else:
                st.info("Run analysis to see report comparison")
        
        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("👁️ View Baseline Report", use_container_width=True):
                st.session_state['show_baseline'] = not st.session_state.get('show_baseline', False)
        
        with col2:
            if st.button("👁️ View Current Report", use_container_width=True):
                st.session_state['show_current'] = not st.session_state.get('show_current', False)
        
        if st.session_state.get('show_baseline', False):
            st.markdown("#### Baseline Report")
            try:
                baseline_data = json.loads(baseline_content)
                st.json(baseline_data)
            except:
                st.code(baseline_content, language="json")
        
        if st.session_state.get('show_current', False):
            st.markdown("#### Current Report")
            try:
                current_data = json.loads(current_content)
                st.json(current_data)
            except:
                st.code(current_content, language="json")
    else:
        st.info("Run an AI analysis first to view test reports here.")


with tab6:
     st.header("📜 History")
    
    # --- Folder-style History Tab ---
     st.markdown("View all previous analysis results, commits, baseline tests, and current test reports. Each analysis is saved as a folder with expandable sections.")

    # --- History logic: Save new analysis ---
     history = st.session_state.get('history', [])
    # If a new report exists and not already in history, append it
     if 'report' in st.session_state and st.session_state.report:
        report = st.session_state.report
        # Build history entry from report and other session state
        new_entry = {
            'timestamp': st.session_state.analysis_timestamp or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'title': 'Analysis',
            'executive_summary': report.get('executive_summary', ''),
            'test_run_summary': report.get('test_run_summary', ''),
            'commits_analyzed': report.get('commits_analyzed', ''),
            'key_findings': report.get('key_findings', []),
            'repo_name': st.session_state.get('dataset_name', ''),
            'commit_range': f"{st.session_state.get('baseline_ref', '')} → {st.session_state.get('current_ref', '')}",
            'commits': st.session_state.get('commits', []),
            'test_reports_preview': [report.get('test_summary', {})],
            'detailed_file_changes': report.get('detailed_file_changes', []),
            # Save commit inference results if present
            'commit_inference': st.session_state.get('inference_results', []),
        }
        # Only append if not already present (avoid duplicates)
        if not history or new_entry['timestamp'] != history[-1].get('timestamp'):
            history.append(new_entry)
            st.session_state['history'] = history
            # Save to file for persistence
            history_file = Path("history.json")
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, default=str)

    # Load history from file if session empty
     if not history:
        history_file = Path("history.json")
        if history_file.exists():
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            st.session_state['history'] = history

     if history:
        delete_index = None
        for idx, entry in enumerate(history[::-1]):  # Show newest first
            real_idx = len(history) - 1 - idx
            col_exp, col_del = st.columns([12, 1])
            with col_exp:
                expander = st.expander(f"🗂️ {entry.get('timestamp', 'Unknown')} — {entry.get('title', 'Analysis')}", expanded=False)
            with col_del:
                if st.button("🗑️", key=f"delete_{entry.get('timestamp','')}", help="Delete this analysis"):
                    delete_index = real_idx
            with expander:
                # Analysis Results
                st.markdown("### 📋 Analysis Results")
                st.markdown(f"**Generated:** {entry.get('timestamp', 'Unknown')}")
                st.markdown(f"**Executive Summary:**")
                st.markdown(entry.get('executive_summary', ''))
                st.markdown(entry.get('test_run_summary', ''))
                if entry.get('key_findings', []):
                    for finding in entry.get('key_findings', []):
                        st.markdown(f"- {finding}")
                st.markdown("<hr style='border: none; border-top: 1px solid #444; margin: 8px 0;'>", unsafe_allow_html=True)

                    # Commit Inference Results
                if entry.get('commit_inference', []):
                        st.markdown("### 🧠 Commit Inference Results")
                        for idx, item in enumerate(entry['commit_inference']):
                            pair, inference_text = item
                            older = pair.get('older', {})
                            newer = pair.get('newer', {})
                            label = f"**{older.get('sha','')[:8]}** → **{newer.get('sha','')[:8]}**  ·  {newer.get('message','')[:70]}"
                            with st.expander(label, expanded=(idx == 0)):
                                st.markdown(inference_text)
                        st.markdown("<hr style='border: none; border-top: 1px solid #444; margin: 8px 0;'>", unsafe_allow_html=True)
                # Commit History
                st.markdown("### 📦 Commit History")
                st.markdown(f"**Repository:** {repo_url.split('/')[-1]} | **Commits:** {start_commit} to {end_commit} ({len(entry.get('commits', []))} total)")
                st.markdown(f"**Commits:** {entry.get('commit_range', '')}")
                for commit in entry.get('commits', []):
                    sha = commit.get('sha', '')[:8]
                    message = commit.get('message', '')
                    author = commit.get('author', {}).get('name', '')
                    date = commit.get('date', '')
                    st.markdown(f"<div style='border-radius:6px;background:#23272f;padding:12px;margin-bottom:8px;'>", unsafe_allow_html=True)
                    st.markdown(f"<b>{sha}</b> — {message[:80]}", unsafe_allow_html=True)
                    st.markdown(f"<b>Author:</b> {author}", unsafe_allow_html=True)
                    st.markdown(f"<b>Date:</b> {date}", unsafe_allow_html=True)
                    st.markdown(f"<b>Message:</b> {message}", unsafe_allow_html=True)
                    if 'changed_files' in commit and commit['changed_files']:
                        st.markdown(f"<b>Files Changed:</b> {len(commit['changed_files'])}", unsafe_allow_html=True)
                        for file in commit['changed_files'][:5]:
                            st.markdown(f"<span style='background:#212d21;color:#4ade80;padding:4px 8px;border-radius:4px;margin-right:4px;'> {file['file']} </span>", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("<hr style='border: none; border-top: 1px solid #444; margin: 8px 0;'>", unsafe_allow_html=True)

                # Test Reports
                st.markdown("### 📊 Test Reports")
                st.markdown(f"#### Test Reports Preview")
                for report_preview in entry.get('test_reports_preview', []):
                    st.json(report_preview)
                st.markdown("<hr style='border: none; border-top: 1px solid #444; margin: 8px 0;'>", unsafe_allow_html=True)

                # Code Changes
                st.markdown("### 📝 Code Changes")
                for file_change in entry.get("detailed_file_changes", [])[:10]:
                    st.markdown(f"#### 📄 {file_change['file_path']}")
                    st.caption(file_change['summary'])
                    for line_change in file_change.get("line_changes", [])[:5]:
                        if line_change['change_type'] == 'modified':
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown(f"<span style='color:#e74c3c;font-weight:bold;'>Line {line_change['line_number']} (Before)</span>", unsafe_allow_html=True)
                                st.markdown(f"<pre style='background:#2c2c2c;color:#e74c3c;border-radius:4px;padding:8px;'>{line_change.get('old_content', '')}</pre>", unsafe_allow_html=True)
                            with col2:
                                st.markdown(f"<span style='color:#27ae60;font-weight:bold;'>Line {line_change['line_number']} (After)</span>", unsafe_allow_html=True)
                                st.markdown(f"<pre style='background:#2c2c2c;color:#27ae60;border-radius:4px;padding:8px;'>{line_change.get('new_content', '')}</pre>", unsafe_allow_html=True)
                st.markdown("<hr style='border: none; border-top: 1px solid #444; margin: 8px 0;'>", unsafe_allow_html=True)

        if delete_index is not None:
            del history[delete_index]
            st.session_state['history'] = history
            history_file = Path("history.json")
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, default=str)
            st.experimental_rerun()

        if delete_index is not None:
            del history[delete_index]
            st.session_state['history'] = history
            history_file = Path("history.json")
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, default=str)
            st.experimental_rerun()

        # Export Report section (unchanged)
        if 'report' in st.session_state:
            report = st.session_state.report
            st.subheader("📥 Export Report")
            report_json = json.dumps(report, indent=2, default=str)
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📥 Download JSON",
                    data=report_json,
                    file_name=f"analysis_{st.session_state.analysis_timestamp.replace(' ', '_').replace(':', '-')}.json" if st.session_state.analysis_timestamp else "analysis.json",
                    mime="application/json",
                    use_container_width=True
                )
            with col2:
                markdown_summary = f"""# QA Intelligence Report
Generated: {st.session_state.analysis_timestamp}

{report["executive_summary"]}

## Key Findings
{chr(10).join(f"- {f}" for f in report.get("key_findings", []))}
"""
                st.download_button(
                    "📄 Download Markdown",
                    data=markdown_summary,
                    file_name=f"summary_{st.session_state.analysis_timestamp.replace(' ', '_').replace(':', '-')}.md" if st.session_state.analysis_timestamp else "summary.md",
                    mime="text/markdown",
                    use_container_width=True
                )
        else:
            st.info("Run analysis first to see history and export options")
     else:
        st.info("No history found. Run analysis to save results.")
