"""
Tests for aare.ai verification engine
"""
import pytest
from aare_core import LLMParser, SMTVerifier, OntologyLoader


@pytest.fixture
def parser():
    return LLMParser()


@pytest.fixture
def verifier():
    return SMTVerifier()


@pytest.fixture
def ontology_loader():
    return OntologyLoader()


@pytest.fixture
def example_ontology(ontology_loader):
    return ontology_loader._get_example_ontology()


class TestSMTVerifier:
    """Test SMTVerifier with formula-based constraints"""

    def test_value_within_limits(self, verifier, example_ontology):
        """Test value within both min and max limits"""
        data = {
            "value": 50.0,
            "prohibited": False,
            "option_a": True,  # Satisfy EITHER_OR_REQUIREMENT
        }
        result = verifier.verify(data, example_ontology)
        assert result["verified"] is True
        assert len(result["violations"]) == 0

    def test_value_exceeds_maximum(self, verifier, example_ontology):
        """Test value exceeding maximum"""
        data = {
            "value": 150.0,  # Exceeds max of 100
        }
        result = verifier.verify(data, example_ontology)
        assert result["verified"] is False
        assert any(v["constraint_id"] == "MAX_VALUE" for v in result["violations"])

    def test_value_below_minimum(self, verifier, example_ontology):
        """Test value below minimum"""
        data = {
            "value": -10.0,  # Below min of 0
        }
        result = verifier.verify(data, example_ontology)
        assert result["verified"] is False
        assert any(v["constraint_id"] == "MIN_VALUE" for v in result["violations"])

    def test_prohibited_flag_violation(self, verifier, example_ontology):
        """Test prohibited flag being set"""
        data = {
            "value": 50.0,
            "prohibited": True,
        }
        result = verifier.verify(data, example_ontology)
        assert result["verified"] is False
        assert any(v["constraint_id"] == "NO_PROHIBITED_FLAG" for v in result["violations"])

    def test_conditional_requirement_satisfied(self, verifier, example_ontology):
        """Test conditional requirement when both conditions true"""
        data = {
            "value": 50.0,
            "condition_a": True,
            "condition_b": True,
        }
        result = verifier.verify(data, example_ontology)
        # Should pass - if A then B, both true
        conditional_violations = [v for v in result["violations"] if v["constraint_id"] == "CONDITIONAL_REQUIREMENT"]
        assert len(conditional_violations) == 0

    def test_conditional_requirement_violated(self, verifier, example_ontology):
        """Test conditional requirement violation"""
        data = {
            "value": 50.0,
            "condition_a": True,
            "condition_b": False,  # A is true but B is false -> violation
        }
        result = verifier.verify(data, example_ontology)
        assert result["verified"] is False
        assert any(v["constraint_id"] == "CONDITIONAL_REQUIREMENT" for v in result["violations"])

    def test_either_or_requirement_satisfied(self, verifier, example_ontology):
        """Test either-or requirement when one option selected"""
        data = {
            "value": 50.0,
            "option_a": True,
            "option_b": False,
        }
        result = verifier.verify(data, example_ontology)
        # Should pass - at least one option selected
        either_violations = [v for v in result["violations"] if v["constraint_id"] == "EITHER_OR_REQUIREMENT"]
        assert len(either_violations) == 0

    def test_either_or_requirement_violated(self, verifier, example_ontology):
        """Test either-or requirement violation when neither selected"""
        data = {
            "value": 50.0,
            "option_a": False,
            "option_b": False,
        }
        result = verifier.verify(data, example_ontology)
        assert result["verified"] is False
        assert any(v["constraint_id"] == "EITHER_OR_REQUIREMENT" for v in result["violations"])


class TestOntologyLoader:
    """Test ontology loading functionality"""

    def test_loads_example_ontology(self, ontology_loader):
        """Test that example ontology loads correctly"""
        ontology = ontology_loader._get_example_ontology()
        assert ontology["name"] == "example"
        assert "constraints" in ontology
        assert len(ontology["constraints"]) > 0

    def test_all_constraints_have_formula(self, ontology_loader):
        """Test that all constraints have formula field"""
        ontology = ontology_loader._get_example_ontology()
        for constraint in ontology["constraints"]:
            assert "formula" in constraint, f"Constraint {constraint['id']} missing formula"

    def test_list_available(self, ontology_loader):
        """Test listing available ontologies"""
        available = ontology_loader.list_available()
        assert "example" in available


class TestCustomOntology:
    """Test with example-custom.json ontology"""

    @pytest.fixture
    def custom_ontology(self, ontology_loader):
        return ontology_loader.load("example-custom")

    def test_discount_within_limit(self, verifier, custom_ontology):
        """Test discount within 25% limit"""
        data = {
            "discount_percentage": 20.0,
            "mentions_competitor": False,
            "word_count": 50,
        }
        result = verifier.verify(data, custom_ontology)
        assert result["verified"] is True

    def test_discount_exceeds_limit(self, verifier, custom_ontology):
        """Test discount exceeding 25% limit"""
        data = {
            "discount_percentage": 30.0,  # Exceeds 25%
            "mentions_competitor": False,
            "word_count": 50,
        }
        result = verifier.verify(data, custom_ontology)
        assert result["verified"] is False
        assert any(v["constraint_id"] == "MAX_DISCOUNT" for v in result["violations"])

    def test_competitor_mention_violation(self, verifier, custom_ontology):
        """Test competitor mention violation"""
        data = {
            "discount_percentage": 10.0,
            "mentions_competitor": True,  # Violated
            "word_count": 50,
        }
        result = verifier.verify(data, custom_ontology)
        assert result["verified"] is False
        assert any(v["constraint_id"] == "NO_COMPETITOR_MENTION" for v in result["violations"])

    def test_response_too_short(self, verifier, custom_ontology):
        """Test response length below minimum"""
        data = {
            "discount_percentage": 10.0,
            "mentions_competitor": False,
            "word_count": 5,  # Below 10 word minimum
        }
        result = verifier.verify(data, custom_ontology)
        assert result["verified"] is False
        assert any(v["constraint_id"] == "RESPONSE_LENGTH" for v in result["violations"])
