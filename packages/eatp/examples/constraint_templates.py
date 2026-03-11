"""EATP Constraint Templates -- using built-in templates for agent archetypes.

Demonstrates:
    - Listing available templates
    - Loading and inspecting a template
    - Customizing a template with overrides
    - Saving templates to JSON files

Run:
    python constraint_templates.py
"""

import json
import tempfile
from pathlib import Path

from eatp.templates import (
    customize_template,
    get_template,
    get_template_names,
    list_templates,
    save_template_json,
)


def main():
    # -- List available templates --------------------------------------------
    print("Available EATP constraint templates:")
    print("-" * 60)
    for tmpl in list_templates():
        print(f"  {tmpl['name']:12s}  {tmpl['description']}")

    print(f"\nTemplate names: {get_template_names()}")

    # -- Load and inspect the finance template -------------------------------
    print("\n--- Finance Template ---")
    finance = get_template("finance")
    print(json.dumps(finance, indent=2))

    # Highlight key constraints
    constraints = finance["constraints"]
    print(f"\n  Max amount:     ${constraints['financial']['max_amount']:,}")
    print(f"  Daily limit:    ${constraints['financial']['daily_limit']:,}")
    print(f"  Market hours:   {constraints['temporal']['market_hours_start']} - "
          f"{constraints['temporal']['market_hours_end']} {constraints['temporal']['timezone']}")
    print(f"  Rate limit:     {constraints['communication']['rate_limit_per_minute']}/min")
    print(f"  Data ceiling:   {constraints['data_access']['classification_max']}")

    # -- Customize the finance template --------------------------------------
    print("\n--- Customized Finance Template ---")
    custom = customize_template(
        "finance",
        overrides={
            "financial": {
                "max_amount": 25000,
                "daily_limit": 50000,
            },
            "temporal": {
                "timezone": "US/Pacific",
            },
            "communication": {
                "approved_domains": ["*.internal.corp"],
                "external_access": False,
            },
        },
    )
    custom_constraints = custom["constraints"]
    print(f"  Max amount:     ${custom_constraints['financial']['max_amount']:,} (was $100,000)")
    print(f"  Daily limit:    ${custom_constraints['financial']['daily_limit']:,} (was $100,000)")
    print(f"  Timezone:       {custom_constraints['temporal']['timezone']} (was US/Eastern)")
    print(f"  External:       {custom_constraints['communication']['external_access']} (was True)")

    # -- Compare governance vs community templates ---------------------------
    print("\n--- Template Comparison: Governance vs Community ---")
    governance = get_template("governance")
    community = get_template("community")

    comparisons = [
        ("External access", governance["constraints"]["communication"]["external_access"],
         community["constraints"]["communication"]["external_access"]),
        ("Rate limit/min", governance["constraints"]["communication"]["rate_limit_per_minute"],
         community["constraints"]["communication"]["rate_limit_per_minute"]),
        ("Data ceiling", governance["constraints"]["data_access"]["classification_max"],
         community["constraints"]["data_access"]["classification_max"]),
        ("Read only", governance["constraints"]["data_access"]["read_only"],
         community["constraints"]["data_access"].get("read_only", False)),
        ("Hours", governance["constraints"]["temporal"]["hours"],
         community["constraints"]["temporal"]["hours"]),
    ]
    print(f"  {'Dimension':20s} {'Governance':15s} {'Community':15s}")
    print(f"  {'-' * 20} {'-' * 15} {'-' * 15}")
    for label, gov_val, com_val in comparisons:
        print(f"  {label:20s} {str(gov_val):15s} {str(com_val):15s}")

    # -- Save a template to a temp JSON file ---------------------------------
    print("\n--- Save Template to JSON ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "audit-constraints.json"
        saved = save_template_json("audit", path=output_path)
        content = json.loads(saved.read_text())
        print(f"  Saved to: {saved}")
        print(f"  Template name: {content['name']}")
        print(f"  Actions: {content['constraints']['scope']['actions']}")

    print("\nConstraint template operations completed.")


if __name__ == "__main__":
    main()
