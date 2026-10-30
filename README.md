# AI Hiking Assistant and Emergency Coordination System

## Overview

The **AI Hiking Assistant and Emergency Coordination System** is a Flutter-based final-year research project designed to improve hiker safety through intelligent risk awareness, offline assistance, navigation support, emergency coordination, contextual information fusion, and decentralised information sharing.

The system follows a modular architecture in which multiple research components contribute to a common hiking-safety platform. Each component addresses a different aspect of the overall problem while sharing agreed models, interfaces, and application infrastructure.

A central design goal is to support hikers in remote environments where internet connectivity may be weak, intermittent, or completely unavailable. For this reason, the system architecture considers local processing, offline resources, on-device intelligence, local event storage, and optional synchronization when connectivity becomes available.

> **Research prototype:** This project is developed for academic research and evaluation. Emergency, medical, navigation, and risk information generated or displayed by the system must not be considered a replacement for professional medical advice, trained rescue personnel, official maps, or emergency services.

---

# 1. Problem Statement

Hiking and outdoor activities frequently take place in environments with limited network coverage and delayed access to emergency services. Hikers may encounter problems such as:

- injuries and medical emergencies;
- becoming lost or disoriented;
- environmental hazards;
- changing trail conditions;
- insufficient safety information;
- difficulty communicating during emergencies;
- limited access to online AI assistants;
- delayed sharing of risk and emergency information.

Many conventional mobile applications depend heavily on cloud services and continuous internet connectivity. This project investigates how intelligent and decentralised technologies can be combined to provide useful hiking assistance even under connectivity constraints.

---

# 2. Project Objectives

The overall system aims to investigate technologies that can improve hiking safety through:

1. Intelligent collection and interpretation of hiking context.
2. Prediction and communication of potential hiking risks.
3. Offline access to hiking safety and emergency information.
4. AI-assisted question answering for hiking situations.
5. Trail and location awareness.
6. Emergency and SOS coordination.
7. Local recording of risk and emergency events.
8. Decentralised information exchange between system components.
9. Optional synchronization when network connectivity is available.
10. Integration of independently developed research components into a common Flutter application.

---

# 3. High-Level System Architecture

The project follows a feature-based modular Flutter architecture.

```text
                         ┌───────────────────────────┐
                         │         HIKER / USER      │
                         └─────────────┬─────────────┘
                                       │
                                       ▼
                         ┌───────────────────────────┐
                         │      Flutter Mobile App   │
                         │        Home / UI Layer    │
                         └─────────────┬─────────────┘
                                       │
             ┌─────────────────────────┼──────────────────────────┐
             │                         │                          │
             ▼                         ▼                          ▼
     ┌───────────────┐        ┌────────────────┐        ┌────────────────┐
     │ Component 1   │        │ Component 2    │        │ Component 3    │
     │ Research      │        │ Research       │        │ AI / Risk      │
     │ Module        │        │ Module         │        │ Assistance     │
     └───────┬───────┘        └───────┬────────┘        └───────┬────────┘
             │                         │                          │
             └──────────────┬──────────┴──────────────┬───────────┘
                            │                         │
                            ▼                         ▼
                  ┌──────────────────┐       ┌──────────────────┐
                  │ Context Fusion   │       │   Component 4    │
                  │ / Shared Context │       │ Research Module  │
                  └────────┬─────────┘       └────────┬─────────┘
                           │                          │
                           └────────────┬─────────────┘
                                        │
                                        ▼
                    ┌────────────────────────────────┐
                    │ Shared Hiking Safety Services  │
                    ├────────────────────────────────┤
                    │ Risk Prediction                │
                    │ Hiking Assistant               │
                    │ Knowledge Base                 │
                    │ Trail Navigation               │
                    │ Emergency Coordination         │
                    │ Event Logs                     │
                    │ Synchronization                │
                    └────────────────────────────────┘
```

The exact data contracts between components are defined through team-agreed shared models, enums, and interfaces.

---

# 4. Main System Components

The application is divided into independently maintainable research and application modules.

## Component 1

```text
lib/features/component_1/
```

This directory is reserved for the implementation owned by Team Member 1.

Its implementation should remain isolated within the component unless a model, interface, or data contract has explicitly been agreed upon by the team.

> Detailed algorithms, datasets, models, and evaluation results for Component 1 should be documented here according to its actual implementation.

---

## Component 2

```text
lib/features/component_2/
```

This directory contains the implementation owned by Team Member 2.

The module communicates with other parts of the system through agreed shared interfaces rather than direct dependencies on another member's internal implementation.

> Detailed Component 2 functionality should be documented from its implemented source code and research methodology.

---

## Component 3

Component 3 contains intelligent hiking-support functionality and is organised by feature rather than through a separate `component_3/` directory.

Relevant modules include:

```text
lib/features/risk_prediction/
lib/features/hiking_assistant/
lib/features/knowledge_base/
```

### Risk Prediction

The risk-prediction feature is intended to analyse relevant hiking context and estimate potential risk conditions.

```text
lib/features/risk_prediction/
```

Its inputs, prediction methodology, model, output classes, thresholds, and evaluation metrics should be documented according to the implemented version.

### Offline Hiking Assistant

```text
lib/features/hiking_assistant/
```

The Offline Hiking Assistant investigates whether useful AI-supported hiking and emergency information can be provided without depending on cloud-based inference.

The implemented assistant architecture combines local knowledge retrieval with an on-device language model.

At a high level:

```text
User Question
      │
      ▼
Question Processing
      │
      ▼
Question Routing / Normalisation
      │
      ▼
Offline Knowledge Retrieval
      │
      ▼
Evidence Ranking / Filtering
      │
      ▼
RAG Context Construction
      │
      ▼
On-Device Language Model
      │
      ▼
Grounding / Response Validation
      │
      ▼
Answer + Supporting Sources
```

This follows the concept of **Retrieval-Augmented Generation (RAG)**.

Instead of asking the language model to answer exclusively from information contained in its pretrained parameters, the application first retrieves relevant information from a curated local knowledge base. The retrieved evidence is then supplied to the local model as context.

This approach is intended to improve grounding while retaining offline operation.

---

# 5. Context Fusion

```text
lib/features/context_fusion/
```

Context fusion provides a location for combining relevant information produced by Components 1, 2, and 4.

The objective is to transform information from independent research components into a common context that other intelligent system features can consume.

Cross-component communication should use agreed interfaces and shared data structures rather than direct coupling between feature implementations.

---

# 6. Knowledge Base

```text
lib/features/knowledge_base/
assets/knowledge/
```

The knowledge-base subsystem is responsible for offline hiking, safety, and first-aid information used by intelligent features.

For the Offline Hiking Assistant, relevant information can be retrieved locally before an answer is generated.

The final documentation should record the exact:

- authoritative information sources;
- number of source documents;
- number of processed records;
- number of knowledge chunks;
- knowledge categories;
- database schema;
- indexing mechanism;
- ranking strategy;
- database size;
- update/versioning mechanism.

These numbers should always be generated from the current dataset/database rather than manually estimated.

---

# 7. Retrieval-Augmented Generation

Retrieval-Augmented Generation combines **information retrieval** with **language-model generation**.

The project's offline assistant follows the general process:

```text
Question
   ↓
Query processing
   ↓
Local knowledge search
   ↓
Relevant evidence
   ↓
Prompt + evidence
   ↓
Local LLM
   ↓
Generated response
   ↓
Grounding/validation
   ↓
Response + sources
```

RAG is particularly relevant to the project because hiking safety information should ideally be grounded in curated evidence rather than generated solely from the language model's internal knowledge.

---

# 8. On-Device AI

The system investigates **Edge AI**, where AI computation occurs on the user's device instead of sending every request to a remote cloud service.

The Offline Hiking Assistant uses a quantized local language-model architecture.

A quantized model reduces numerical precision to decrease:

- storage requirements;
- runtime memory requirements;
- computational cost.

Quantization is different from model training or fine-tuning.

### Important terminology

**Pretraining**  
Training a language model on a very large corpus from an initial or near-initial state.

**Fine-tuning**  
Continuing the training of a pretrained model using a specialised dataset.

**Quantization**  
Reducing the numerical precision of an existing model to make inference more resource-efficient.

**RAG**  
Retrieving external evidence and providing it to a model during inference.

**Local inference**  
Executing the model directly on the user's device.

The project's final documentation should state exactly which of these techniques are actually performed by the repository rather than describing quantization or RAG as fine-tuning.

---

# 9. Trail Navigation

```text
lib/features/trail_navigation/
assets/maps/
```

The trail-navigation module is the designated location for GPS and trail-related functionality.

The system architecture allows navigation information to contribute to hiking assistance, contextual awareness, and emergency workflows.

Any offline map technology, GPS processing, route algorithms, map datasets, or navigation APIs should be documented according to the final implementation.

---

# 10. Emergency Coordination

```text
lib/features/emergency/
```

This module provides the architectural location for SOS and emergency-coordination workflows.

Emergency coordination can potentially consume information from:

- user context;
- navigation;
- risk prediction;
- event logs;
- other research components.

The exact SOS communication mechanism and emergency workflow depend on the implemented version of the research system.

---

# 11. Event Logging

```text
lib/features/event_logs/
```

Event logs provide a location for recording relevant risk and emergency information locally.

Local event storage is important in an offline-first system because information may need to be retained even when a network connection is unavailable.

Recorded information may later be consumed by other system components or synchronized according to the final implementation.

---

# 12. Synchronization

```text
lib/features/synchronization/
```

The synchronization feature is designed for functionality that requires data exchange when network connectivity is available.

The overall architecture distinguishes between:

```text
Offline-critical functionality
        +
Optional connected functionality
```

This prevents essential offline features from being unnecessarily dependent on continuous internet connectivity.

---

# 13. Component 4

```text
lib/features/component_4/
```

This directory contains the research implementation assigned to Team Member 4.

Its internal algorithms and dependencies should remain within its feature boundary unless functionality is intentionally exposed through shared contracts.

> Component 4's detailed methodology, technology stack, datasets, algorithms, and evaluation should be added according to its actual implementation.

---

# 14. Shared Models and Interfaces

```text
lib/shared/
├── models/
├── enums/
└── interfaces/
```

The `shared` package contains contracts explicitly agreed upon by the team.

### `shared/models`

Contains data models that need to be understood by multiple research components.

### `shared/enums`

Contains common enumerations used across component boundaries.

### `shared/interfaces`

Defines contracts through which independently developed components can communicate.

Keeping these contracts separate from component-specific implementations reduces unnecessary coupling between research modules.

---

# 15. Core Application Layer

```text
lib/core/
```

The `core` directory is reserved for reusable functionality that is not specific to an individual research domain.

Examples include:

- constants;
- reusable utilities;
- common errors;
- generic widgets.

Domain-specific functionality should remain inside its corresponding feature.

---

# 16. Application Configuration

```text
lib/app/
├── app.dart
├── router.dart
└── theme/
```

### `app.dart`

Contains root Flutter application configuration.

### `router.dart`

Provides the agreed location for application navigation and routing.

### `theme/`

Contains shared visual-design configuration.

---

# 17. Application Entry Point

```text
lib/main.dart
```

`main.dart` is the Flutter application entry point.

It is responsible for bootstrapping the application and transferring control to the application's root configuration.

---

# 18. Assets

The project maintains feature resources under:

```text
assets/
├── images/
├── models/
├── maps/
└── knowledge/
```

### `assets/images`

Application imagery and visual resources.

### `assets/models`

On-device model artefacts where applicable.

Large model binaries should only be committed when explicitly intended by the project. Otherwise, the README should provide instructions for obtaining or installing them.

### `assets/maps`

Offline or packaged map resources where applicable.

### `assets/knowledge`

Curated offline knowledge resources used by knowledge-based functionality.

---

# 19. Research Resources

Research experiments, data preparation, model evaluation, knowledge-base construction, and mobile-model preparation should remain reproducible.

Where present, the repository's `research/` resources should document the complete research pipeline:

```text
Raw Data
    ↓
Data Exploration
    ↓
Cleaning
    ↓
Normalisation
    ↓
Labelling
    ↓
Categorisation
    ↓
Knowledge Preparation
    ↓
Model / Retrieval Experiments
    ↓
Evaluation
    ↓
Mobile Deployment
```

Each notebook and script should clearly state its inputs, processing steps, outputs, and evaluation purpose.

---

# 20. Data and Dataset Documentation

Every research component should document its datasets separately.

For each dataset, record:

| Information | Description |
|---|---|
| Dataset | Dataset/source name |
| Component | Research component using it |
| Purpose | Why the dataset is required |
| Source | Origin of the data |
| Records | Number of usable records |
| Categories | Classes/categories represented |
| Processing | Cleaning/transformation performed |
| Output | Processed dataset/database/model input |
| License | Dataset usage conditions |

Dataset counts should be calculated from the current research artefacts rather than manually estimated.

---

# 21. AI Model Evaluation

There is not necessarily one meaningful **“system accuracy”** for a multi-component application.

Each intelligent subsystem should be evaluated according to its task.

For example:

### Classification / Prediction

Potential metrics include:

- Accuracy
- Precision
- Recall
- F1-score
- Confusion matrix

### Information Retrieval

Potential metrics include:

- Top-k retrieval success
- Precision@k
- Recall@k
- Mean Reciprocal Rank
- category-routing performance

### Generative AI

Potential evaluation dimensions include:

- grounding;
- relevance;
- completeness;
- unsupported-claim rate;
- response acceptance;
- latency.

### Mobile System

Potential measurements include:

- inference latency;
- memory consumption;
- model loading time;
- application stability;
- offline success rate.

Only metrics actually produced by experiments should be reported as project results.

---

# 22. Offline-First Architecture

An important research direction of the system is reducing unnecessary dependence on remote infrastructure.

Offline-capable components can potentially keep resources such as:

```text
Knowledge
Models
Maps
Event Records
Retrieval
Inference
```

on the user's device.

Connected services can then be treated separately:

```text
                    SYSTEM
                       │
           ┌───────────┴───────────┐
           ▼                       ▼
    OFFLINE SERVICES        CONNECTED SERVICES
           │                       │
    Local knowledge          Synchronization
    Local models             Remote exchange
    Local maps               Online updates
    Local event logs         External services
```

The exact offline/online boundary depends on each component's implemented functionality.

---

# 23. Privacy

Local processing can provide privacy advantages because information that can be processed on-device does not necessarily need to be transmitted to a remote AI service.

The final system should document which information:

- remains on the device;
- is shared with another device;
- is synchronized;
- is sent to an external service.

This distinction is particularly important for location and emergency information.

---

# 24. Safety

This system is an academic research prototype.

It must not be considered a substitute for:

- professional medical care;
- trained first responders;
- official emergency services;
- professional rescue services;
- certified navigation equipment;
- official safety instructions.

AI-generated information may be incomplete, delayed, incorrectly retrieved, or incorrectly generated.

---

# 25. Project Structure

```text
lib/
├── main.dart
├── app/
│   ├── app.dart
│   ├── router.dart
│   └── theme/
│
├── core/
│
├── features/
│   ├── component_1/
│   ├── component_2/
│   ├── home/
│   ├── context_fusion/
│   ├── risk_prediction/
│   ├── hiking_assistant/
│   ├── knowledge_base/
│   ├── trail_navigation/
│   ├── emergency/
│   ├── event_logs/
│   ├── synchronization/
│   └── component_4/
│
└── shared/
    ├── models/
    ├── enums/
    └── interfaces/

assets/
├── images/
├── models/
├── maps/
└── knowledge/
```

Feature implementations should remain within their designated module boundaries.

Shared contracts should only be introduced when they are required by more than one component and have been agreed upon by the team.

---

# 26. Development Principles

The project follows several architectural principles:

### Feature isolation

Research components should remain independently maintainable.

### Explicit interfaces

Cross-component communication should occur through defined contracts.

### Offline-first design

Critical hiking functionality should avoid unnecessary network dependencies where technically feasible.

### Evidence grounding

Safety-related AI responses should be grounded in curated information where the implemented feature supports it.

### Modularity

Individual research components should be independently testable and replaceable.

### Reproducible research

Datasets, experiments, transformations, and evaluations should be documented sufficiently for research results to be reproduced.

---

# 27. Prerequisites

Install Flutter using the official Flutter installation documentation.

Required development tools generally include:

- Flutter SDK
- Dart SDK
- Git
- Android Studio / Android SDK for Android development
- Xcode for iOS development on macOS, where required
- Python/Jupyter for research experiments, where applicable

Verify Flutter:

```bash
flutter doctor
```

---

# 28. Installation

Clone the repository:

```bash
git clone https://github.com/mirshadahamed/Decentralized-Hiking-AI.git
```

Enter the project:

```bash
cd Decentralized-Hiking-AI
```

Install Flutter dependencies:

```bash
flutter pub get
```

Check the project:

```bash
flutter analyze
```

Run tests:

```bash
flutter test
```

Run the application:

```bash
flutter run
```

Additional model, database, map, dataset, or platform-specific setup should be documented alongside the component that requires it.

---

# 29. Testing

Before merging changes, contributors should run:

```bash
flutter pub get
flutter analyze
flutter test
```

Individual research components should additionally maintain tests appropriate to their algorithms and data pipelines.

Testing should cover both **individual component correctness** and **cross-component integration**.

---

# 30. Team Development Workflow

1. Update the local `main` branch.
2. Create a feature-specific branch.
3. Implement functionality inside the assigned module.
4. Avoid modifying another component's internal implementation without coordination.
5. Discuss new shared contracts before adding them.
6. Keep credentials and generated development artefacts out of Git.
7. Run analysis and tests.
8. Document research and implementation changes.
9. Open a pull request.
10. Obtain review before merging.

Example branch names:

```text
feature/component-1-inputs
feature/component-2-processing
feature/risk-prediction
feature/offline-hiking-assistant
feature/emergency-coordination
feature/component-4
```

---

# 31. Repository Boundaries

The following directories have explicit ownership or architectural purposes:

```text
features/component_1/     → Team Member 1
features/component_2/     → Team Member 2

features/risk_prediction/
features/hiking_assistant/
features/knowledge_base/  → Component 3-related functionality

features/component_4/     → Team Member 4
```

Cross-component functionality belongs in shared modules only when the team has agreed on the corresponding contract.

The project intentionally avoids introducing speculative integration layers before concrete interfaces and use cases have been defined.

---

# 32. Current Development Status

The repository began as a shared Flutter architecture establishing module boundaries for the four research components.

Development is now progressing from this common foundation toward independently implemented and integrated research features.

Because individual components can progress at different rates, the existence of a feature directory should **not** automatically be interpreted as evidence that the corresponding feature is complete.

The implementation status of each component should be determined from its current source code, tests, research artefacts, and documentation.

---

# 33. Known Limitations

As a research prototype, the system may contain limitations relating to:

- incomplete integration between research components;
- mobile-device resource constraints;
- offline data coverage;
- AI inference latency;
- retrieval quality;
- model output quality;
- GPS and sensor accuracy;
- map availability;
- network availability for synchronization;
- device-to-device communication;
- emergency communication reliability;
- differences between emulator and physical-device behaviour.

Component-specific limitations should be documented separately and supported by experimental results wherever possible.

---

# 34. Future Work

Potential system-level development includes:

- completion of individual research components;
- cross-component context fusion;
- improved offline operation;
- broader hiking-safety knowledge coverage;
- improved AI retrieval and response grounding;
- mobile inference optimisation;
- improved risk prediction;
- richer offline navigation;
- emergency-coordination improvements;
- decentralised information exchange;
- synchronization and conflict handling;
- privacy and security evaluation;
- battery and memory optimisation;
- usability studies;
- physical-device field testing;
- end-to-end system evaluation.

---

# 35. Research Scope

The overall project investigates how multiple intelligent and decentralised technologies can be combined into a single mobile hiking-safety platform.

The research is therefore broader than any individual AI model or application feature.

The system provides a common experimental environment for investigating:

- intelligent hiking support;
- contextual awareness;
- risk prediction;
- offline artificial intelligence;
- retrieval-augmented generation;
- edge AI;
- navigation;
- emergency coordination;
- local information storage;
- decentralised information exchange;
- intermittent-connectivity operation;
- mobile-system integration.

---

# 36. Contributors

This repository is developed collaboratively as a final-year research project.

Each team member is responsible for an assigned research component while contributing to the agreed shared system architecture and integration process.

Component ownership, research responsibilities, and contributor information should be maintained according to the team's agreed project documentation.

---

# 37. License

Add the project's selected software license here once it has been formally agreed by the team.

If datasets, pretrained models, maps, or third-party resources use separate licenses, their respective terms must also be followed.
