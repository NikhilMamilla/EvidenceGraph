"""
Phase 8 — Provider-Aware Payment State Machine.

Encapsulates Razorpay payment lifecycle semantics and determines whether
observed status changes represent valid lifecycle progress or semantic conflicts.
"""
from __future__ import annotations

from typing import Dict, Set, Tuple


class PaymentStateMachine:
    """
    Explicit model of Razorpay payment states and transitions.
    """

    STATES = {
        "created",
        "authorized",
        "captured",
        "failed",
        "refunded",
    }

    TERMINAL_STATES = {"captured", "failed", "refunded"}

    # Allowed forward transitions: (from_state, to_state)
    VALID_TRANSITIONS: Set[Tuple[str, str]] = {
        ("created", "authorized"),
        ("created", "captured"),
        ("created", "failed"),
        ("authorized", "captured"),
        ("authorized", "failed"),
        ("captured", "refunded"),
    }

    @classmethod
    def normalize_state(cls, state: str) -> str:
        s = str(state).lower().strip()
        if s == "paid":
            return "captured"  # 'paid' is equivalent to 'captured' in order/payment contexts
        return s

    @classmethod
    def classify_transition(
        cls,
        from_state: str,
        to_state: str,
    ) -> Dict[str, any]:
        """
        Evaluates a transition from from_state to to_state.
        Returns:
            - is_valid: bool
            - transition_type: str ("VALID_FORWARD", "SAME_STATE", "INVALID_BACKWARD", "CONTRADICTORY_TERMINAL")
            - explanation: str
        """
        s1 = cls.normalize_state(from_state)
        s2 = cls.normalize_state(to_state)

        if s1 == s2:
            return {
                "is_valid": True,
                "transition_type": "SAME_STATE",
                "explanation": f"Idempotent state confirmation '{s1}'",
            }

        if (s1, s2) in cls.VALID_TRANSITIONS:
            return {
                "is_valid": True,
                "transition_type": "VALID_FORWARD",
                "explanation": f"Valid forward lifecycle progression from '{s1}' to '{s2}'",
            }

        # Terminal state conflict (e.g. captured vs failed)
        if s1 in cls.TERMINAL_STATES and s2 in cls.TERMINAL_STATES:
            return {
                "is_valid": False,
                "transition_type": "CONTRADICTORY_TERMINAL",
                "explanation": f"Contradictory terminal state transition between '{s1}' and '{s2}'",
            }

        # Backward / Invalid transition (e.g. captured -> authorized)
        return {
            "is_valid": False,
            "transition_type": "INVALID_BACKWARD",
            "explanation": f"Invalid backward transition from '{s1}' to '{s2}'",
        }
