---
name: mcp-builder
description: "Design and implementation of Model Context Protocol (MCP) tool servers for CashPilot. Use when exposing local databases, ERP connectors, bank statement parsers, and financial calculator tools to LLMs via standard JSON-RPC protocol."
---

# Model Context Protocol (MCP) Builder

Patterns for exposing deterministic financial tools to AI agents using the standard Model Context Protocol.

## 1. FastMCP Server Pattern (Python)

```python
from mcp.server.fastmcp import FastMCP
from decimal import Decimal
from typing import List, Dict

mcp = FastMCP("cashpilot-tools")

@mcp.tool()
def calculate_dscr(
    net_operating_income: float,
    total_debt_service: float
) -> Dict[str, str]:
    """Calculate the Debt Service Coverage Ratio (DSCR) deterministically.
    
    Args:
        net_operating_income: Annual net operating income before interest and taxes.
        total_debt_service: Total annual principal and interest debt payments.
    """
    if total_debt_service <= 0:
        return {"dscr": "N/A", "status": "Debt-free", "eligible": "True"}
        
    noi = Decimal(str(net_operating_income))
    ds = Decimal(str(total_debt_service))
    ratio = (noi / ds).quantize(Decimal("0.01"))
    
    eligible = ratio >= Decimal("1.25")
    return {
        "dscr": str(ratio),
        "status": "Healthy" if eligible else "Sub-prime / Covenant breach hazard",
        "eligible": str(eligible)
    }
```

## 2. Invariants for Financial MCP Tools

- **String Representation of Decimals**: Return exact strings (`"1.35"`) rather than floats (`1.34999999999`) to prevent JSON serialization precision loss.
- **Strict Parameter Documentation**: Every parameter must have an explicit type, description, and boundary constraint.
- **Read-Only Guarantee**: Tools exposed to Tier 1 agents must have zero state-mutation side effects.
