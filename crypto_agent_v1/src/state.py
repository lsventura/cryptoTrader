from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    candles: Any
    sentiment: str
    quant_signal: str
    risk_decision: Dict[str, Any]
    pnl_history: List[float]
    metrics: Dict[str, Any]
    next_step: str
