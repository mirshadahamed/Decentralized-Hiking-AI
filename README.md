# AI Hiking Assistant and Emergency Coordination System

A Flutter starter application for a final-year research project on intelligent hiking support, risk awareness, emergency coordination, and decentralised information sharing. The repository provides an agreed team structure only: it does not yet contain AI models, databases, integrations, or research-feature implementations.

## Project structure

```text
lib/
├── main.dart                     # Minimal application entry point
├── app/
│   ├── app.dart                  # Root application configuration
│   ├── router.dart               # Reserved for agreed navigation
│   └── theme/                    # Shared visual design
├── core/                         # Reusable constants, errors, utilities, and widgets
├── features/
│   ├── component_1/              # Team member 1 implementation
│   ├── component_2/              # Team member 2 implementation
│   ├── home/                     # Main application dashboard
│   ├── context_fusion/           # Context from Components 1, 2, and 4
│   ├── risk_prediction/          # Hiking risk prediction (Component 3)
│   ├── hiking_assistant/         # Offline hiking assistant (Component 3)
│   ├── knowledge_base/           # Offline safety and first-aid knowledge
│   ├── trail_navigation/         # GPS and trail navigation
│   ├── emergency/                # SOS and emergency coordination workflow
│   ├── event_logs/               # Local risk and emergency records
│   ├── synchronization/          # Optional online synchronization
│   └── component_4/              # Team member 4 implementation
└── shared/
    ├── models/                   # Team-agreed shared models
    ├── enums/                    # Team-agreed shared enumerations
    └── interfaces/               # Team-agreed shared interfaces

assets/
├── images/                       # UI imagery
├── models/                       # Future on-device model artefacts
├── maps/                         # Future map resources
└── knowledge/                    # Future curated knowledge resources
```

Empty directories include `.gitkeep` so the agreed architecture is retained in Git. `features/component_1`, `features/component_2`, and `features/component_4` are the designated homes for those members' implementations; there is intentionally no `integrations/` substitute layer. Component 3 remains organised by its individual features rather than a separate `component_3/` directory.

## Responsibilities and boundaries

- Build a feature in its designated `features/` directory and keep implementation details local to that feature.
- Use `shared/` only for models, enums, and interfaces the team has explicitly agreed to share.
- Place generic, non-domain-specific helpers in `core/`; put application setup, routing, and theming in `app/`.
- Add integration adapters only after a concrete interface and use case have been agreed. Do not introduce speculative APIs or data contracts.

## Prerequisites

- [Flutter](https://docs.flutter.dev/get-started/install) on the stable channel
- A configured target platform such as Android, iOS, macOS, Windows, Linux, or Chrome

Confirm your setup:

```bash
flutter doctor
```

## Getting started

```bash
git clone https://github.com/mirshadahamed/Decentralized-Hiking-AI.git
cd Decentralized-Hiking-AI
flutter pub get
flutter run
```

Run the project checks before sharing work:

```bash
flutter analyze
flutter test
```

## Team workflow

1. Update your local `main` branch, then create a focused branch such as `feature/component-1-inputs` or `feature/risk-prediction-ui`.
2. Work only within the agreed module boundary and discuss any new shared model, interface, dependency, or cross-component contract before adding it.
3. Keep credentials, local environment files, build output, generated caches, databases, and model artefacts out of Git; the repository `.gitignore` covers common cases.
4. Run `flutter pub get`, `flutter analyze`, and `flutter test` before opening a pull request.
5. Describe the affected research component, implementation scope, contract changes, and validation in the pull request. Obtain review before merging into `main`.

## Current scope

The app currently renders a minimal launch screen and establishes the shared architecture. AI inference, offline data storage, maps, networking, emergency workflows, and third-party packages are intentionally deferred until the team agrees on requirements and interfaces.
