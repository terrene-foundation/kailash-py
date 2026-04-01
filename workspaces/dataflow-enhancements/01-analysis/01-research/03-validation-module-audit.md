# Validation Module Audit

## Source

`packages/kailash-dataflow/src/dataflow/validation/` (8 files)

## Available Validators (`field_validators.py`)

All validators are pure functions, stdlib-only, thread-safe:

| Validator                              | Type    | Input                     | Returns                                     |
| -------------------------------------- | ------- | ------------------------- | ------------------------------------------- |
| `email_validator`                      | Simple  | `value -> bool`           | RFC 5322 simplified check                   |
| `url_validator`                        | Simple  | `value -> bool`           | HTTP(S) URL check                           |
| `uuid_validator`                       | Simple  | `value -> bool`           | Any UUID version                            |
| `phone_validator`                      | Simple  | `value -> bool`           | E.164 + formatted variants                  |
| `length_validator(min_len?, max_len?)` | Factory | Returns `(value) -> bool` | String/sequence length bounds               |
| `range_validator(min_val?, max_val?)`  | Factory | Returns `(value) -> bool` | Numeric bounds, validates `math.isfinite()` |
| `pattern_validator(regex)`             | Factory | Returns `(value) -> bool` | Full-string regex match                     |

**Missing from the brief's design**: `one_of_validator` does NOT exist yet. The brief correctly identifies this as needing to be added. Also not present: `ip_address_validator`, `date_validator`, `required_validator`.

## Decorator System (`decorators.py`)

- `@field_validator(field_name, validator_fn)` -- class decorator that appends to `cls.__field_validators__` list.
- `validate_model(instance)` -- runs all registered validators, returns `ValidationResult`.
- Validators stored as `List[Tuple[field_name, validator_fn, label]]`.
- Error aggregation (collects ALL errors, not fail-fast).
- Exception in validator treated as validation failure, not crash.

## Result Types (`result.py`)

- `FieldValidationError(frozen=True)` -- field, message, validator, value. Has `to_dict()/from_dict()`.
- `ValidationResult` -- errors list, `valid` property, `add_error()`, `merge()`, `to_dict()/from_dict()`.

## Other Modules

- `model_validator.py` (~24K) -- Model structure validation (schema-level, not field-level)
- `parameter_validator.py` (~17K) -- Workflow parameter validation
- `connection_validator.py` (~21K) -- Connection string validation
- `strict_mode.py` -- Opt-in strict validation config
- `validators.py` (~2K) -- Legacy/general validators

## DataFlowEngine Builder Integration

In `packages/kailash-dataflow/src/dataflow/engine.py` (the builder pattern):

- `DataFlowEngineBuilder` has a `validate_on_write(enabled: bool)` method
- `self._validate_on_write: bool = False` -- defaults to OFF
- This is on the ENGINE BUILDER, not on `DataFlow.__init__`

## What Is NOT Present

1. **No `__validation__` dict parsing** -- the `@db.model` decorator does NOT read any `__validation__` attribute.
2. **No `one_of_validator`** -- needs to be created.
3. **No validation-on-write in Express** -- Express `create()`, `update()`, `upsert()` do NOT call `validate_model()`.
4. **No `db.validate()` manual validation** -- not exposed on DataFlow class.
5. **The `DataFlowEngine.builder().validate_on_write(True)` exists** but is separate from the `DataFlow(...)` constructor path. The brief's proposed `DataFlow(validate_on_write=False)` parameter does NOT exist on `DataFlow.__init__`.

## Alignment Check

The brief says "The validator functions already exist" -- TRUE. email, url, uuid, length, range, pattern, phone all exist.
The brief says "@field_validator decorator: Working decorator approach" -- TRUE.
The brief says "There is no declarative dict syntax" -- TRUE.

## Risk for TSG-103

Low risk. Validators exist. The parser logic is straightforward mapping. The main work is:

1. Create `_apply_validation_dict()` parser
2. Add `one_of_validator`
3. Wire into `@db.model` decorator's config reading
4. Wire into Express write methods
5. Add `validate_on_write` parameter to `DataFlow.__init__`
