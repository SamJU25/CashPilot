---
name: grill-me
description: Stress-test thinking and requirements through structured interview rounds before implementation.
---

# Grilling Protocol

Interview the user relentlessly until reaching shared understanding. Map requirements as a **design tree**: every architectural decision branches into dependent choices.

## The Frontier
The frontier consists of decisions whose prerequisites are already settled. Ask the entire frontier in one structured round.

## Question Format
Number each question, explain context, provide choices, and state your recommendation:

```
❓ **Q1** - **<Decision Title>**: <Context and implications. Multiple choice options if applicable.>

➡️ <Recommended answer with technical rationale>

---

❓ **Q2** - **<Decision Title>**: <Context and implications.>

➡️ <Recommended answer with technical rationale>
```

Wait for the user's answers before proceeding to the next round or writing implementation code.
