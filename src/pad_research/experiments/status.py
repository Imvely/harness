"""Run status vocabulary (contract §35: failed experiments are stored, never deleted).

Terminal statuses
-----------------
* ``smoke_ok``: every *smoke* run that finishes its pipeline ends here, whatever
  the security gate said.  Smoke runs use tiny budgets whose metrics carry no
  scientific weight, so the gate verdict is recorded only as the MLflow/registry
  tag ``gate_verdict`` and never promoted to a status.
* ``success`` / ``security_regression`` / ``inconclusive``: full runs only, set
  from the security-gate verdict (``pass`` -> ``success``).
* ``failed_environment`` / ``failed_training``: crashes; ``invalid_spec`` /
  ``invalid_protocol``: rejected by validation; ``blocked_by_gate``: the launch
  gate refused to start the run.
"""

from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    running = "running"
    smoke_ok = "smoke_ok"
    success = "success"
    failed_environment = "failed_environment"
    failed_training = "failed_training"
    invalid_spec = "invalid_spec"
    invalid_protocol = "invalid_protocol"
    security_regression = "security_regression"
    inconclusive = "inconclusive"
    blocked_by_gate = "blocked_by_gate"

    @property
    def is_terminal(self) -> bool:
        return self is not RunStatus.running


TERMINAL_STATUSES: frozenset[RunStatus] = frozenset(s for s in RunStatus if s.is_terminal)
