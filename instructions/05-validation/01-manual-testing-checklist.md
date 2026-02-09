# Manual End-to-End Testing Checklist

## Overview

This checklist validates the complete Narrated Financials pipeline including:
- Excel Schema Adapter (multi-format support)
- Semantic Matcher (synonym and similarity matching)
- Data extraction and transformation

---

## Pre-requisites

### Environment Setup
```bash
cd ./repos/projects/tpc_backend
source venv/bin/activate  # or your virtual environment

# Verify Python path
python -c "import sys; print(sys.path[:3])"
```

### Required Files
```
narrated_financials/
├── tools/docx_tables/
│   ├── schema_adapter.py      # Excel format detection and transformation
│   └── semantic_matcher.py    # Similarity matching with synonyms
├── models/
│   └── synonym.py             # Database model for synonyms
├── api/
│   └── synonym_endpoints.py   # REST API for synonym management
└── data/tpc-working-folder/
    └── Erroneous Entities/    # Test data (16 entities)
```

---

## Test 1: Schema Adapter - Format Detection

### 1.1 Verify Available Schema Patterns

```python
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from narrated_financials.tools.docx_tables.schema_adapter import SCHEMA_PATTERNS

print("Available Schema Patterns:")
print("=" * 60)
for schema_id, pattern in SCHEMA_PATTERNS.items():
    print(f"\nSchema: {schema_id}")
    print(f"  Name: {pattern.get('name')}")
    print(f"  Detection: {pattern.get('detection')}")
    print(f"  Source Sheet: {pattern.get('source_sheet', 'pattern-based')}")
    print(f"  Header Row: {pattern.get('header_row')}")
EOF
```

**Expected Output:**
| Schema ID | Name | Detection Pattern |
|-----------|------|-------------------|
| `fccs_standard` | FCCS Standard Export | sheets: `Mapping_AI`, columns: `Class`, `Value` |
| `oracle_trial_balance` | Oracle Trial Balance Export | sheets: `^(TB\|Trial Balance)(\s+\d{4})?$` |
| `oracle_profit_loss` | Oracle Profit & Loss Export | sheets: `^(PL\|Profit & Loss\|P&L)(\s+\d{4})?$` |

**[ ] PASS** - All 3 patterns displayed correctly

---

### 1.2 Test Format Detection on Sample Files

```python
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from pathlib import Path
from narrated_financials.tools.docx_tables.schema_adapter import SchemaDetector

detector = SchemaDetector()

test_files = [
    ("FCCS Standard", "narrated_financials/data/tpc-working-folder/Erroneous Entities/6.Kendilo Pte. Ltd/codes.xlsx"),
    ("Oracle TB", "narrated_financials/data/tpc-working-folder/Erroneous Entities/30. IMC Resources Gold Holdings Pte Ltd/IMCRG AFS FY2024 working.xlsx"),
    ("Oracle TB 2024", "narrated_financials/data/tpc-working-folder/Erroneous Entities/31. IMC Resources Holdings Pte Ltd/IMC Resources Holdings Pte Ltd FY2024 AFS working.xlsx"),
]

print("Format Detection Results:")
print("=" * 80)
for name, filepath in test_files:
    schema_id = detector.detect(Path(filepath))
    status = "✓" if schema_id else "✗"
    print(f"{status} {name}: {schema_id}")
EOF
```

**Expected Output:**
```
✓ FCCS Standard: fccs_standard
✓ Oracle TB: oracle_trial_balance
✓ Oracle TB 2024: oracle_trial_balance
```

**[ ] PASS** - All 3 files detected correctly

---

### 1.3 Test Data Extraction

```python
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from pathlib import Path
from narrated_financials.tools.docx_tables.schema_adapter import SchemaAdapter, SchemaDetector

detector = SchemaDetector()
filepath = Path("narrated_financials/data/tpc-working-folder/Erroneous Entities/30. IMC Resources Gold Holdings Pte Ltd/IMCRG AFS FY2024 working.xlsx")

schema_id = detector.detect(filepath)
adapter = SchemaAdapter(schema_id)
items = adapter.transform(filepath)

print(f"Extracted {len(items)} line items")
print("\nSample (first 5):")
print("-" * 80)
for item in items[:5]:
    print(f"Row {item.row_number}: {item.afs_class}")
    print(f"  Account: {item.account_code} | Value: {item.value}")
EOF
```

**Expected Output:**
- `Extracted 28 line items`
- Sample shows AFS Class, Account Code, and Value for each row

**Verify:**
- [ ] Line items count > 0
- [ ] AFS Class is properly extracted (e.g., "Financial asset, FVOCI")
- [ ] Account codes are extracted (e.g., "11601002")
- [ ] Values are Decimal type (not strings)
- [ ] Row numbers are correct (starting from 8 for Oracle TB)

**[ ] PASS** - Data extraction working correctly

---

## Test 2: All Entities Validation

### 2.1 Load All 16 Erroneous Entities

```python
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from pathlib import Path
from decimal import Decimal
from narrated_financials.tools.docx_tables.schema_adapter import ExcelDataLoader

loader = ExcelDataLoader()
base = Path("narrated_financials/data/tpc-working-folder/Erroneous Entities")

print("Entity Validation Results:")
print("=" * 100)
print(f"{'Entity':<55} {'Items':>8} {'Classes':>8} {'Zeros':>6} {'Status':>10}")
print("-" * 100)

success = 0
failed = 0
total_items = 0

for entity_dir in sorted(base.iterdir()):
    if not entity_dir.is_dir():
        continue
    try:
        items = loader.load_entity_data(entity_dir)
        unique_classes = len(set(i.afs_class for i in items))
        zero_count = sum(1 for i in items if i.value == Decimal("0"))
        print(f"{entity_dir.name:<55} {len(items):>8} {unique_classes:>8} {zero_count:>6} {'✓ PASS':>10}")
        success += 1
        total_items += len(items)
    except Exception as e:
        print(f"{entity_dir.name:<55} {0:>8} {0:>8} {0:>6} {'✗ FAIL':>10}")
        print(f"  ERROR: {e}")
        failed += 1

print("-" * 100)
print(f"{'TOTAL':<55} {total_items:>8} {'':>8} {'':>6} {success}/{success+failed}")
EOF
```

**Expected Output:**
| Entity | Items | Classes | Zeros | Status |
|--------|-------|---------|-------|--------|
| 11.Meridian Navigation | 159 | 48 | 8 | ✓ PASS |
| ... | ... | ... | ... | ... |
| **TOTAL** | **1922** | | | **16/16** |

**Verify:**
- [ ] All 16 entities show ✓ PASS
- [ ] Total items ≈ 1922
- [ ] Zeros are preserved (not skipped)

**[ ] PASS** - All entities processed successfully

---

## Test 3: Semantic Matcher - Synonym Tests

### 3.1 Verify Synonym Loading

```python
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from narrated_financials.tools.docx_tables.semantic_matcher import SemanticMatcher

matcher = SemanticMatcher()
synonyms = matcher.get_all_synonyms()

print(f"Loaded {len(synonyms)} synonyms:")
print("-" * 40)
for source, target in sorted(synonyms.items()):
    print(f"  '{source}' → '{target}'")
EOF
```

**Expected Synonyms (minimum):**
| Source | Target | Category |
|--------|--------|----------|
| translation | exchange | Currency/FX |
| forex | exchange | Currency/FX |
| fx | exchange | Currency/FX |
| realised | realized | UK/US Spelling |
| unrealised | unrealized | UK/US Spelling |
| capitalised | capitalized | UK/US Spelling |
| recognised | recognized | UK/US Spelling |
| organisation | organization | UK/US Spelling |
| labour | labor | UK/US Spelling |
| favour | favor | UK/US Spelling |

**[ ] PASS** - At least 10 synonyms loaded

---

### 3.2 Test Synonym Matching

```python
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from narrated_financials.tools.docx_tables.semantic_matcher import SemanticMatcher

matcher = SemanticMatcher()

test_cases = [
    # (source, target, expected_min_score, description)
    ("translation", "exchange", 0.85, "Synonym: translation→exchange"),
    ("realised", "realized", 0.85, "Synonym: UK/US spelling"),
    ("capitalised", "capitalized", 0.85, "Synonym: UK/US spelling"),
    ("forex", "exchange", 0.85, "Synonym: forex→exchange"),
    ("Net currency translation losses", "Net currency exchange losses", 0.75, "Synonym in phrase"),
]

print("Synonym Matching Tests:")
print("=" * 90)
print(f"{'Source':<35} {'Target':<35} {'Score':>8} {'Status':>8}")
print("-" * 90)

passed = 0
for source, target, min_score, desc in test_cases:
    score = matcher.combined_similarity(source, target)
    status = "✓ PASS" if score >= min_score else "✗ FAIL"
    print(f"{source:<35} {target:<35} {score:>8.2f} {status:>8}")
    if score >= min_score:
        passed += 1

print("-" * 90)
print(f"Results: {passed}/{len(test_cases)} passed")
EOF
```

**Expected Output:**
- All scores ≥ 0.85 for direct synonyms
- All scores ≥ 0.75 for phrase matches

**[ ] PASS** - All 5 tests passed

---

### 3.3 Test Semantic Similarity

```python
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from narrated_financials.tools.docx_tables.semantic_matcher import SemanticMatcher

matcher = SemanticMatcher()

test_cases = [
    ("Financial asset, FVOCI", "Financial assets at fair value through OCI", 0.70),
    ("Other receivable", "Other receivables", 0.80),
    ("Accrued expenses", "Accrued expense", 0.80),
    ("Investment in - subsidiary", "Investment in subsidiary", 0.85),
    ("Trade payable", "Trade payables", 0.80),
    ("Cash and cash equivalents", "Cash and bank balances", 0.60),
]

print("Semantic Similarity Tests:")
print("=" * 90)
print(f"{'Source':<40} {'Target':<35} {'Score':>8} {'Status':>8}")
print("-" * 90)

passed = 0
for source, target, min_score in test_cases:
    score = matcher.combined_similarity(source, target)
    status = "✓ PASS" if score >= min_score else "✗ FAIL"
    print(f"{source:<40} {target:<35} {score:>8.2f} {status:>8}")
    if score >= min_score:
        passed += 1

print("-" * 90)
print(f"Results: {passed}/{len(test_cases)} passed")
EOF
```

**[ ] PASS** - All 6 tests passed (or at least 5/6)

---

## Test 4: API Endpoint Validation (Optional - Requires Django)

### 4.1 Start Django Shell

```bash
cd ./repos/projects/tpc_backend
python manage.py shell
```

### 4.2 Test Synonym Model

```python
from narrated_financials.models.synonym import (
    FinancialSynonym,
    SynonymCategory,
    SynonymStatus,
    get_active_synonyms
)

# Create test synonym
synonym = FinancialSynonym.objects.create(
    source_term="test_source",
    target_term="test_target",
    category=SynonymCategory.CUSTOM,
    status=SynonymStatus.ACTIVE,
    description="Test synonym"
)
print(f"Created: {synonym}")

# Verify it's returned by get_active_synonyms
synonyms = get_active_synonyms()
assert "test_source" in synonyms
print(f"✓ Synonym found in active synonyms")

# Cleanup
synonym.delete()
print("✓ Test synonym deleted")
```

**[ ] PASS** - Model CRUD operations work

---

## Test 5: Edge Cases

### 5.1 Empty Values Handling

```python
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from decimal import Decimal
from pathlib import Path
from narrated_financials.tools.docx_tables.schema_adapter import ExcelDataLoader

loader = ExcelDataLoader()
entity = Path("narrated_financials/data/tpc-working-folder/Erroneous Entities/5.IMC Shipping Co. Pte. Ltd")

items = loader.load_entity_data(entity)

# Check zero values are preserved
zeros = [i for i in items if i.value == Decimal("0")]
print(f"Total items: {len(items)}")
print(f"Zero values preserved: {len(zeros)}")
print(f"\nSample zero value items:")
for item in zeros[:3]:
    print(f"  - {item.afs_class}: {item.value}")
EOF
```

**Expected:**
- Zero values should be preserved (not skipped)
- IMC Shipping has ~242 zero value items

**[ ] PASS** - Zero values preserved

---

### 5.2 AFS Suffix Stripping

```python
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from narrated_financials.tools.docx_tables.schema_adapter import SchemaAdapter

adapter = SchemaAdapter("oracle_trial_balance")

# Test suffix stripping
test_values = [
    "Financial asset, FVOCI - 0",
    "Other receivable - intermediate hold co",
    "Trade payable - immediate hold co",
    "Cash and cash equivalents - 0",
]

print("AFS Suffix Stripping Tests:")
print("-" * 60)
for value in test_values:
    stripped = adapter._apply_transform(value, "strip_afs_suffix")
    print(f"'{value}'")
    print(f"  → '{stripped}'")
    print()
EOF
```

**Expected:**
- Suffixes like ` - 0`, ` - intermediate hold co` should be removed

**[ ] PASS** - Suffixes stripped correctly

---

## Test 6: Full Pipeline Integration

### 6.1 End-to-End with Logging

```bash
python3 << 'EOF'
import sys
import logging

# Enable detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
)

sys.path.insert(0, '.')
from pathlib import Path
from narrated_financials.tools.docx_tables.schema_adapter import ExcelDataLoader

loader = ExcelDataLoader()
entity = Path("narrated_financials/data/tpc-working-folder/Erroneous Entities/30. IMC Resources Gold Holdings Pte Ltd")

print("=" * 80)
print("FULL PIPELINE WITH DEBUG LOGGING")
print("=" * 80)

items = loader.load_entity_data(entity)
print(f"\n✓ Pipeline completed: {len(items)} items extracted")
EOF
```

**Check logs for:**
- [ ] Schema detection: `Detected schema 'oracle_trial_balance'`
- [ ] Sheet selection: `sheet='TB', header_row=6`
- [ ] Columns parsed: `Columns: ['Account', ...]`
- [ ] Items extracted: `Extracted 28 line items`

**[ ] PASS** - Full pipeline logs show correct flow

---

## Summary Checklist

| Test | Description | Status |
|------|-------------|--------|
| 1.1 | Schema patterns available | [ ] |
| 1.2 | Format detection works | [ ] |
| 1.3 | Data extraction works | [ ] |
| 2.1 | All 16 entities load | [ ] |
| 3.1 | Synonyms loaded | [ ] |
| 3.2 | Synonym matching works | [ ] |
| 3.3 | Semantic similarity works | [ ] |
| 4.1 | Django model works | [ ] |
| 5.1 | Zero values preserved | [ ] |
| 5.2 | AFS suffix stripping | [ ] |
| 6.1 | Full pipeline with logs | [ ] |

**Overall Status:** [ ] ALL TESTS PASSED

---

## Troubleshooting

### Issue: "No schema match" for a file

**Check logs:**
```python
import logging
logging.getLogger('narrated_financials.tools.docx_tables.schema_adapter').setLevel(logging.DEBUG)
```

**Common causes:**
1. File doesn't have expected sheet names (TB, PL, Mapping_AI)
2. Expected columns not found in first 20 rows
3. File is corrupted or password-protected

### Issue: Wrong data extracted

**Debug steps:**
1. Check `header_row` - Oracle files have 6 header rows
2. Check column indices in schema pattern
3. Verify column names match expected pattern

### Issue: Synonyms not working

**Check:**
1. Database connection for Django-based synonyms
2. Default synonyms in `SYNONYMS` dict in semantic_matcher.py
3. Fallback message in logs: "Could not load synonyms from database"

---

## Log Locations

| Component | Log Level | What to Look For |
|-----------|-----------|------------------|
| schema_adapter | DEBUG | Schema detection, sheet selection, column parsing |
| semantic_matcher | DEBUG | Synonym loading, similarity calculations |
| Django | INFO | Model operations, database queries |

**Enable full logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```
