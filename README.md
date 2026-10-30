Inspect the complete `Decentralized-Hiking-AI` repository and create/replace the root `README.md` with a comprehensive professional README for the full project.

The README must be based only on the actual repository. Do not invent dataset counts, category names, model accuracy, training results, technologies, or implementation details.

Include:

# Decentralized Hiking AI — Offline Hiking Assistant

## 1. Project Overview
Explain the problem, motivation, project objective, and why an offline AI hiking assistant is useful in areas with poor or no network connectivity.

## 2. Key Features
Document the features that actually exist, including:
- Offline question answering
- Hiking/emergency knowledge retrieval
- Local RAG
- On-device LLM generation
- Source/evidence display
- Quick emergency questions
- No cloud inference/server requirement, if confirmed by the implementation

## 3. System Architecture
Create a clear text/Mermaid architecture diagram based on the real implementation.

Explain the complete pipeline, for example:

User Question
→ Flutter UI
→ Question Processing / Router
→ Offline Knowledge Retrieval
→ SQLite Knowledge Database
→ Evidence Ranking
→ RAG Context Construction
→ Local LLM
→ Grounded Answer Validation
→ Sources
→ UI Response

Change this pipeline if the actual code works differently.

## 4. End-to-End System Workflow
Explain exactly what happens from the moment the user enters a question until the answer appears.

Include relevant classes/functions/file paths.

## 5. Technology Stack
Create a table:

Technology | Purpose | Why Used

Include only technologies actually found in the repository, such as Flutter, Dart, SQLite, GGUF, Qwen, llama.cpp/JNI/native Android components, Python, Jupyter, etc.

Explain why each technology was selected.

## 6. Project Structure
Show the actual important directory tree.

Then explain every important file individually.

Pay special attention to:
- `lib/`
- `lib/features/hiking_assistant/`
- UI/screens
- services
- models
- local LLM generation
- question router
- offline knowledge database
- RAG services
- `assets/`
- database assets
- `research/`
- datasets
- notebooks
- scripts
- Android/native integration
- `test/`

For each important file explain:
1. Purpose
2. Main classes/functions
3. Input
4. Processing
5. Output
6. How it connects to the rest of the system

## 7. Offline Knowledge Base
Inspect the actual datasets and database.

Report exact values where they can be calculated:
- Number of source datasets/files
- Number of source documents
- Number of processed records
- Number of knowledge chunks
- Number of categories
- Exact category names
- Source organizations
- Database tables
- Important columns
- Indexes/search mechanisms
- Database size if available

Do not guess any number.

## 8. The 18 Hiking Categories
If the repository really contains 18 categories, list all 18 using their exact names.

For every category explain:
- What it represents
- Example questions
- Relevant knowledge sources

If the final repository does not actually contain exactly 18 categories, state the real number instead.

## 9. Dataset Preparation
Explain the complete data pipeline:

Raw sources
→ extraction
→ cleaning
→ normalization
→ labeling
→ categorization
→ chunking
→ quality filtering
→ database construction

Reference the actual notebooks/scripts/files responsible for each stage.

## 10. RAG Architecture
Explain Retrieval-Augmented Generation in the context of this project.

Describe the actual:
- Query normalization
- Question routing
- Retrieval
- SQLite search
- FTS/fallback retrieval if implemented
- Ranking
- Filtering
- Evidence selection
- Context building
- Prompt construction
- Generation
- Grounding/validation
- Citation/source display

Explain why RAG is used instead of relying only on the LLM.

## 11. Local AI Model
Determine the exact model from the repository.

Document:
- Model family
- Exact model/version
- Parameter count
- GGUF file name
- Quantization
- Approximate model file size if determinable
- Context configuration
- Generation settings
- Runtime/inference engine
- Android integration
- Model loading lifecycle

Clearly state whether the model is:
- trained from scratch,
- fine-tuned,
- instruction-tuned pretrained model,
- converted/exported,
- quantized,
or some combination.

Do not describe quantization as fine-tuning.

## 12. Model Training / Fine-Tuning
Inspect all research notebooks and scripts.

Explain exactly what training/fine-tuning was actually performed.

If the final mobile model was NOT fine-tuned by this project, clearly say so.

Explain the difference between:
- pretraining
- fine-tuning
- quantization
- local inference
- RAG

and identify which ones this project actually uses.

## 13. Model and System Evaluation
Find all evaluation code/results.

Report only real metrics.

Possible metrics may include:
- accuracy
- precision
- recall
- F1
- retrieval accuracy
- top-k retrieval
- category routing accuracy
- answer acceptance rate
- latency
- memory
- model size

If there is no valid single “model accuracy” value, explicitly explain why rather than inventing one.

Separate:
1. Model evaluation
2. Router evaluation
3. Retrieval evaluation
4. RAG/generation evaluation
5. Mobile runtime evaluation

## 14. Why the System Works Offline
Explain exactly which components remain on the device:
- database
- retrieval
- model
- inference
- prompt/context
- response generation

Explain whether any server, cloud API, LLaMA server, Wi-Fi, or mobile data is required after installation/model provisioning.

Base this on the actual code.

## 15. Android / On-Device Inference
Explain the native integration.

Include the actual Android/JNI/native libraries and model loading flow if present.

Explain how Flutter communicates with the local model.

## 16. Quick Questions
Document the actual quick-question buttons and explain that they must pass through the normal RAG pipeline if that is what the code does.

## 17. Testing
List the actual test files.

Explain what each test verifies.

Include the latest test results only if they can be reproduced or are recorded in the repository.

Provide commands such as:

```bash
flutter pub get
flutter analyze
flutter test
```

Add any project-specific commands that actually exist.

## 18. Running the Application
Provide complete setup instructions:
- prerequisites
- Flutter version if specified
- dependencies
- database/assets
- model setup
- Android requirements
- emulator/physical device
- commands to run

Do not commit a large GGUF model to Git unless the repository already intentionally does so.

## 19. Example Questions
Provide test questions covering every real category.

Include formal and natural-language examples.

## 20. Known Limitations
Document current known issues based on code/tests/current project state, including where applicable:
- repeated-query Android crash/termination
- slow local inference
- memory/native inference lifecycle concerns
- retrieval inconsistency
- lost-hiker evidence quality
- snakebite evidence retrieved but generation/validation failure
- query wording sensitivity
- knowledge coverage gaps
- answer generation/validation inconsistencies
- malformed/poor output
- twisted-leg query producing an unhelpful/echo response
- Android SQLite FTS5 compatibility/fallback issue

Do not claim RAM is the confirmed cause of the repeated-query crash unless logs prove it. Clearly distinguish confirmed bugs from hypotheses.

## 21. Future Improvements
Include:
- repeated-inference stability
- memory profiling
- model/context lifecycle optimization
- retrieval/ranking improvements
- knowledge-base expansion
- better natural-language query normalization
- systematic 18-category evaluation
- latency optimization
- physical-device testing
- response validation improvements

## 22. Privacy and Safety
Explain local processing/privacy benefits.

Also make clear that this is a research/prototype hiking assistant and should not replace professional medical or emergency services.

## 23. Research / Academic Context
Explain the project's research contribution:
- offline-first AI
- edge AI
- local RAG
- resource-constrained LLM inference
- evidence-grounded hiking assistance

## 24. Current Project Status
State what is working, partially working, and still under development.

## 25. License / Author
Use only information actually available in the repository.

### Important rules

Before modifying `README.md`:
1. Read `git status`.
2. Read the existing README.
3. Inspect `pubspec.yaml`.
4. Inspect all relevant `lib/features/hiking_assistant` files.
5. Inspect dataset/label files.
6. Inspect research notebooks and scripts.
7. Inspect database-building code.
8. Inspect tests.
9. Inspect Android/native configuration.
10. Calculate dataset/category/chunk counts programmatically where possible.
11. Check model configuration/file names.
12. Inspect evaluation outputs.

Preserve all existing application code. Only update `README.md`.

Do not reset, revert, clean, delete, or overwrite any other uncommitted work.

After creating the README:
- show me the exact file changed;
- summarize the verified dataset/category/model facts;
- list any facts that could NOT be verified;
- run a Markdown sanity check if available;
- show `git diff -- README.md`.

The README should be detailed enough to serve both as GitHub documentation and as technical documentation for my PP1/project presentation.
