---
domain: five_points
category: knowledge
name: FDS_CLIENT_MANAGEMENT_OVERVIEW
title: "Five Points — FDS Client Management: Overview & Glossary"
description: "TFI One FDS Client Management — Section I: Purpose, Glossary, Dependencies, and Table of Contents"
keywords: [fds, client-management, tfi-one, intake, placement, glossary, terms, overview]
updated: 2026-03-30
---

| Detail | Value |
| --- | --- |
| Title | Client Management |


| Date | By | Description |
| --- | --- | --- |
| 05/01/2025 | FPTG | Initial draft |
| 07/02/2025 | FPTG | Component section imports |
| 08/08/2025 | FPTG | Final review. Submitted to TFI. |


# Section I – Functional Category/ Module Overview
This section introduces the Client Management module, emphasizing its role in capturing and maintaining comprehensive client records across programs and services within the TFI One system. It covers the module’s purpose and core functionalities, including demographic intake, enrollment tracking, identity verification, and cross-agency record visibility. The module enables accurate, up-to-date client information is available to authorized users and supports coordination of care, compliance with state data standards, and integration with dependent modules. Key terms and acronyms are defined, and critical dependencies are identified to ensure proper configuration and use.
# 1. Purpose
The purpose of this Functional Design Specification (FDS) is to define the system functionality, user interfaces, business rules, screen elements, and security for each screen in the Client Management module. It serves as a blueprint for development and a reference for stakeholders to ensure that system design aligns with TFI requirements.
# 2. General Functional Category Description
The Client Management module supports TFI staff in the intake, identification, and ongoing maintenance of individual client records across the child welfare continuum. This module facilitates accurate capture and tracking of client demographics, enrollment history, household associations, and program involvement. The purpose is to ensure a single, consistent source of truth for client identity, eligibility, and participation.
Key functional capabilities include:
- Capturing and updating demographic and contact information.
- Managing multiple identifiers, aliases, and enrollment records.
- Associating clients with households, caregivers, and legal representatives.
- Verifying identity and preventing duplicate records.
- Tracking client status across agencies and programs.
- Supporting eligibility determinations and service planning.
# 3. Module Terms and Glossary
The Module Terms and Glossary section defines key terms and acronyms used throughout the Client Management module. It ensures a common understanding among all stakeholders and supports clarity in system design and implementation.

| Term | Description |
| --- | --- |
| ARD (Admission, Review, Dismissal) | Education process for evaluating and placing students with special needs |
| IEP (Individualized Education Program) | Customized education plan for students with disabilities |
| ECAP | External system used for placement and assessment data exchange |
| PID | Unique client identifier used across systems |
| TPG | Third-party group or system receiving placement transmissions |
| TEP (Temporary Placement) | Temporary placement |
| CPA | Child Placing Agency |
| CMP | Case Management Provider |
| GRO | General Residential Operation |
| OPPLA | Other Planned Permanent Living Arrangement |
| ICWA | Indian Child Welfare Act status indicator |
| PRTF | Psychiatric Residential Treatment Facility |
| Alias | Alternate name used for a client, often due to legal name changes |
| Face Sheet | Summary screen displaying key client information and program tiles |
| Intake | Initial process of enrolling a client into a program |
| Placement Request | Formal request for client placement into a program or facility |
| Service Package | Defined set of services provided to a client based on needs |
| Assessment | Evaluation of client needs, often used for placement or service planning |
| Recruitment Event | Outreach activity to identify potential adoptive families |
| Matched Event | Interaction event between prospective adoptive families and children |
| Home Study | Evaluation of a home’s suitability for foster or adoptive placement |
| Staffing | Formal meeting to discuss placement or adoption decisions |
| Client Alert | Notification of critical client status or behavior |
| Case Participant | Individual associated with a client’s case, such as caregiver or legal rep |

# 4. Target TFI Agency and Scoping Considerations
The Client Management module is utilized by all TFI agencies, including CPA, CMP, and Behavioral Health, and serves as the central hub for client-related data across the system. It is designed to support a unified client record accessible to authorized users across programs and geographic regions.
The Client Management module supports:
- Agency-wide access to client demographics and enrollment history.
- Integration with intake, service planning, and case management functions.
- Association of clients with households, legal reps, and caregivers.
- Support for cross-agency coordination and shared service delivery.
- Deduplication and identity resolution across systems.
- Compliance with state and federal data standards.
# 5. Functional Category Dependencies
The Contract Management module relies on integration with several other core functional areas of TFI One:
- General
- Client Management
- Case Management
- Service Requests
