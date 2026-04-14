from app.nodes.extract_relations import parse_relations


def normalize_relation(relation: dict) -> tuple[str, str, str, str, str]:
    return (
        relation["source"].strip().lower(),
        relation["source_type"].strip().lower(),
        relation["target"].strip().lower(),
        relation["target_type"].strip().lower(),
        relation["relation"].strip().lower(),
    )


def run_case(name: str, raw: str, entities: list[dict], expected: list[dict]) -> bool:
    parsed = parse_relations(raw, entities)
    parsed_norm = {normalize_relation(item) for item in parsed}
    expected_norm = {normalize_relation(item) for item in expected}
    passed = parsed_norm == expected_norm

    print("=" * 100)
    print(f"TEST: {name}")
    print(f"EXPECTED: {expected}")
    print(f"PREDICTED: {parsed}")
    print(f"STATUS: {'PASS' if passed else 'FAIL'}")
    return passed


def main() -> None:
    shared_entities = [
        {"name": "MindGraph", "type": "project"},
        {"name": "Claude", "type": "tool"},
        {"name": "Rahul", "type": "person"},
        {"name": "Priya", "type": "person"},
        {"name": "Google", "type": "organization"},
    ]

    duplicate_name_entities = [
        {"name": "Phoenix", "type": "project"},
        {"name": "Phoenix", "type": "organization"},
        {"name": "Claude", "type": "tool"},
    ]

    cases = [
        {
            "name": "valid_semantic_relation",
            "raw": """
            [
              {
                "source": "MindGraph",
                "source_type": "project",
                "target": "Claude",
                "target_type": "tool",
                "relation": "built_with"
              }
            ]
            """,
            "entities": shared_entities,
            "expected": [
                {
                    "source": "MindGraph",
                    "source_type": "project",
                    "target": "Claude",
                    "target_type": "tool",
                    "relation": "built_with",
                }
            ],
        },
        {
            "name": "co_occurrence_rejection",
            "raw": "[]",
            "entities": shared_entities,
            "expected": [],
        },
        {
            "name": "invalid_relation_type_rejected",
            "raw": """
            [
              {
                "source": "MindGraph",
                "source_type": "project",
                "target": "Claude",
                "target_type": "tool",
                "relation": "mentioned_with"
              }
            ]
            """,
            "entities": shared_entities,
            "expected": [],
        },
        {
            "name": "self_edge_rejected",
            "raw": """
            [
              {
                "source": "Claude",
                "source_type": "tool",
                "target": "Claude",
                "target_type": "tool",
                "relation": "part_of"
              }
            ]
            """,
            "entities": shared_entities,
            "expected": [],
        },
        {
            "name": "ambiguous_direction_rejected",
            "raw": """
            [
              {
                "source": "Claude",
                "source_type": "tool",
                "target": "MindGraph",
                "target_type": "project",
                "relation": "uses"
              }
            ]
            """,
            "entities": shared_entities,
            "expected": [],
        },
        {
            "name": "works_with_is_canonicalized",
            "raw": """
            [
              {
                "source": "Rahul",
                "source_type": "person",
                "target": "Priya",
                "target_type": "person",
                "relation": "works_with"
              }
            ]
            """,
            "entities": shared_entities,
            "expected": [
                {
                    "source": "Priya",
                    "source_type": "person",
                    "target": "Rahul",
                    "target_type": "person",
                    "relation": "works_with",
                }
            ],
        },
        {
            "name": "duplicate_name_type_disambiguation_accepts_project",
            "raw": """
            [
              {
                "source": "Phoenix",
                "source_type": "project",
                "target": "Claude",
                "target_type": "tool",
                "relation": "built_with"
              }
            ]
            """,
            "entities": duplicate_name_entities,
            "expected": [
                {
                    "source": "Phoenix",
                    "source_type": "project",
                    "target": "Claude",
                    "target_type": "tool",
                    "relation": "built_with",
                }
            ],
        },
        {
            "name": "duplicate_name_type_disambiguation_rejects_org",
            "raw": """
            [
              {
                "source": "Phoenix",
                "source_type": "organization",
                "target": "Claude",
                "target_type": "tool",
                "relation": "built_with"
              }
            ]
            """,
            "entities": duplicate_name_entities,
            "expected": [],
        },
    ]

    results = [
        run_case(case["name"], case["raw"], case["entities"], case["expected"])
        for case in cases
    ]

    passed = sum(1 for result in results if result)
    total = len(results)

    print("\n" + "#" * 100)
    print(f"PASSED {passed}/{total} relation parsing tests")

    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
