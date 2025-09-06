## Norm Audit (fallback)

## Norm Audit
- NormSet: `NormSet.base.v1`
- L2 Validators: ruff:fail, mypy:fail, pytest:fail, docs_updated:pass
- L1 Violations: 3
- Metrics: NormPass@1=0.25, RepairDepth=0, DeterminismScore=1.00, WaiverCount=0

```json
{
  "conformance": {
    "L0": "pass",
    "L1": [
      "exceptions.narrow:fail"
    ],
    "L2": [
      "ruff:fail",
      "mypy:fail",
      "pytest:fail",
      "docs_updated:pass"
    ],
    "L3": [
      "journals:append"
    ]
  },
  "metrics": {
    "DeterminismScore": 1.0,
    "NormPass@1": 0.25,
    "RepairDepth": 0,
    "ViolationMix": [
      "/home/rose/lexlattice/urs.py: except Exception",
      "/home/rose/lexlattice/scripts/dev/norm_audit.py: except Exception",
      "/home/rose/lexlattice/scripts/dev/norm_audit.py: except BaseException"
    ],
    "WaiverCount": 0
  },
  "normset": "NormSet.base.v1",
  "notes": ""
}
```

