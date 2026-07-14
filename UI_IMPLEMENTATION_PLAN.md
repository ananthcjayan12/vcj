# Physics Production Studio — Implementation Plan

## 1. Goal

Build one repo-local control room for producing Cambridge IGCSE Physics 0625 videos topic-by-topic. The studio must make the existing curriculum tracker, question index, Physics V3 generator, scene preview, validation, MP4 renderer, and coverage registry usable without remembering terminal commands.

The studio is a manually operated production engine. It will not schedule daily jobs, publish to social platforms, or mark coverage complete without a deliberate user action.

## 2. Product principles

1. **Curriculum first:** every production run starts from a stable syllabus topic and objective set.
2. **No repetition:** current coverage, prior runs, video records, and content fingerprints are visible before generation.
3. **Grounded teaching:** generated facts packets contain syllabus objectives and aggregate assessment patterns, never copied past-paper questions.
4. **Human control:** paid generation, scene regeneration, rendering, review, and coverage changes are explicit actions.
5. **Recoverable runs:** each pipeline stage can be resumed independently from cached artifacts.
6. **Local ownership:** UI, API, registries, prompts, assets, previews, logs, and output videos remain inside this repository.

## 3. Reference interaction model

The UI follows the useful parts of the existing MAV Studio:

- persistent navigation and recent-run context;
- a focused production workspace instead of many disconnected pages;
- an eight-step pipeline with current/completed states;
- live process logs;
- preview and render actions beside the active run;
- per-scene regeneration with a director note;
- clear paid-API confirmation.

The finance-oriented discovery and template grid are replaced by syllabus coverage, objective selection, question-pattern evidence, and the fixed Physics V3 identity.

## 4. Information architecture

### 4.1 Production

- next recommended incomplete topic;
- searchable topic rail in prerequisite-aware order;
- selected topic overview and objective list;
- Core/Supplement labels and objective status;
- aggregate question count, command-word, difficulty, question-type, and visual patterns;
- lesson duration, voice provider, run ID, and paid-API confirmation;
- prepare-only and full-generate actions;
- active-run pipeline, logs, artifacts, preview, scenes, regeneration, and MP4 render.

### 4.2 Curriculum

- global topic and objective coverage;
- status distribution;
- progress grouped by syllabus domain;
- topic-level status and completion;
- deliberate status updates after review.

### 4.3 Scene library

- all 35 registered deterministic physics scenes;
- category, description, module path, parameter availability, and examples;
- filtering by name/category;
- link to the live scene-library preview.

### 4.4 Runs

- generated and in-progress runs discovered from `template_lab/runs`;
- current pipeline step and state;
- preview/MP4 availability;
- resume, inspect, render, or stop controls.

## 5. Technical architecture

### 5.1 Studio server

`studio/server.py` uses Python's standard `ThreadingHTTPServer`, so the dashboard adds no mandatory framework dependency.

Responsibilities:

- serve the dashboard and repo-local preview/render assets;
- read curriculum, coverage, asset, and video registries;
- query aggregate assessment-pattern data from the SQLite question index;
- invoke existing CLI and Template Lab scripts as subprocesses;
- persist `studio_run.json` and `studio.log` within each generated run;
- manage active processes and stop requests safely;
- expose only allow-listed run IDs, topic refs, pipeline steps, statuses, and render options;
- never expose API-key values to the browser.

### 5.2 Browser client

`studio/static/` is a dependency-free HTML/CSS/JavaScript application.

Responsibilities:

- load dashboard data and selected-topic detail;
- render responsive production, curriculum, assets, and runs views;
- call local API actions;
- poll active-run state and logs;
- embed generated V3 previews;
- present scene-level regeneration controls;
- maintain harmless UI preferences in local storage.

### 5.3 Existing systems remain authoritative

- `video_engine/curriculum/*.json`: objective identity, ordering, and coverage;
- `pilot/index_output/question_index.sqlite3`: private aggregate assessment patterns;
- `video_engine/registry/*.json`: animation, video, question, and duplication registries;
- `template_lab/scripts/mav_generate.py`: eight-stage Physics V3 generation;
- `template_lab/scripts/mav_render.py`: final MP4 rendering;
- `template_lab/runs/<run-id>/`: generated artifacts.

## 6. API surface

Read endpoints:

- `GET /api/dashboard`
- `GET /api/topics/{topic_ref}`
- `GET /api/assets`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/logs`

Mutation endpoints:

- `POST /api/topics/{topic_ref}/prepare`
- `POST /api/runs`
- `POST /api/runs/{run_id}/execute`
- `POST /api/runs/{run_id}/scenes/{scene_id}/regenerate`
- `POST /api/runs/{run_id}/render`
- `POST /api/runs/{run_id}/stop`
- `POST /api/topics/{topic_ref}/status`

Static artifact routes:

- `/artifacts/runs/{run_id}/...`
- `/scene-library/...`

## 7. Pipeline behaviour

| Step | Name | Paid boundary | Main artifacts |
|---|---|---:|---|
| 1 | Inputs | No | `input.json` |
| 2 | Script | Yes | story skeleton and narration |
| 3 | Audio | Yes | voiceover and provider report |
| 4 | Timing | No | paragraph and word timestamps |
| 5 | Scenes | Yes | V3 plan and per-scene JSON |
| 6 | Validate | No | validation and repair reports |
| 7 | Preview | No | `master_v3.html` and manifest |
| 8 | QA | Optional | generation summary and QA report |

The backend refuses steps 2, 3, or 5 unless paid APIs are explicitly confirmed. Local validation, preview rebuilding, inspection, and rendering do not require that confirmation.

## 8. Run lifecycle

`created → queued → running → completed/failed/stopped → rendering → rendered`

Each run records:

- topic reference and selected objective IDs;
- duration and provider settings;
- current step and last completed step;
- subprocess status and failure detail;
- timestamps;
- facts packet path;
- preview and render artifacts.

## 9. Safety and integrity

- Normalize and validate every run ID and topic ref.
- Resolve artifact paths and reject traversal outside allow-listed roots.
- Use argument arrays rather than shell command strings.
- Never return `.env` contents or provider keys.
- Keep paid confirmation false by default.
- Do not expose raw past-paper question text through the API.
- Require an explicit status action before marking objectives reviewed or covered.
- Preserve existing run artifacts unless the user deliberately regenerates a stage.

## 10. Verification

### Automated

- payload aggregation and topic-detail tests;
- run-ID and path-safety tests;
- pipeline command-construction tests;
- paid-boundary rejection tests;
- static-file and JSON API smoke tests;
- existing `video_engine` and `template_lab` tests.

### Browser

- desktop and narrow viewport layout;
- navigation between all four workspaces;
- topic search and selection;
- prepare-topic action;
- run selection and pipeline state rendering;
- preview iframe and artifact links;
- paid confirmation gating;
- no console errors or failed local resources.

## 11. Delivery phases

### Phase 1 — operational studio (this implementation)

- curriculum dashboard;
- topic preparation;
- generation/resume/stop controls;
- live logs through polling;
- preview and render;
- scene regeneration;
- coverage updates;
- asset browser;
- responsive UI and automated tests.

### Phase 2 — editorial refinement

- edit narration paragraphs inside the studio;
- compare regenerated scene versions;
- visual QA thumbnails at selected timestamps;
- objective-to-scene traceability;
- explicit review checklist and approval record.

### Phase 3 — publishing support

- title, description, chapter, thumbnail, and short-form derivative drafting;
- exportable upload package;
- publishing history entered manually after upload;
- performance feedback linked to future reinforcement videos.

Publishing remains manual unless a later, separately approved integration is built.
