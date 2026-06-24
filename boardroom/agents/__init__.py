"""The LLM layer — divisions' narrator, the CEO's rationale, the risk manager,
and the Critic's post-mortems, as separate prompted agents. Reasoning ONLY.
The LLM never produces a number the system acts on (scope §5, §12).
"""

from boardroom.agents.llm import LLM
from boardroom.agents.narrator import narrate_pitch
from boardroom.agents.risk_manager import RiskManager, RiskChallenge

__all__ = ["LLM", "narrate_pitch", "RiskManager", "RiskChallenge"]
