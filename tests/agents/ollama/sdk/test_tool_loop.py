from pydantic import BaseModel

from agents.ollama.sdk.tool_loop import _to_serializable

class DummyModel(BaseModel):
    x: int
    y: str

class NestedModel(BaseModel):
    a: DummyModel
    b: list[DummyModel]
    c: dict[str, DummyModel]

def test_to_serializable_with_pydantic_model():
    """
    Test that _to_serializable correctly converts a Pydantic model to a dict.
    """
    model = DummyModel(x=1, y="foo")
    result = _to_serializable(model)
    assert isinstance(result, dict)
    assert result == {"x": 1, "y": "foo"}

def test_to_serializable_with_nested_structures():
    """
    Test that _to_serializable recursively converts nested Pydantic models in lists and dicts.
    """
    nested = NestedModel(
        a=DummyModel(x=2, y="bar"),
        b=[DummyModel(x=3, y="baz")],
        c={"k": DummyModel(x=4, y="qux")}
    )
    result = _to_serializable(nested)
    assert isinstance(result, dict)
    assert result["a"] == {"x": 2, "y": "bar"}
    assert result["b"] == [{"x": 3, "y": "baz"}]
    assert result["c"] == {"k": {"x": 4, "y": "qux"}}

def test_to_serializable_with_primitive_types():
    """
    Test that _to_serializable returns primitive types unchanged.
    """
    assert _to_serializable(42) == 42
    assert _to_serializable("hello") == "hello"
    assert _to_serializable([1, 2, 3]) == [1, 2, 3]
    assert _to_serializable({"a": 1}) == {"a": 1}

def test_to_serializable_with_non_pydantic_object():
    """
    Test that _to_serializable falls back to the object itself for unsupported types.
    """
    class NotSerializable:
        pass
    obj = NotSerializable()
    assert _to_serializable(obj) == obj
