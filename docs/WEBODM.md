# WebODM round trip

This optional integration uploads a session's usable source images to WebODM, reports the
remote task state, supports cancellation, and saves completed mapping assets under the configured
`exports_dir` at `webodm/<project_id>/<task_id>/`. It does not retain WebODM credentials. Local
COLMAP reconstructions continue to use the persistent job queue; a WebODM task is remote and is
submitted directly to its server.

## Configure

Set a WebODM server origin and enable the integration in `config.yaml`. HTTPS is required by
default; an isolated development deployment can deliberately opt in to HTTP.

```yaml
webodm:
  enabled: true
  url: "https://webodm.example"
  jwt_env: "WEBODM_JWT"
```

Put the JWT in the named environment variable before starting the backend. Obtain it from your
WebODM account/API; never place it in YAML, requests, or documentation. The server validates that
the URL is an origin (not an `/api` path), and returns `422` with an actionable message when the
integration is disabled, the URL is unsafe, or the JWT is absent.

## Workflow

1. Import a session with at least two usable image files and inspect `GET /reconstruction/backends`.
   It always reports local `colmap`; `webodm` is available only after the opt-in configuration and
   environment variable above pass validation.
2. Start the selected backend using `POST /reconstruction/start`. Omitting `backend` preserves the
   local `colmap` workflow. Send `{"session_id": 42, "backend": "webodm",
   "webodm_options": [{"name":"orthophoto-resolution","value":24}]}` to submit one session
   to WebODM. The response includes `project_id`, `task_id`, `status_url`, and `results_url`.
   WebODM does not support multi-session, target-area, or lineage reruns through this route; use
   local COLMAP for those workflows.
3. The original explicit API remains available: `POST /webodm/sessions/{session_id}/tasks` with
   optional `project_name`, `task_name`, and
   WebODM `options` (`[{"name":"orthophoto-resolution","value":24}]`). This creates a WebODM
   project and multipart task, returning numeric `project_id` and `task_id`.
4. Poll `GET /webodm/projects/{project_id}/tasks/{task_id}`. It maps WebODM statuses `10`, `20`,
   `30`, and `40` to queued, running, failed, and completed, including progress/error fields.
5. If needed, `POST /webodm/projects/{project_id}/tasks/{task_id}/cancel`; WebODM accepts the
   cancellation asynchronously.
6. Once status is completed, `POST /webodm/projects/{project_id}/tasks/{task_id}/results`.
   By default it downloads available `orthophoto.tif`, `georeferenced_model.las`, and
   `georeferenced_model.ply`; pass `{"assets":[...]}` to choose from the task's
   `available_assets`. A missing requested asset returns `422`; an unfinished task returns `409`.

The API follows the documented WebODM endpoints: `POST /api/projects/`, multipart
`POST /api/projects/{project_id}/tasks/`, `GET /api/projects/{project_id}/tasks/{task_id}/`,
`POST .../cancel/`, and `GET .../download/{asset}`. See the
[WebODM API quickstart](https://docs.webodm.org/api/quickstart/) and
[Task API](https://docs.webodm.org/api/task/) for the upstream contract.
