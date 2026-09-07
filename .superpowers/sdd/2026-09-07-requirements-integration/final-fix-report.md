# Requirements integration final fix

## Finding

`validate_bundle` normalized `scenario_code` with `text()` but did not reject a
different original value containing leading or trailing whitespace. Import then
stored the unnormalized value, while scenario updates normalized the lookup
value, making the imported scenario unreachable by update.

## TDD red-green record

Added a parametrized regression test covering both leading and trailing spaces.
Each case asserts `DomainError`, preserves the pre-existing `APP-1` issue and
project list, and confirms no extra issue was imported.

### RED

Command:

```text
PYTHONPATH=devops/agent-harness pytest -q devops/agent-harness/cli_anything/devops/tests/test_requirements.py -k scenario_code_with_surrounding_whitespace
```

Result: `2 failed, 18 deselected` — both whitespace cases did not raise
`DomainError`.

### GREEN

Minimal production change: reject when the normalized scenario code differs
from the original value, using the same rule as `req_code` validation.

Focused command:

```text
PYTHONPATH=. pytest -q cli_anything/devops/tests/test_requirements.py -k scenario_code_with_surrounding_whitespace
```

Result: `2 passed, 18 deselected`.

Full focused module command:

```text
PYTHONPATH=. pytest -q cli_anything/devops/tests/test_requirements.py
```

Result: `20 passed`.
