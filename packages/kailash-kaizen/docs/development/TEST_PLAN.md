# Test Plan: Structured Output Fix

**Version**: 1.0
**Date**: 2025-11-03
**Total Tests**: 155 new tests + 80 existing = 235 tests
**Estimated Test Writing Time**: 36 hours

---

## Test Summary

| Category | Test Files | Tests | Lines | Purpose |
|----------|-----------|-------|-------|---------|
| **Type Introspection** | 1 | 45 | 500 | Validate all typing constructs |
| **Extension Points** | 1 | 60 | 800 | Validate all 7 extension points |
| **Strict Mode** | 1 | 30 | 400 | Validate OpenAI compatibility |
| **E2E Integration** | 1 | 20 | 400 | End-to-end scenarios |
| **TOTAL NEW** | **4** | **155** | **2100** | - |
| **Existing Tests** | 3 | 80 | ~1500 | Should pass unchanged |
| **GRAND TOTAL** | **7** | **235** | **~3600** | Complete coverage |

---

## Test File 1: Type Introspection

**File**: `tests/unit/core/test_type_introspection.py`
**Tests**: 45 (25 validation + 20 schema generation)
**Lines**: 500
**Time to Write**: 12 hours

### Test Suite 1.1: TypeIntrospector Validation (25 tests)

#### Literal Type Tests (5 tests)
```python
class TestLiteralTypeValidation:
    """Test Literal type runtime validation."""

    def test_literal_valid_value(self):
        """Test Literal["A", "B", "C"] with valid value 'A'."""
        is_valid, error = TypeIntrospector.is_valid_type("A", Literal["A", "B", "C"])
        assert is_valid
        assert error == ""

    def test_literal_invalid_value(self):
        """Test Literal["A", "B", "C"] with invalid value 'D'."""
        is_valid, error = TypeIntrospector.is_valid_type("D", Literal["A", "B", "C"])
        assert not is_valid
        assert "not in allowed values" in error
        assert "['A', 'B', 'C']" in error

    def test_literal_single_value(self):
        """Test Literal with single value (edge case)."""
        is_valid, error = TypeIntrospector.is_valid_type("FIXED", Literal["FIXED"])
        assert is_valid

    def test_literal_with_spaces(self):
        """Test Literal values containing spaces."""
        is_valid, error = TypeIntrospector.is_valid_type(
            "Option One",
            Literal["Option One", "Option Two"]
        )
        assert is_valid

    def test_literal_with_special_chars(self):
        """Test Literal values with special characters."""
        is_valid, error = TypeIntrospector.is_valid_type(
            "pending...",
            Literal["pending...", "in-progress", "done!"]
        )
        assert is_valid
```

#### Union Type Tests (5 tests)
```python
class TestUnionTypeValidation:
    """Test Union type runtime validation."""

    def test_union_str_int_valid_str(self):
        """Test Union[str, int] with str value."""
        is_valid, error = TypeIntrospector.is_valid_type("test", Union[str, int])
        assert is_valid

    def test_union_str_int_valid_int(self):
        """Test Union[str, int] with int value."""
        is_valid, error = TypeIntrospector.is_valid_type(42, Union[str, int])
        assert is_valid

    def test_union_str_int_invalid(self):
        """Test Union[str, int] with invalid float value."""
        is_valid, error = TypeIntrospector.is_valid_type(3.14, Union[str, int])
        assert not is_valid
        assert "doesn't match any of" in error

    def test_union_with_none(self):
        """Test Union[str, int, None] with None value."""
        is_valid, error = TypeIntrospector.is_valid_type(None, Union[str, int, None])
        assert is_valid

    def test_union_complex_types(self):
        """Test Union with complex types: Union[str, List[int]]."""
        is_valid, error = TypeIntrospector.is_valid_type("test", Union[str, List[int]])
        assert is_valid

        is_valid, error = TypeIntrospector.is_valid_type([1, 2, 3], Union[str, List[int]])
        assert is_valid
```

#### Optional Type Tests (3 tests)
```python
class TestOptionalTypeValidation:
    """Test Optional type runtime validation."""

    def test_optional_with_none(self):
        """Test Optional[str] with None value."""
        is_valid, error = TypeIntrospector.is_valid_type(None, Optional[str])
        assert is_valid

    def test_optional_with_value(self):
        """Test Optional[str] with str value."""
        is_valid, error = TypeIntrospector.is_valid_type("test", Optional[str])
        assert is_valid

    def test_optional_with_wrong_type(self):
        """Test Optional[str] with int value (should fail)."""
        is_valid, error = TypeIntrospector.is_valid_type(42, Optional[str])
        assert not is_valid
```

#### List Type Tests (4 tests)
```python
class TestListTypeValidation:
    """Test List[T] type runtime validation."""

    def test_list_int_valid(self):
        """Test List[int] with valid int list."""
        is_valid, error = TypeIntrospector.is_valid_type([1, 2, 3], List[int])
        assert is_valid

    def test_list_int_invalid_element(self):
        """Test List[int] with string element at index 1."""
        is_valid, error = TypeIntrospector.is_valid_type([1, "two", 3], List[int])
        assert not is_valid
        assert "List element at index 1" in error

    def test_list_int_empty(self):
        """Test List[int] with empty list (should be valid)."""
        is_valid, error = TypeIntrospector.is_valid_type([], List[int])
        assert is_valid

    def test_list_not_a_list(self):
        """Test List[int] with non-list value."""
        is_valid, error = TypeIntrospector.is_valid_type("not a list", List[int])
        assert not is_valid
        assert "Expected list" in error
```

#### Dict Type Tests (4 tests)
```python
class TestDictTypeValidation:
    """Test Dict[K, V] type runtime validation."""

    def test_dict_str_int_valid(self):
        """Test Dict[str, int] with valid dict."""
        is_valid, error = TypeIntrospector.is_valid_type(
            {"a": 1, "b": 2},
            Dict[str, int]
        )
        assert is_valid

    def test_dict_str_int_invalid_key(self):
        """Test Dict[str, int] with int key."""
        is_valid, error = TypeIntrospector.is_valid_type(
            {123: "value"},
            Dict[str, int]
        )
        assert not is_valid
        assert "Dict key" in error

    def test_dict_str_int_invalid_value(self):
        """Test Dict[str, int] with str value."""
        is_valid, error = TypeIntrospector.is_valid_type(
            {"key": "value"},
            Dict[str, int]
        )
        assert not is_valid
        assert "Dict value" in error

    def test_dict_empty(self):
        """Test Dict[str, int] with empty dict."""
        is_valid, error = TypeIntrospector.is_valid_type({}, Dict[str, int])
        assert is_valid
```

#### Basic Type Tests (4 tests)
```python
class TestBasicTypeValidation:
    """Test basic Python type validation."""

    def test_str_valid(self):
        """Test str type with valid string."""
        is_valid, error = TypeIntrospector.is_valid_type("test", str)
        assert is_valid

    def test_int_float_interchangeable(self):
        """Test int accepts float (special case)."""
        is_valid, error = TypeIntrospector.is_valid_type(3.0, int)
        assert is_valid

    def test_float_int_interchangeable(self):
        """Test float accepts int (special case)."""
        is_valid, error = TypeIntrospector.is_valid_type(3, float)
        assert is_valid

    def test_bool_not_int(self):
        """Test bool doesn't accept int."""
        is_valid, error = TypeIntrospector.is_valid_type(1, bool)
        # Note: In Python, bool is subclass of int, so this may be valid
        # This test documents expected behavior
        pass
```

### Test Suite 1.2: TypeIntrospector Schema Generation (20 tests)

#### Literal Schema Tests (3 tests)
```python
class TestLiteralSchemaGeneration:
    """Test Literal → enum schema conversion."""

    def test_literal_to_enum(self):
        """Test Literal["A", "B"] generates enum schema."""
        schema = TypeIntrospector.to_json_schema_type(Literal["A", "B", "C"])
        assert schema == {
            "type": "string",
            "enum": ["A", "B", "C"]
        }

    def test_literal_single_value(self):
        """Test Literal with single value."""
        schema = TypeIntrospector.to_json_schema_type(Literal["FIXED"])
        assert schema["enum"] == ["FIXED"]

    def test_literal_many_values(self):
        """Test Literal with 10+ values."""
        colors = ["red", "orange", "yellow", "green", "blue", "indigo", "violet", "black", "white", "gray"]
        schema = TypeIntrospector.to_json_schema_type(Literal[*colors])
        assert len(schema["enum"]) == 10
```

#### Union Schema Tests (3 tests)
```python
class TestUnionSchemaGeneration:
    """Test Union → anyOf schema conversion."""

    def test_union_to_any_of(self):
        """Test Union[str, int] generates anyOf schema."""
        schema = TypeIntrospector.to_json_schema_type(Union[str, int])
        assert "anyOf" in schema
        assert {"type": "string"} in schema["anyOf"]
        assert {"type": "integer"} in schema["anyOf"]

    def test_union_with_none(self):
        """Test Union[str, None] generates anyOf with null."""
        schema = TypeIntrospector.to_json_schema_type(Union[str, None])
        assert "anyOf" in schema
        # or check for nullable string pattern

    def test_union_complex_types(self):
        """Test Union with complex types."""
        schema = TypeIntrospector.to_json_schema_type(Union[str, List[int]])
        assert "anyOf" in schema
```

#### Optional Schema Tests (2 tests)
```python
class TestOptionalSchemaGeneration:
    """Test Optional → nullable type schema conversion."""

    def test_optional_str_to_nullable(self):
        """Test Optional[str] generates nullable string."""
        schema = TypeIntrospector.to_json_schema_type(Optional[str])
        # Should be {"type": ["string", "null"]} or anyOf pattern
        assert "null" in str(schema)

    def test_optional_list_to_nullable(self):
        """Test Optional[List[str]] generates nullable array."""
        schema = TypeIntrospector.to_json_schema_type(Optional[List[str]])
        # Should include array type and null
        pass
```

#### List Schema Tests (3 tests)
```python
class TestListSchemaGeneration:
    """Test List[T] → array schema conversion."""

    def test_list_int_to_array(self):
        """Test List[int] generates array with integer items."""
        schema = TypeIntrospector.to_json_schema_type(List[int])
        assert schema == {
            "type": "array",
            "items": {"type": "integer"}
        }

    def test_list_str_to_array(self):
        """Test List[str] generates array with string items."""
        schema = TypeIntrospector.to_json_schema_type(List[str])
        assert schema["items"]["type"] == "string"

    def test_list_generic_to_array(self):
        """Test bare list generates array with string items (default)."""
        schema = TypeIntrospector.to_json_schema_type(list)
        assert schema["type"] == "array"
```

#### Dict Schema Tests (2 tests)
```python
class TestDictSchemaGeneration:
    """Test Dict[K, V] → object schema conversion."""

    def test_dict_str_int_to_object(self):
        """Test Dict[str, int] generates object with integer additionalProperties."""
        schema = TypeIntrospector.to_json_schema_type(Dict[str, int])
        assert schema["type"] == "object"
        assert "additionalProperties" in schema
        assert schema["additionalProperties"]["type"] == "integer"

    def test_dict_generic_to_object(self):
        """Test bare dict generates object."""
        schema = TypeIntrospector.to_json_schema_type(dict)
        assert schema["type"] == "object"
```

#### Basic Type Schema Tests (4 tests)
```python
class TestBasicTypeSchemaGeneration:
    """Test basic Python type → JSON schema conversion."""

    def test_str_to_string(self):
        """Test str → string."""
        schema = TypeIntrospector.to_json_schema_type(str)
        assert schema == {"type": "string"}

    def test_int_to_integer(self):
        """Test int → integer."""
        schema = TypeIntrospector.to_json_schema_type(int)
        assert schema == {"type": "integer"}

    def test_float_to_number(self):
        """Test float → number."""
        schema = TypeIntrospector.to_json_schema_type(float)
        assert schema == {"type": "number"}

    def test_bool_to_boolean(self):
        """Test bool → boolean."""
        schema = TypeIntrospector.to_json_schema_type(bool)
        assert schema == {"type": "boolean"}
```

#### Complex Schema Tests (3 tests)
```python
class TestComplexSchemaGeneration:
    """Test complex nested schema generation."""

    def test_nested_list_dict(self):
        """Test List[Dict[str, int]] generates correct nested schema."""
        schema = TypeIntrospector.to_json_schema_type(List[Dict[str, int]])
        assert schema["type"] == "array"
        assert schema["items"]["type"] == "object"

    def test_optional_list(self):
        """Test Optional[List[str]] generates nullable array."""
        schema = TypeIntrospector.to_json_schema_type(Optional[List[str]])
        # Should handle nullable array

    def test_union_literal(self):
        """Test Union with Literal."""
        schema = TypeIntrospector.to_json_schema_type(Union[Literal["A", "B"], int])
        # Should handle enum + integer
```

---

## Test File 2: Extension Points

**File**: `tests/unit/core/test_extension_points.py`
**Tests**: 60 (8 + 15 + 20 + 17)
**Lines**: 800
**Time to Write**: 12 hours

### Test Suite 2.1: ExtensionCallbacks (8 tests)

```python
class TestExtensionCallbacksDataclass:
    """Test ExtensionCallbacks dataclass."""

    def test_create_empty_callbacks(self):
        """Test creating ExtensionCallbacks with all None."""
        callbacks = ExtensionCallbacks()
        assert callbacks.generate_system_prompt is None
        assert callbacks.validate_signature_output is None
        assert callbacks.pre_execution_hook is None
        assert callbacks.post_execution_hook is None
        assert callbacks.handle_error is None

    def test_create_partial_callbacks(self):
        """Test creating ExtensionCallbacks with some callbacks."""
        def my_prompt():
            return "custom"

        callbacks = ExtensionCallbacks(generate_system_prompt=my_prompt)
        assert callbacks.generate_system_prompt is not None
        assert callbacks.validate_signature_output is None

    def test_callback_signatures_correct(self):
        """Test callback signatures match expected types."""
        def prompt_gen() -> str:
            return "prompt"

        def validator(output: Dict) -> tuple[bool, List[str]]:
            return True, []

        callbacks = ExtensionCallbacks(
            generate_system_prompt=prompt_gen,
            validate_signature_output=validator
        )

        # Test callbacks are callable
        assert callable(callbacks.generate_system_prompt)
        assert callable(callbacks.validate_signature_output)

    # 5 more tests...
```

### Test Suite 2.2: Extension Point Nodes (15 tests)

```python
class TestValidationNode:
    """Test ValidationNode execution."""

    def test_validation_node_passes_valid_data(self):
        """Test ValidationNode passes valid data through."""
        def validator(data):
            return True, []

        node = ValidationNode(validator=validator)
        result = node.execute(input={"key": "value"})

        assert result == {"key": "value"}

    def test_validation_node_raises_on_invalid(self):
        """Test ValidationNode raises error on validation failure."""
        def validator(data):
            return False, ["Error 1", "Error 2"]

        node = ValidationNode(validator=validator)

        with pytest.raises(ValueError) as exc_info:
            node.execute(input={"key": "value"})

        assert "Validation failed" in str(exc_info.value)
        assert "Error 1" in str(exc_info.value)

    # 13 more tests for ValidationNode, PreHookNode, PostHookNode...
```

### Test Suite 2.3: WorkflowGenerator Callbacks (20 tests)

```python
class TestWorkflowGeneratorWithCallbacks:
    """Test WorkflowGenerator accepts and uses callbacks."""

    def test_generate_workflow_with_all_callbacks(self):
        """Test workflow generation with all callbacks provided."""
        callbacks = ExtensionCallbacks(
            generate_system_prompt=lambda: "CUSTOM",
            validate_signature_output=lambda x: (True, []),
            pre_execution_hook=lambda x: x,
            post_execution_hook=lambda x: x,
            handle_error=lambda e: None
        )

        generator = WorkflowGenerator(
            config=config,
            signature=signature,
            callbacks=callbacks
        )

        workflow = generator.generate_signature_workflow()

        # Verify workflow contains extension point nodes
        nodes = workflow.nodes
        assert "pre_hook" in nodes
        assert "validate_output" in nodes
        assert "post_hook" in nodes

    def test_custom_system_prompt_used(self):
        """Test custom system prompt callback is called."""
        custom_prompt = "MY CUSTOM PROMPT"

        callbacks = ExtensionCallbacks(
            generate_system_prompt=lambda: custom_prompt
        )

        generator = WorkflowGenerator(
            config=config,
            signature=signature,
            callbacks=callbacks
        )

        workflow = generator.generate_signature_workflow()

        # Extract system prompt from LLMAgentNode config
        agent_node = workflow.nodes["agent_exec"]
        assert agent_node["system_prompt"] == custom_prompt

    # 18 more tests...
```

### Test Suite 2.4: BaseAgent Extension Points (17 tests)

```python
class TestBaseAgentExtensionPoints:
    """Test BaseAgent extension points work end-to-end."""

    def test_custom_generate_system_prompt_called(self):
        """Test custom _generate_system_prompt is called during execution."""
        prompt_calls = []

        class CustomAgent(BaseAgent):
            def _generate_system_prompt(self) -> str:
                prompt_calls.append(True)
                return "CUSTOM PROMPT"

        agent = CustomAgent(config=config, signature=signature)
        result = agent.run(question="test")

        assert prompt_calls  # Verify method was called

    def test_custom_validate_signature_output_called(self):
        """Test custom _validate_signature_output is called."""
        validation_calls = []

        class ValidatingAgent(BaseAgent):
            def _validate_signature_output(self, output: Dict) -> tuple[bool, List[str]]:
                validation_calls.append(output)
                return True, []

        agent = ValidatingAgent(config=config, signature=signature)
        result = agent.run(question="test")

        assert validation_calls
        assert "answer" in validation_calls[0]  # Output was passed

    def test_custom_pre_execution_hook_modifies_input(self):
        """Test pre-execution hook can modify input data."""
        class PreHookAgent(BaseAgent):
            def _pre_execution_hook(self, input_data: Dict) -> Dict:
                input_data["modified"] = True
                return input_data

        agent = PreHookAgent(config=config, signature=signature)
        result = agent.run(question="test")

        # Verify modification propagated (would need workflow introspection)

    # 14 more tests...
```

---

## Test File 3: Strict Mode Validator

**File**: `tests/unit/core/test_strict_mode_validator.py`
**Tests**: 30 (15 + 10 + 5)
**Lines**: 400
**Time to Write**: 8 hours

### Test Suite 3.1: Compatibility Checking (15 tests)

```python
class TestStrictModeCompatibility:
    """Test strict mode compatibility detection."""

    def test_compatible_signature(self):
        """Test signature fully compatible with strict mode."""
        class CompatibleSig(Signature):
            input: str = InputField(desc="Input")
            output: str = OutputField(desc="Output")
            confidence: float = OutputField(desc="Confidence")

        compatibility = StrictModeValidator.check_signature_compatibility(CompatibleSig())

        assert compatibility.is_compatible
        assert len(compatibility.errors) == 0
        assert len(compatibility.warnings) == 0

    def test_pattern_validation_incompatible(self):
        """Test pattern validation detected as incompatible."""
        class PatternSig(Signature):
            input: str = InputField(desc="Input")
            email: str = OutputField(
                desc="Email",
                metadata={"validation": {"pattern": r"^[\w\.-]+@"}}
            )

        compatibility = StrictModeValidator.check_signature_compatibility(PatternSig())

        assert not compatibility.is_compatible
        assert any("pattern" in err.lower() for err in compatibility.errors)
        assert any("Literal" in rec for rec in compatibility.recommendations)

    def test_min_max_validation_incompatible(self):
        """Test min/max validation detected as incompatible."""
        class MinMaxSig(Signature):
            input: str = InputField(desc="Input")
            value: int = OutputField(
                desc="Value",
                metadata={"validation": {"min": 0, "max": 100}}
            )

        compatibility = StrictModeValidator.check_signature_compatibility(MinMaxSig())

        assert not compatibility.is_compatible
        assert any("min/max" in err.lower() for err in compatibility.errors)

    # 12 more tests covering all OpenAI constraints...
```

### Test Suite 3.2: Auto-Fallback Behavior (10 tests)

```python
class TestAutoFallbackBehavior:
    """Test auto_fallback parameter behavior."""

    def test_auto_fallback_with_compatible(self):
        """Test auto_fallback=True with compatible signature uses strict mode."""
        class CompatibleSig(Signature):
            input: str = InputField(desc="Input")
            output: str = OutputField(desc="Output")

        config = create_structured_output_config(
            CompatibleSig(),
            strict=True,
            auto_fallback=True
        )

        assert config["type"] == "json_schema"
        assert config["json_schema"]["strict"] is True

    def test_auto_fallback_with_incompatible(self):
        """Test auto_fallback=True with incompatible signature falls back."""
        class IncompatibleSig(Signature):
            input: str = InputField(desc="Input")
            value: int = OutputField(
                desc="Value",
                metadata={"validation": {"min": 0}}
            )

        with patch('logging.Logger.warning') as mock_warning:
            config = create_structured_output_config(
                IncompatibleSig(),
                strict=True,
                auto_fallback=True
            )

            assert config["type"] == "json_object"  # Fell back
            assert mock_warning.called  # Warning logged

    def test_no_fallback_raises_error(self):
        """Test auto_fallback=False raises error on incompatibility."""
        class IncompatibleSig(Signature):
            input: str = InputField(desc="Input")
            value: int = OutputField(
                desc="Value",
                metadata={"validation": {"pattern": "test"}}
            )

        with pytest.raises(ValueError) as exc_info:
            config = create_structured_output_config(
                IncompatibleSig(),
                strict=True,
                auto_fallback=False
            )

        error_msg = str(exc_info.value)
        assert "incompatible" in error_msg.lower()
        assert "recommendations" in error_msg.lower()

    # 7 more tests...
```

### Test Suite 3.3: Integration Tests (5 tests)

```python
class TestStrictModeIntegration:
    """Test strict mode end-to-end with BaseAgent."""

    def test_compatible_signature_uses_strict_mode(self):
        """Test BaseAgent with compatible signature uses strict mode."""
        class CompatibleSig(Signature):
            question: str = InputField(desc="Question")
            answer: str = OutputField(desc="Answer")

        config = BaseAgentConfig(
            llm_provider="mock",
            model="gpt-4o-2024-08-06",
            generation_config={
                "response_format": create_structured_output_config(
                    CompatibleSig(),
                    strict=True
                )
            }
        )

        agent = BaseAgent(config=config, signature=CompatibleSig())

        # Verify strict mode enabled in config
        response_format = config.generation_config["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True

    # 4 more E2E integration tests...
```

---

## Test File 4: E2E Integration

**File**: `tests/integration/test_structured_output_e2e.py`
**Tests**: 20 (10 OpenAI + 10 Mock)
**Lines**: 400
**Time to Write**: 4 hours

### Test Suite 4.1: Real OpenAI API (10 tests)

```python
@pytest.mark.integration
@pytest.mark.openai
class TestStructuredOutputOpenAI:
    """E2E tests with real OpenAI API."""

    def test_literal_type_strict_mode(self):
        """Test Literal type with real OpenAI strict mode."""
        class CategorySig(Signature):
            text: str = InputField(desc="Text to categorize")
            category: Literal["tech", "business", "personal"] = OutputField(
                desc="Category"
            )

        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-2024-08-06",
            generation_config={
                "response_format": create_structured_output_config(
                    CategorySig(),
                    strict=True
                )
            }
        )

        agent = BaseAgent(config=config, signature=CategorySig())
        result = agent.run(text="AI is transforming software development")

        # Verify Literal constraint enforced
        assert result["category"] in ["tech", "business", "personal"]

    def test_union_type_fallback_mode(self):
        """Test Union type falls back to strict=False."""
        class UnionSig(Signature):
            text: str = InputField(desc="Text")
            value: Union[str, int] = OutputField(desc="Value")

        # Union likely not supported in strict mode
        with patch('logging.Logger.warning') as mock_warning:
            config = create_structured_output_config(
                UnionSig(),
                strict=True,
                auto_fallback=True
            )

            # Should fallback (depending on implementation)
            # Test that it works either way

    # 8 more E2E tests with real OpenAI...
```

### Test Suite 4.2: Mock Provider (10 tests)

```python
@pytest.mark.unit
class TestStructuredOutputMock:
    """E2E tests with mock provider (faster)."""

    def test_all_typing_constructs_work(self):
        """Test signature with all typing constructs."""
        class ComprehensiveSig(Signature):
            text: str = InputField(desc="Input")

            # All supported types
            literal_field: Literal["A", "B"] = OutputField(desc="Literal")
            union_field: Union[str, int] = OutputField(desc="Union")
            optional_field: Optional[str] = OutputField(desc="Optional")
            list_field: List[str] = OutputField(desc="List")
            dict_field: Dict[str, int] = OutputField(desc="Dict")
            basic_str: str = OutputField(desc="String")
            basic_int: int = OutputField(desc="Integer")
            basic_float: float = OutputField(desc="Float")
            basic_bool: bool = OutputField(desc="Boolean")

        config = BaseAgentConfig(
            llm_provider="mock",
            model="gpt-4",
            generation_config={
                "response_format": create_structured_output_config(
                    ComprehensiveSig(),
                    strict=False  # Use fallback for complex types
                )
            }
        )

        agent = BaseAgent(config=config, signature=ComprehensiveSig())
        result = agent.run(text="test input")

        # Verify all fields present
        assert "literal_field" in result
        assert "union_field" in result
        # ... etc

    # 9 more mock-based E2E tests...
```

---

## Existing Tests to Verify

### File 1: test_structured_output_literal.py (18 tests)

**Status**: Should pass without changes after Bug #1 fix

**Key Tests**:
- `test_validate_literal_field_valid_value` - **CURRENTLY FAILING, WILL PASS**
- `test_literal_string_to_enum` - Should pass
- `test_literal_with_sentinel_value` - Should pass
- `test_multiple_literal_fields` - Should pass
- All 18 tests should pass

**Verification**:
```bash
pytest tests/unit/core/test_structured_output_literal.py -v
```

### File 2: test_structured_output.py (40 tests estimated)

**Status**: May need minor updates

**Key Tests**:
- Schema generation tests - May need updates for TypeIntrospector
- Validation tests - May need updates for error message format
- System prompt generation - Should pass unchanged

**Verification**:
```bash
pytest tests/unit/core/test_structured_output.py -v
```

### File 3: test_workflow_generator.py (22 tests estimated)

**Status**: Should pass with minor additions

**Key Tests**:
- Workflow generation - Should pass unchanged
- System prompt generation - Should pass unchanged
- Node configuration - Should pass unchanged

**Verification**:
```bash
pytest tests/unit/core/test_workflow_generator.py -v
```

---

## Test Execution Plan

### Phase 1: Type Introspection Tests (Day 3-4)

```bash
# Write tests first (TDD)
pytest tests/unit/core/test_type_introspection.py -v --tb=short

# Expected: All 45 tests FAIL (implementation not done yet)

# After implementation (Task 1.1-1.2)
pytest tests/unit/core/test_type_introspection.py -v

# Expected: All 45 tests PASS
```

### Phase 2: Extension Point Tests (Day 9-10)

```bash
# Write tests first
pytest tests/unit/core/test_extension_points.py -v --tb=short

# Expected: All 60 tests FAIL

# After implementation (Task 2.1-2.3)
pytest tests/unit/core/test_extension_points.py -v

# Expected: All 60 tests PASS
```

### Phase 3: Strict Mode Tests (Day 14)

```bash
# Write tests first
pytest tests/unit/core/test_strict_mode_validator.py -v --tb=short

# Expected: All 30 tests FAIL

# After implementation (Task 3.1-3.2)
pytest tests/unit/core/test_strict_mode_validator.py -v

# Expected: All 30 tests PASS
```

### Phase 4: Integration Tests (Day 15)

```bash
# Write tests first
pytest tests/integration/test_structured_output_e2e.py -v --tb=short -m "not openai"

# Expected: Mock tests fail

# After full implementation
pytest tests/integration/test_structured_output_e2e.py -v

# Expected: All 20 tests PASS (10 mock + 10 OpenAI with API key)
```

### Regression Testing (Day 16-17)

```bash
# Run all unit tests
pytest packages/kailash-kaizen/tests/unit/ -v --durations=10

# Expected: 215 tests pass (155 new + 60 existing)

# Run all integration tests
pytest packages/kailash-kaizen/tests/integration/ -v

# Expected: All integration tests pass

# Run full test suite
pytest packages/kailash-kaizen/tests/ -v --cov=kaizen.core --cov-report=html

# Expected: >90% coverage
```

---

## Coverage Goals

| Module | Target Coverage | Critical Paths |
|--------|-----------------|----------------|
| `type_introspection.py` | 100% | All typing constructs |
| `extension_points.py` | 100% | Dataclass only |
| `extension_point_nodes.py` | 95% | Node execution, error handling |
| `strict_mode_validator.py` | 95% | All OpenAI constraints |
| `structured_output.py` (modified) | 100% | Schema generation, validation |
| `workflow_generator.py` (modified) | 90% | Callback integration |
| `base_agent.py` (modified) | 85% | Extension point wiring |

**Overall Target**: >90% coverage for all modified/new code

---

## Performance Benchmarks

**To be measured during testing:**

```python
def test_type_introspector_performance():
    """Benchmark TypeIntrospector overhead."""
    import time

    # Test 1000 type checks
    start = time.perf_counter()
    for _ in range(1000):
        TypeIntrospector.is_valid_type("A", Literal["A", "B", "C"])
    duration = time.perf_counter() - start

    # Target: <1ms per call on average
    assert duration < 1.0  # 1 second for 1000 calls

def test_extension_point_node_latency():
    """Benchmark extension point node execution."""
    import time

    def simple_hook(data):
        return data

    node = PreHookNode(hook=simple_hook)

    start = time.perf_counter()
    for _ in range(1000):
        node.execute(input={"key": "value"})
    duration = time.perf_counter() - start

    # Target: <5ms per call
    assert duration < 5.0

def test_schema_generation_performance():
    """Benchmark schema generation for complex signature."""
    # Test with 20 fields, nested structures
    # Target: <10ms
    pass
```

---

## Test Metrics

**Success Criteria**:
- ✅ All 155 new tests written (2100 lines)
- ✅ All 155 new tests passing
- ✅ All 80 existing tests still passing
- ✅ >90% code coverage for modified/new code
- ✅ Performance benchmarks pass
- ✅ Zero regressions in existing functionality

**Test Quality Metrics**:
- Clear test names describing what is tested
- Comprehensive edge case coverage
- Realistic test data (not just happy path)
- Clear assertions with good error messages
- Well-organized test suites
- Fast execution (<5 seconds for unit tests)

---

## Test Writing Guidelines

### Test Naming Convention
```python
# ✅ GOOD: Descriptive, specific
def test_literal_type_with_valid_value_passes_validation():
    pass

# ❌ BAD: Vague, unclear
def test_literal():
    pass
```

### Test Structure (AAA Pattern)
```python
def test_example():
    # Arrange: Set up test data
    signature = MySignature()
    expected = {"type": "string", "enum": ["A", "B"]}

    # Act: Execute the code under test
    result = TypeIntrospector.to_json_schema_type(Literal["A", "B"])

    # Assert: Verify results
    assert result == expected
```

### Test Documentation
```python
def test_complex_scenario():
    """
    Test that complex nested structures generate correct schemas.

    This test verifies:
    - List[Dict[str, int]] generates nested array/object schema
    - All type information preserved
    - Schema is OpenAI strict mode compatible
    """
    pass
```

---

**Document Status**: Ready for Test Implementation
**Next Step**: Begin writing tests (Phase 1, Day 3)
