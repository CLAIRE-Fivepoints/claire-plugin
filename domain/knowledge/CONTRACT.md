---
domain: fivepoints
category: knowledge
name: CONTRACT
title: "FivePoints — TFI One Pilot Contract & Pricing"
keywords: [contract, pricing, signed, defect, bug, tier, phase, pilot, fivepoints, dothelp, payment, acceptance, scope]
updated: 2026-03-27
---

# FivePoints — TFI One Pilot Contract & Pricing

Commercial terms for the TFI One Agentic AI Development Pilot between **Dot Help, LLC** (André Perez) and **Five Points Technology Group, Inc.**

---

## Signed Contract — Effective Pricing

**Document:** AI Development Pilot Program Sub-Contract Agreement
**Parties:** Five Points Technology Group, Inc. ("Company") × Dot Help, LLC ("Subcontractor")
**Status:** Signed agreement — these are the binding prices

### Phase 1 — Discovery & Enablement
- **Fee:** $5,000 fixed
- **Billing:** Due within 30 days of final agreement execution
- **Includes:** codebase connection, architecture review, FDS/PBI context, training, tuning, prompt config, workflow setup, human iteration
- **Exit criteria:** AI environment produces output ≥90% complete, ready for developer handoff
  - Must include: at least 1 FDS (similar to education module) + at least 1 defect resolution
  - "90% complete" = materially ready for developer handoff; only final completion/refinement/debugging/QA-readiness remaining
- **Note:** No additional setup, onboarding, training, or enablement fees beyond Phase 1

### Phase 2A — Defect Remediation

| Defect Type | Definition | Signed Price |
|-------------|-----------|--------------|
| Standard | Existing functionality, documented ticket, assigned by Five Points, sufficient info, no major redesign/architecture/net-new | **$75/defect** |
| Complex | Cross-module, ambiguous root cause, or >5 files | **$150/defect** |

- **Resolved definition:** Change materially corrects the reported issue in the agreed scenario; ready for QA validation
- **Scope approval:** Assignment of an individual defect ticket or approved batch by Five Points constitutes scope approval

### Phase 2B — New Development Tiers (Signed)

| Tier | Scope | Signed Price |
|------|-------|-------------|
| Tier 1 | Small change (1–5 files) | **$200** |
| Tier 2 | Small feature (5–15 files, single module) | **$350** |
| Tier 3 | Medium feature (15–40 files, cross-module) | **$750** *(or mutually agreed)* |
| Tier 4 | Large feature / major module / architectural enhancement | **$1,500+** *(or mutually agreed)* |
| Tier 5 | Extra large / enterprise-wide / multi-system | Custom quote |

**Scope approval required:** Each new development item must be scoped and approved in writing before work begins. Scope approval must identify:
- Tier designation
- Short scope description
- Related PBIs, FDS references, or other requirements
- Delivery target
- Acceptance criteria

### Monthly Subscription
- **Fee:** $500/month
- **Begins:** After written acceptance of Phase 1
- **Billing:** Monthly in advance, Net 30
- **Covers:** TFI One AI environment availability, context/training/prompt maintenance, reasonable ongoing tuning

### Phase 3 — Optional Services
Test script creation/execution, QA support, regression testing, defect triage — separately scoped and priced, payable Net 30.

### Payment Terms
- Phase 1: fixed $5,000, due within 30 days of final agreement
- Phase 2: invoiced monthly in arrears for accepted deliverables, Net 30
- Phase 3: per approved quote, Net 30
- Subscription: monthly in advance, Net 30
- No setup fees, enablement fees, performance bonuses, or API overage charges unless pre-approved in writing

---

## Key Contract Clauses

### Acceptance
- **Window:** 5 business days after delivery to accept or reject
- **Rejection:** Must identify material gaps against agreed acceptance criteria
- **No silence = acceptance:** A deliverable is NOT deemed accepted by silence alone
- **Defect acceptance:** No longer reproducible in agreed scenario OR materially corrected and ready for QA

### Iterations
- 1–3 iterations assumed between Five Points and Subcontractor
- Additional iterations resulting from incomplete or invalid FDS may incur additional fees as mutually agreed

### Scope Approval
- Written approval required before starting each new development item
- Defect batches: ticket assignment by Five Points constitutes approval

### Termination
- Either party may terminate with **5 calendar days' written notice**
- No early termination fee
- Accrued fees for accepted work before termination date are due

### Ownership
- All deliverables (software, source code, documentation, test scripts, design specs) belong exclusively to Five Points — "works made for hire"
- Subcontractor retains ownership of pre-existing tools, prompts, workflows, methodologies, platform components
- Subcontractor retains intangible residual know-how retained in memory (not tangible implementations)

### Data Residency
- Application code and related data must stay within the continental United States
- Company code/specs may not be used to train unrelated AI models

### Phase 1 Exit Criteria
- AI output ≥90% complete
- Must deliver: at least 1 FDS (comparable to education module) + at least 1 defect resolution
- "90% complete" = materially ready for developer handoff

---

## Task Tracker Reference

Active PBIs, tier assignments, and invoicing status are tracked in:

```
~/Documents/fivepoints_task_tracker.csv
```

This spreadsheet is the source of truth for:
- Which PBIs have been assigned and at what tier
- Invoicing status per deliverable
- Acceptance status per deliverable

---

## Historical: Negotiation Context (Term Sheet vs Signed)

The following reflects the negotiation outcome between the initial term sheet and the signed contract. Preserved for historical context.

### Price Comparison

| Item | Term Sheet | Signed Contract |
|------|-----------|-----------------|
| Phase 1 fee | $5,000 | $5,000 ✓ |
| Standard defect | $65 | **$75** |
| Complex defect | Not defined | **$150** |
| Tier 1 | $150 | **$200** |
| Tier 2 | $200 | **$350** |
| Tier 3 | $500 | **$750** |
| Tier 4 | $750+ | **$1,500+** |
| Tier 5 | Custom | Custom |
| Monthly subscription | $500 | $500 ✓ |
| Silence = acceptance | Not explicit | Explicitly NO |
| Termination | Not specified | 5 calendar days' written notice |

### Original Risk Analysis (Term Sheet)

The term sheet's $65/defect flat rate presented significant risk:
- Estimated 200 bugs in scope → $13,000 total at $65 flat
- Time per bug: 30–45 minutes minimum → effective rate ~$87–130/h (best case)
- Complex bugs would destroy the effective rate
- Complex defects explicitly excluded but no alternative price defined

**Result:** Negotiated to $75/standard + $150/complex — providing clarity and better protection on complex work.

### Comparison to dothelp Standard Contract

| Item | Signed Contract | dothelp Standard |
|------|----------------|-----------------|
| Phase 1 fee | $5,000 | $5,000 |
| Defect standard | $75 | $100–250 |
| Tier 1 | $200 | $250 |
| Tier 2 | $350 | $500 |
| Tier 3 | $750 | $1,000 |
| Tier 4 | $1,500+ | $2,500+ |
| Monthly subscription | $500 | $3,500 retainer |
| Acceptance window | 5 business days | 48 business hours |
| Silence = acceptance | No | Yes |
| Minimum term | None | 3 months |
| Early termination fee | None | 1 month |

The signed prices reflect FivePoints' negotiating position as a pilot client with volume potential. The $500/month subscription is low but generates recurring revenue.

---

## Key Contact

- **Brian Cliburn (CEO)** — Five Points Technology Group, Inc.
  - 2039 Centre Pointe Blvd, Ste 204, Tallahassee, FL 32308
  - brian.cliburn@fiveptg.com
