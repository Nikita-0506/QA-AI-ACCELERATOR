"""Detailed diff analysis with line-by-line changes."""
import re
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class LineChange:
    """Represents a single line change."""
    line_number: int
    change_type: str  # "added", "removed", "modified"
    old_content: str = None
    new_content: str = None
    context_before: List[str] = None
    context_after: List[str] = None


@dataclass
class FileChangeDetail:
    """Detailed changes for a single file."""
    file_path: str
    change_type: str  # from ChangeType enum
    line_changes: List[LineChange]
    summary: str


class DiffAnalyzer:
    """Analyze git diffs in detail."""
    
    @staticmethod
    def parse_unified_diff(diff_text: str, file_path: str) -> FileChangeDetail:
        """Parse unified diff format and extract line-by-line changes."""
        if not diff_text:
            return FileChangeDetail(
                file_path=file_path,
                change_type="unknown",
                line_changes=[],
                summary="No diff available"
            )
        
        lines = diff_text.split('\n')
        line_changes = []
        
        current_old_line = 0
        current_new_line = 0
        context_buffer = []
        
        # Track consecutive changes for "modified" detection
        pending_removal = None
        
        for i, line in enumerate(lines):
            # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
            hunk_match = re.match(r'^@@\s+-(\d+),?\d*\s+\+(\d+),?\d*\s+@@', line)
            if hunk_match:
                current_old_line = int(hunk_match.group(1))
                current_new_line = int(hunk_match.group(2))
                continue
            
            # Skip diff headers
            if line.startswith('---') or line.startswith('+++') or line.startswith('diff --git'):
                continue
            
            # Context line (unchanged)
            if line.startswith(' ') or (not line.startswith('+') and not line.startswith('-')):
                context_buffer.append(line[1:] if line.startswith(' ') else line)
                if len(context_buffer) > 3:  # Keep only last 3 context lines
                    context_buffer.pop(0)
                current_old_line += 1
                current_new_line += 1
                
                # If we had a pending removal, it wasn't modified
                if pending_removal:
                    line_changes.append(pending_removal)
                    pending_removal = None
                continue
            
            # Removed line
            if line.startswith('-'):
                content = line[1:]
                # Store as pending - might be part of a modification
                pending_removal = LineChange(
                    line_number=current_old_line,
                    change_type="removed",
                    old_content=content,
                    new_content=None,
                    context_before=context_buffer.copy()
                )
                current_old_line += 1
                continue
            
            # Added line
            if line.startswith('+'):
                content = line[1:]
                
                # Check if this is a modification (had a pending removal)
                if pending_removal and DiffAnalyzer._are_lines_related(pending_removal.old_content, content):
                    # This is a modification
                    line_changes.append(LineChange(
                        line_number=pending_removal.line_number,
                        change_type="modified",
                        old_content=pending_removal.old_content,
                        new_content=content,
                        context_before=pending_removal.context_before
                    ))
                    pending_removal = None
                else:
                    # Pure addition or pending removal was separate
                    if pending_removal:
                        line_changes.append(pending_removal)
                        pending_removal = None
                    
                    line_changes.append(LineChange(
                        line_number=current_new_line,
                        change_type="added",
                        old_content=None,
                        new_content=content,
                        context_before=context_buffer.copy()
                    ))
                
                current_new_line += 1
                continue
        
        # Don't forget the last pending removal
        if pending_removal:
            line_changes.append(pending_removal)
        
        summary = DiffAnalyzer._generate_summary(file_path, line_changes)
        
        return FileChangeDetail(
            file_path=file_path,
            change_type=DiffAnalyzer._classify_change_type(file_path),
            line_changes=line_changes,
            summary=summary
        )
    
    @staticmethod
    def _are_lines_related(old_line: str, new_line: str) -> bool:
        """Determine if two lines are modifications of each other."""
        # Simple heuristic: if they share some significant content
        old_words = set(old_line.split())
        new_words = set(new_line.split())
        
        if not old_words or not new_words:
            return False
        
        # Calculate similarity
        common = old_words.intersection(new_words)
        similarity = len(common) / max(len(old_words), len(new_words))
        
        return similarity > 0.3  # More than 30% overlap
    
    @staticmethod
    def _classify_change_type(file_path: str) -> str:
        """Quick classification of file type."""
        if file_path.endswith('.feature'):
            return 'feature'
        elif 'stepDefinition' in file_path or 'Steps.java' in file_path:
            return 'step_definition'
        elif 'pageObject' in file_path or 'Page.java' in file_path:
            return 'page_object'
        elif 'locators.properties' in file_path or 'locator' in file_path.lower():
            return 'locator'
        return 'other'
    
    @staticmethod
    def _generate_summary(file_path: str, line_changes: List[LineChange]) -> str:
        """Generate human-readable summary of changes."""
        if not line_changes:
            return "No changes detected"
        
        added = sum(1 for c in line_changes if c.change_type == "added")
        removed = sum(1 for c in line_changes if c.change_type == "removed")
        modified = sum(1 for c in line_changes if c.change_type == "modified")
        
        parts = []
        if added:
            parts.append(f"{added} line(s) added")
        if removed:
            parts.append(f"{removed} line(s) removed")
        if modified:
            parts.append(f"{modified} line(s) modified")
        
        return f"{file_path}: {', '.join(parts)}"
    
    @staticmethod
    def extract_key_changes(file_changes: List[FileChangeDetail]) -> Dict[str, Any]:
        """Extract the most important changes for LLM analysis."""
        key_changes = {
            "feature_changes": [],
            "step_definition_changes": [],
            "test_data_changes": [],
            "locator_changes": []
        }
        
        for file_detail in file_changes:
            if file_detail.change_type == "feature":
                key_changes["feature_changes"].extend([
                    {
                        "file": file_detail.file_path,
                        "line": lc.line_number,
                        "type": lc.change_type,
                        "old": lc.old_content,
                        "new": lc.new_content
                    }
                    for lc in file_detail.line_changes
                    if lc.change_type != "context"
                ])
            
            elif file_detail.change_type == "step_definition":
                # Look for important changes in step definitions
                for lc in file_detail.line_changes:
                    if any(keyword in (lc.new_content or lc.old_content or "").lower() 
                           for keyword in ["password", "username", "login", "assert", "wait", "click"]):
                        key_changes["step_definition_changes"].append({
                            "file": file_detail.file_path,
                            "line": lc.line_number,
                            "type": lc.change_type,
                            "old": lc.old_content,
                            "new": lc.new_content
                        })
            
            elif file_detail.change_type == "locator":
                key_changes["locator_changes"].extend([
                    {
                        "file": file_detail.file_path,
                        "line": lc.line_number,
                        "type": lc.change_type,
                        "old": lc.old_content,
                        "new": lc.new_content
                    }
                    for lc in file_detail.line_changes
                ])
        
        return key_changes