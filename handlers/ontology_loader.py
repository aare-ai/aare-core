"""
Ontology loader for aare.ai (Self-hosted version)
Loads verification rules from local filesystem or returns example default
"""
import json
import os
import logging
from functools import lru_cache
from pathlib import Path


class OntologyLoader:
    def __init__(self, ontology_dir=None):
        self.ontology_dir = Path(
            ontology_dir or os.environ.get("ONTOLOGY_DIR", "./ontologies")
        )

    @lru_cache(maxsize=10)
    def load(self, ontology_name):
        """Load ontology from filesystem or return default"""
        ontology_file = self.ontology_dir / f"{ontology_name}.json"

        try:
            if ontology_file.exists():
                with open(ontology_file, "r") as f:
                    ontology = json.load(f)
                return self._validate_ontology(ontology)
        except Exception as e:
            logging.warning(f"Failed to load ontology from {ontology_file}: {e}")

        # Fall back to example ontology
        logging.info(f"Using example ontology for {ontology_name}")
        return self._get_example_ontology()

    def _validate_ontology(self, ontology):
        """Validate ontology structure"""
        required_fields = ["name", "version", "constraints"]
        for field in required_fields:
            if field not in ontology:
                raise ValueError(f"Invalid ontology: missing {field}")

        # Validate each constraint has a formula field
        for constraint in ontology.get("constraints", []):
            if "formula" not in constraint:
                raise ValueError(
                    f"Invalid ontology: constraint {constraint.get('id', 'unknown')} missing 'formula' field"
                )

        return ontology

    def _get_example_ontology(self):
        """
        Return example ontology demonstrating the framework.

        This is a generic example showing how to define constraints.
        For production use, create your own ontology JSON files in the ontologies/ directory.
        """
        return {
            "name": "example",
            "version": "1.0.0",
            "description": "Example ontology demonstrating constraint syntax",
            "constraints": [
                {
                    "id": "MAX_VALUE",
                    "category": "Limits",
                    "description": "Value must not exceed maximum",
                    "formula_readable": "value ≤ 100",
                    "formula": {"<=": ["value", 100]},
                    "variables": [{"name": "value", "type": "real"}],
                    "error_message": "Value exceeds maximum allowed (100)",
                    "citation": "Example Policy",
                },
                {
                    "id": "MIN_VALUE",
                    "category": "Limits",
                    "description": "Value must meet minimum threshold",
                    "formula_readable": "value ≥ 0",
                    "formula": {">=": ["value", 0]},
                    "variables": [{"name": "value", "type": "real"}],
                    "error_message": "Value below minimum threshold (0)",
                    "citation": "Example Policy",
                },
                {
                    "id": "NO_PROHIBITED_FLAG",
                    "category": "Compliance",
                    "description": "Prohibited flag must not be set",
                    "formula_readable": "¬prohibited",
                    "formula": {"==": ["prohibited", False]},
                    "variables": [{"name": "prohibited", "type": "bool"}],
                    "error_message": "Prohibited action detected",
                    "citation": "Example Policy",
                },
                {
                    "id": "CONDITIONAL_REQUIREMENT",
                    "category": "Logic",
                    "description": "If condition A, then condition B must be true",
                    "formula_readable": "condition_a → condition_b",
                    "formula": {
                        "implies": [
                            {"==": ["condition_a", True]},
                            {"==": ["condition_b", True]},
                        ]
                    },
                    "variables": [
                        {"name": "condition_a", "type": "bool"},
                        {"name": "condition_b", "type": "bool"},
                    ],
                    "error_message": "Condition B required when Condition A is true",
                    "citation": "Example Policy",
                },
                {
                    "id": "EITHER_OR_REQUIREMENT",
                    "category": "Logic",
                    "description": "At least one option must be selected",
                    "formula_readable": "option_a ∨ option_b",
                    "formula": {
                        "or": [
                            {"==": ["option_a", True]},
                            {"==": ["option_b", True]},
                        ]
                    },
                    "variables": [
                        {"name": "option_a", "type": "bool"},
                        {"name": "option_b", "type": "bool"},
                    ],
                    "error_message": "At least one option must be selected",
                    "citation": "Example Policy",
                },
            ],
            "extractors": {
                "value": {"type": "float", "pattern": "value[:\\s]*(\\d+(?:\\.\\d+)?)"},
                "prohibited": {
                    "type": "boolean",
                    "keywords": ["prohibited", "forbidden", "banned"],
                },
                "condition_a": {"type": "boolean", "keywords": ["condition a", "case a"]},
                "condition_b": {"type": "boolean", "keywords": ["condition b", "case b"]},
                "option_a": {"type": "boolean", "keywords": ["option a", "choice a"]},
                "option_b": {"type": "boolean", "keywords": ["option b", "choice b"]},
            },
        }

    def list_available(self):
        """List all available ontologies"""
        ontologies = set(["example"])

        # Add any from the ontology directory
        if self.ontology_dir.exists():
            for f in self.ontology_dir.glob("*.json"):
                ontologies.add(f.stem)

        return sorted(list(ontologies))
