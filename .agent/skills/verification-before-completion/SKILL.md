---
name: verification-before-completion
description: Use before claiming work is complete, fixed, or passing - requires fresh command execution and evidence inspection.
---

# Verification Before Completion

## The Iron Law
```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

## The Gate Protocol
1. **Identify:** Determine the exact command that proves the outcome (`npm run typecheck`, test runner, build command).
2. **Execute:** Run the complete command freshly within the current turn.
3. **Read:** Examine full terminal output and confirm zero errors or failures.
4. **Report Evidence:** Present exact output in the user response.
5. **Prohibit Assumptions:** Never use terms like "should pass", "looks good", or "assumed fixed" without terminal confirmation.
