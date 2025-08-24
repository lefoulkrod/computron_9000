import inspect
import json
import pytest
from pydantic import BaseModel

from agents.ollama.sdk.tool_loop import _to_serializable, _validate_tool_arguments
from tools.virtual_computer.models import TextPatch, ApplyPatchResult


class DummyModel(BaseModel):
    x: int
    y: str


class NestedModel(BaseModel):
    a: DummyModel
    b: list[DummyModel]
    c: dict[str, DummyModel]


@pytest.mark.unit
def test_to_serializable_with_pydantic_model():
    """
    Test that _to_serializable correctly converts a Pydantic model to a dict.
    """
    model = DummyModel(x=1, y="foo")
    result = _to_serializable(model)
    assert isinstance(result, dict)
    assert result == {"x": 1, "y": "foo"}


@pytest.mark.unit
def test_to_serializable_with_nested_structures():
    """
    Test that _to_serializable recursively converts nested Pydantic models in lists and dicts.
    """
    nested = NestedModel(
        a=DummyModel(x=2, y="bar"),
        b=[DummyModel(x=3, y="baz")],
        c={"k": DummyModel(x=4, y="qux")},
    )
    result = _to_serializable(nested)
    assert isinstance(result, dict)
    assert result["a"] == {"x": 2, "y": "bar"}
    assert result["b"] == [{"x": 3, "y": "baz"}]
    assert result["c"] == {"k": {"x": 4, "y": "qux"}}


@pytest.mark.unit
def test_to_serializable_with_primitive_types():
    """
    Test that _to_serializable returns primitive types unchanged.
    """
    assert _to_serializable(42) == 42
    assert _to_serializable("hello") == "hello"
    assert _to_serializable([1, 2, 3]) == [1, 2, 3]
    assert _to_serializable({"a": 1}) == {"a": 1}


@pytest.mark.unit
def test_to_serializable_with_non_pydantic_object():
    """
    Test that _to_serializable falls back to the object itself for unsupported types.
    """

    class NotSerializable:
        pass

    obj = NotSerializable()
    assert _to_serializable(obj) == obj


class PydanticTestModel(BaseModel):
    """Test Pydantic model for argument validation tests."""
    
    name: str
    value: int


@pytest.mark.unit
def test_validate_tool_arguments_basic_types():
    """
    Test argument validation with basic Python types.
    """
    def sample_tool(name: str, count: int, price: float, active: bool) -> str:
        return f"{name}: {count} @ {price} (active: {active})"
    
    arguments = {
        "name": "test",
        "count": "42",
        "price": "19.99",
        "active": "true"
    }
    
    result = _validate_tool_arguments(sample_tool, arguments)
    
    assert result["name"] == "test"
    assert result["count"] == 42
    assert isinstance(result["count"], int)
    assert result["price"] == 19.99
    assert isinstance(result["price"], float)
    assert result["active"] is True
    assert isinstance(result["active"], bool)


@pytest.mark.unit
def test_validate_tool_arguments_with_defaults():
    """
    Test argument validation when some parameters have default values.
    """
    def sample_tool(name: str, count: int = 10, active: bool = False) -> str:
        return f"{name}: {count} (active: {active})"
    
    arguments = {"name": "test"}
    
    result = _validate_tool_arguments(sample_tool, arguments)
    
    assert result["name"] == "test"
    assert result["count"] == 10
    assert result["active"] is False


@pytest.mark.unit
def test_validate_tool_arguments_no_type_hints():
    """
    Test argument validation when parameters have no type hints.
    """
    def sample_tool(name, count):
        return f"{name}: {count}"
    
    arguments = {"name": "test", "count": 42}
    
    result = _validate_tool_arguments(sample_tool, arguments)
    
    assert result["name"] == "test"
    assert result["count"] == 42


@pytest.mark.unit 
def test_validate_tool_arguments_pydantic_model():
    """
    Test argument validation with Pydantic model parsing.
    """
    def sample_tool(model: PydanticTestModel) -> str:
        return f"{model.name}: {model.value}"
    
    # Test with JSON string
    arguments = {"model": '{"name": "test", "value": 42}'}
    result = _validate_tool_arguments(sample_tool, arguments)
    
    assert isinstance(result["model"], PydanticTestModel)
    assert result["model"].name == "test"
    assert result["model"].value == 42
    
    # Test with dict
    arguments = {"model": {"name": "test2", "value": 24}}
    result = _validate_tool_arguments(sample_tool, arguments)
    
    assert isinstance(result["model"], PydanticTestModel)
    assert result["model"].name == "test2"
    assert result["model"].value == 24


@pytest.mark.unit
def test_validate_tool_arguments_optional_type():
    """
    Test argument validation with optional (None) type hints.
    """
    def sample_tool(name: str, optional_param: str | None = None) -> str:
        return f"{name}: {optional_param}"
    
    arguments = {"name": "test", "optional_param": None}
    
    result = _validate_tool_arguments(sample_tool, arguments)
    
    assert result["name"] == "test"
    assert result["optional_param"] is None


@pytest.mark.unit
def test_validate_tool_arguments_type_conversion_errors():
    """
    Test argument validation when type conversion fails.
    """
    def sample_tool(count: int) -> str:
        return f"Count: {count}"
    
    arguments = {"count": "not_a_number"}
    
    with pytest.raises(ValueError):
        _validate_tool_arguments(sample_tool, arguments)


@pytest.mark.unit
def test_validate_tool_arguments_json_decode_error():
    """
    Test argument validation when JSON parsing fails for Pydantic model.
    """
    def sample_tool(model: PydanticTestModel) -> str:
        return f"{model.name}: {model.value}"
    
    arguments = {"model": "invalid json"}
    
    with pytest.raises(json.JSONDecodeError):
        _validate_tool_arguments(sample_tool, arguments)


@pytest.mark.unit
def test_validate_tool_arguments_missing_required_param():
    """
    Test argument validation when a required parameter is missing.
    """
    def sample_tool(name: str, count: int) -> str:
        return f"{name}: {count}"
    
    arguments = {"name": "test"}  # missing 'count'
    
    with pytest.raises(ValueError, match="Required parameter 'count' is missing"):
        _validate_tool_arguments(sample_tool, arguments)


@pytest.mark.unit
def test_validate_tool_arguments_bool_conversion():
    """
    Test boolean argument validation with various input types.
    """
    def sample_tool(flag: bool) -> str:
        return f"Flag: {flag}"
    
    # Test various truthy/falsy values
    test_cases = [
        ("true", True),
        ("false", True),  # bool("false") is True in Python
        ("", False),
        (0, False),
        (1, True),
        ([], False),
        ([1], True),
    ]
    
    for input_val, expected in test_cases:
        arguments = {"flag": input_val}
        result = _validate_tool_arguments(sample_tool, arguments)
        assert result["flag"] == expected, f"Input {input_val} should result in {expected}"


@pytest.mark.unit
def test_validate_tool_arguments_mixed_types():
    """
    Test argument validation with a mix of different type hints.
    """
    def complex_tool(
        name: str,
        count: int,
        price: float,
        active: bool,
        model: PydanticTestModel,
        optional: str | None = None,
        no_hint=42
    ) -> str:
        return "complex result"
    
    arguments = {
        "name": "test",
        "count": "100",
        "price": "29.99",
        "active": "1",
        "model": {"name": "model_test", "value": 123},
        "optional": None,
        "no_hint": "any_value"
    }
    
    result = _validate_tool_arguments(complex_tool, arguments)
    
    assert result["name"] == "test"
    assert result["count"] == 100
    assert result["price"] == 29.99
    assert result["active"] is True
    assert isinstance(result["model"], PydanticTestModel)
    assert result["model"].name == "model_test"
    assert result["model"].value == 123
    assert result["optional"] is None
    assert result["no_hint"] == "any_value"


@pytest.mark.unit
def test_validate_tool_arguments_execute_python_program_example():
    """
    Test argument validation with the exact example from the user's request.
    
    This simulates the tool call: ToolCall(function=Function(name='execute_python_program', 
    arguments={'packages': [], 'program_text': "print('Hello World')"}))
    """
    def execute_python_program(packages: list[str], program_text: str) -> str:
        """Execute a Python program with optional packages."""
        return f"Executed: {program_text}"
    
    # This matches the exact structure from the user's example
    arguments = {
        "packages": [],
        "program_text": "print('Hello World')"
    }
    
    result = _validate_tool_arguments(execute_python_program, arguments)
    
    assert result["packages"] == []
    assert isinstance(result["packages"], list)
    assert result["program_text"] == "print('Hello World')"
    assert isinstance(result["program_text"], str)


@pytest.mark.unit
def test_validate_tool_arguments_apply_text_patch_example():
    """
    Test argument validation with the apply_text_patch tool function.
    
    This simulates a tool call for apply_text_patch with TextPatch objects,
    testing Pydantic model validation for complex nested structures.
    """
    def apply_text_patch(path: str, patches: list[TextPatch]) -> ApplyPatchResult:
        """Apply structured text patches to a file."""
        return ApplyPatchResult(success=True, file_path=path, diff="")
    
    # Simulate a tool call with nested Pydantic models
    arguments = {
        "path": "src/main.py",
        "patches": [
            {
                "start_line": 5,
                "end_line": 7,
                "replacement": "def new_function():\n    return 'updated'\n"
            },
            {
                "original": "old_text",
                "replacement": "new_text"
            }
        ]
    }
    
    result = _validate_tool_arguments(apply_text_patch, arguments)
    
    assert result["path"] == "src/main.py"
    assert isinstance(result["path"], str)
    assert isinstance(result["patches"], list)
    assert len(result["patches"]) == 2
    
    # First patch should be a TextPatch with line-based mode
    patch1 = result["patches"][0]
    assert isinstance(patch1, TextPatch)
    assert patch1.start_line == 5
    assert patch1.end_line == 7
    assert patch1.replacement == "def new_function():\n    return 'updated'\n"
    assert patch1.mode() == "lines"
    
    # Second patch should be a TextPatch with substring mode
    patch2 = result["patches"][1]
    assert isinstance(patch2, TextPatch)
    assert patch2.original == "old_text"
    assert patch2.replacement == "new_text"
    assert patch2.mode() == "substring"


@pytest.mark.unit
def test_validate_tool_arguments_list_edge_cases():
    """
    Test argument validation for list types with various edge cases.
    """
    def tool_with_list_args(simple_list: list[str], empty_list: list[int]) -> str:
        return "result"
    
    arguments = {
        "simple_list": ["item1", "item2", "item3"],
        "empty_list": []
    }
    
    result = _validate_tool_arguments(tool_with_list_args, arguments)
    
    assert result["simple_list"] == ["item1", "item2", "item3"]
    assert isinstance(result["simple_list"], list)
    assert result["empty_list"] == []
    assert isinstance(result["empty_list"], list)


@pytest.mark.unit
def test_validate_tool_arguments_list_with_json_strings():
    """
    Test argument validation for list of Pydantic models with JSON string inputs.
    """
    def tool_with_pydantic_list(models: list[PydanticTestModel]) -> str:
        return "result"
    
    # Test with JSON strings in the list
    arguments = {
        "models": ['{"name": "first", "value": 10}', '{"name": "second", "value": 20}']
    }
    
    result = _validate_tool_arguments(tool_with_pydantic_list, arguments)
    
    assert isinstance(result["models"], list)
    assert len(result["models"]) == 2
    assert isinstance(result["models"][0], PydanticTestModel)
    assert result["models"][0].name == "first"
    assert result["models"][0].value == 10
    assert isinstance(result["models"][1], PydanticTestModel)
    assert result["models"][1].name == "second"
    assert result["models"][1].value == 20
