#!/bin/sh
set -eu

PYTEST=.venv/bin/pytest

echo '1. Agent loop and final evidence'
$PYTEST -q -k 'agent_fixes_project or cannot_finish_test_task or rejected_bash_gets_exact_feedback'

echo '2. Policy: allow and deny'
$PYTEST -q -k 'policy_allows_exact_command or policy_rejects_command or policy_rejects_path or protected_file_and_symlink or list_files_hides'

echo '3. Plan, safe mode, recovery, budgets and dependencies'
$PYTEST -q -k 'plan_mode or safe_mode or resume_preserves or crash_becomes or retry_checks or uncertain_call or budget'

echo '4. Readable events and usage'
$PYTEST -q -k 'session_events_stats or model_usage'

echo '5. Skills: positive, negative and no match'
$PYTEST -q -k 'skill_is_discovered or invalid_skill or skills_can_be_disabled or explicitly_choose_no_skill'

echo '6. MCP: success, error, timeout and policy denial'
$PYTEST -q -k 'mcp_discovers or mcp_error_and_timeout or mcp_policy_can_deny or exposes_and_logs_mcp'

echo '7. Doctor: finding and normal session'
$PYTEST -q -k 'doctor_finds or doctor_does_not_flag or doctor_shows_usage'

echo '8. Reproducible eval and resume'
$PYTEST -q -k 'eval_runner_restores or eval_checks_real'

echo '9. Market: discovery, validation and staging'
$PYTEST -q -k 'market_'

echo '10. Update: accept, reject, atomic apply and rollback'
$PYTEST -q -k 'update_decision or skill_update_applies_atomically_and_rolls_back or chat_can_roll_back'

echo '11. Full quality gate'
.venv/bin/ruff format --check agent tests
.venv/bin/ruff check agent tests
.venv/bin/mypy agent tests
$PYTEST -q
