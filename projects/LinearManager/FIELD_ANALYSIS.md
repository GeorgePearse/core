# Linear API Field Analysis

## Current Implementation Status

### Currently Supported Fields

Based on analysis of `src/linear_manager/sync.py`:

#### For Issue Creation (`IssueCreateInput`)
| Field | YAML Key | Type | Required | Status |
|-------|----------|------|----------|--------|
| `teamId` | `team_key` | String | ✅ Yes | ✅ Implemented |
| `title` | `title` | String | ✅ Yes | ✅ Implemented |
| `description` | `description` | String | ❌ No | ✅ Implemented (defaults to "") |
| `priority` | `priority` | Int (0-4) | ❌ No | ✅ Implemented |
| `labelIds` | `labels` | [String] | ❌ No | ✅ Implemented |
| `assigneeId` | `assignee_email` | String | ❌ No | ✅ Implemented |
| `stateId` | `state` | String | ❌ No | ✅ Implemented |

#### For Issue Updates (`IssueUpdateInput`)
- Same fields as create (except `teamId` which can't be changed)
- Issue identified by `identifier` field in YAML

#### Special Handling
- `complete: true` flag maps to the team's "done" state when `--mark-done` is passed
- Labels are resolved by name → ID lookup via team context
- States are resolved by name → ID lookup via team context
- Assignees are resolved by email → user ID lookup via team context

### Code References
- YAML parsing: `src/linear_manager/sync.py:140-219`
- Issue creation: `src/linear_manager/sync.py:113-137`
- Issue updates: `src/linear_manager/sync.py:88-111`
- Team context resolution: `src/linear_manager/sync.py:342-386`

---

## Likely Missing Fields

Based on Linear's feature set and common issue tracking needs:

### High Priority Missing Fields

#### 1. **Cycle Management** (`cycleId`)
- **Why Critical**: Cycles are Linear's core planning unit (sprints/iterations)
- **Current Gap**: Issues can't be assigned to cycles via YAML
- **Proposed YAML**:
  ```yaml
  issues:
    - title: Example
      cycle: "Sprint 23"  # or cycle_id: "cycle_uuid"
  ```
- **Implementation**: Add cycle lookup to `TeamContext` similar to states/labels

#### 2. **Project Assignment** (`projectId`)
- **Why Critical**: Projects organize work across multiple cycles
- **Current Gap**: Can't link issues to projects
- **Proposed YAML**:
  ```yaml
  issues:
    - title: Example
      project: "Q1 Redesign"  # or project_id: "project_uuid"
  ```
- **Implementation**: Add project lookup to `TeamContext`

#### 3. **Parent/Sub-issue Relationships** (`parentId`)
- **Why Important**: Essential for task breakdown and epic management
- **Current Gap**: Can't create hierarchies
- **Proposed YAML**:
  ```yaml
  issues:
    - identifier: ENG-100
      title: Epic
    - title: Sub-task
      parent: ENG-100  # or parent_id: "issue_uuid"
  ```
- **Implementation**: Resolve identifier → ID similar to updates

#### 4. **Estimates** (`estimate`)
- **Why Important**: Core to agile planning and velocity tracking
- **Current Gap**: Can't set story points/estimates
- **Proposed YAML**:
  ```yaml
  issues:
    - title: Example
      estimate: 3  # story points
  ```
- **Implementation**: Simple integer field

#### 5. **Due Dates** (`dueDate`)
- **Why Important**: Critical for deadline tracking
- **Current Gap**: Can't set deadlines
- **Proposed YAML**:
  ```yaml
  issues:
    - title: Example
      due_date: "2025-10-20"  # ISO date format
  ```
- **Implementation**: Parse date string, validate format

### Medium Priority Missing Fields

#### 6. **Subscribers** (`subscriberIds`)
- **Why Useful**: Keep stakeholders informed without assignment
- **Proposed YAML**:
  ```yaml
  issues:
    - title: Example
      subscribers: ["user1@example.com", "user2@example.com"]
  ```

#### 7. **Start Date** (`startedAt`)
- **Why Useful**: Track when work actually begins
- **Proposed YAML**:
  ```yaml
  issues:
    - title: Example
      started_at: "2025-10-14"
  ```

#### 8. **Template Selection** (`templateId`)
- **Why Useful**: Apply pre-defined issue templates
- **Proposed YAML**:
  ```yaml
  issues:
    - title: Example
      template: "Bug Report Template"
  ```

---

## Verification Plan

### Step 1: Run Introspection Script
```bash
export LINEAR_API_KEY="your_key_here"
python scripts/introspect_schema.py
```

This will generate:
1. Console output showing required vs optional fields
2. `linear_schema_introspection.json` with full schema

### Step 2: Compare Against Current Implementation
Review the introspection output to confirm:
- [ ] `teamId` and `title` are the only required fields for creation
- [ ] All other fields are truly optional
- [ ] Field names match what we're using (e.g., `assigneeId` not `assignee`)

### Step 3: Identify Missing Fields
From the introspection output, check for these fields:
- [ ] `cycleId`
- [ ] `projectId`
- [ ] `parentId`
- [ ] `estimate`
- [ ] `dueDate`
- [ ] `subscriberIds`
- [ ] `startedAt`
- [ ] `templateId`
- [ ] Any other fields we haven't considered

### Step 4: Test Current Implementation
```bash
# Create a test YAML with all currently supported fields
cat > test_manifest.yaml <<'EOF'
defaults:
  team_key: ENG
  state: Triage
  labels: ["Test"]
  assignee_email: test@example.com
  priority: 2

issues:
  - title: Test Create All Fields
    description: Testing all supported fields
    priority: 1
    labels: ["Bug", "P0"]
EOF

# Dry run to validate
linear-manager test_manifest.yaml --dry-run

# Actually create (if dry-run looks good)
linear-manager test_manifest.yaml
```

---

## Recommendations

### Immediate Actions
1. ✅ Run introspection script to confirm field requirements
2. Add support for critical fields in this order:
   - `cycleId` - Most impactful for Linear workflows
   - `projectId` - Also core to Linear's model
   - `estimate` - Essential for agile teams
   - `dueDate` - Common need
   - `parentId` - For hierarchies

### Implementation Notes

#### For Cycle/Project Support
Need to extend `TeamContext` with new lookups:
```python
@dataclass
class TeamContext:
    # ... existing fields ...
    cycles: dict[str, str]  # name -> id
    projects: dict[str, str]  # name -> id
    available_cycles: list[str]
    available_projects: list[str]
```

Update `TEAM_CONTEXT_QUERY` in `src/linear_manager/sync.py:425` to fetch cycles and projects.

#### For Date Fields
Add date parsing and validation:
```python
from datetime import datetime

def _parse_iso_date(value: Any, field_name: str) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        try:
            # Validate ISO format
            datetime.fromisoformat(value)
            return value
        except ValueError as exc:
            raise RuntimeError(f"{field_name} must be ISO date format (YYYY-MM-DD)") from exc
    raise RuntimeError(f"{field_name} must be a string")
```

#### Backward Compatibility
All new fields should be optional with defaults to maintain backward compatibility with existing YAML files.

---

## Next Steps

1. Get LINEAR_API_KEY access
2. Run introspection script
3. Review output and update this document with actual field definitions
4. Prioritize and implement missing fields based on user needs
5. Update README.md with new field documentation
6. Add tests for new fields
