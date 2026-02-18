"""Classify code changes."""
import re
from typing import List, Tuple
from ..config import ChangeType, FileChange, LocatorChange


class ChangeClassifier:
    """Classify file changes by type."""
    
    # Pattern mappings
    PATTERNS = {
        ChangeType.LOCATOR: [
            r".*locators?\.properties$",
            r".*\/repository\/.*\.properties$",
        ],
        ChangeType.FEATURE: [
            r".*\.feature$",
        ],
        ChangeType.STEP_DEFINITION: [
            r".*stepDefinitions?\/.*\.java$",
            r".*steps?\/.*\.java$",
        ],
        ChangeType.PAGE_OBJECT: [
            r".*pageObjects?\/.*\.java$",
            r".*pages?\/.*\.java$",
        ],
        ChangeType.CONFIG: [
            r"pom\.xml$",
            r"testng\.xml$",
            r".*config\.properties$",
            r".*\.yml$",
            r".*\.yaml$",
        ],
        ChangeType.UTILITY: [
            r".*utilities?\/.*\.java$",
            r".*utils?\/.*\.java$",
        ],
    }
    
    @classmethod
    def classify_file(cls, file_path: str) -> ChangeType:
        """Classify a single file."""
        for change_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, file_path, re.IGNORECASE):
                    return change_type
        return ChangeType.OTHER
    
    @classmethod
    def classify_changes(
        cls, 
        changes: List[Tuple[str, str, int, int]]
    ) -> List[FileChange]:
        """Classify all file changes."""
        classified = []
        for path, diff, additions, deletions in changes:
            change_type = cls.classify_file(path)
            classified.append(FileChange(
                path=path,
                change_type=change_type,
                additions=additions,
                deletions=deletions,
                diff=diff
            ))
        return classified
    
    @staticmethod
    def extract_locator_changes(diff: str) -> List[LocatorChange]:
        """Extract specific locator key changes from properties diff."""
        changes = []
        
        # Parse diff line by line
        lines = diff.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('-') and not line.startswith('---'):
                # Removed or changed line
                key_match = re.match(r'^-\s*([^=\s]+)\s*=\s*(.*)$', line)
                if key_match:
                    key = key_match.group(1)
                    old_value = key_match.group(2)
                    
                    # Check if next line is addition (modification)
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        if next_line.startswith('+'):
                            new_key_match = re.match(r'^\+\s*([^=\s]+)\s*=\s*(.*)$', next_line)
                            if new_key_match and new_key_match.group(1) == key:
                                new_value = new_key_match.group(2)
                                changes.append(LocatorChange(
                                    key=key,
                                    old_value=old_value,
                                    new_value=new_value,
                                    change_type="modified"
                                ))
                                continue
                    
                    # Pure removal
                    changes.append(LocatorChange(
                        key=key,
                        old_value=old_value,
                        new_value=None,
                        change_type="removed"
                    ))
                    
            elif line.startswith('+') and not line.startswith('+++'):
                # Added line (not part of modification)
                key_match = re.match(r'^\+\s*([^=\s]+)\s*=\s*(.*)$', line)
                if key_match:
                    key = key_match.group(1)
                    new_value = key_match.group(2)
                    
                    # Check if it's not already captured as modification
                    if not any(c.key == key and c.change_type == "modified" for c in changes):
                        changes.append(LocatorChange(
                            key=key,
                            old_value=None,
                            new_value=new_value,
                            change_type="added"
                        ))
        
        return changes