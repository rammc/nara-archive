"""HTTP-level tests for /api/jobs (lifespan-aware)."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from actari.config import Config
from actari.jobs import JobManager
from actari.server import create_app


def _config(tmp_path: Path) -> Config:
    return Config(
        api_key="fake-key",
        api_base_url="https://example.test/api/v2/",
        default_rate=0.0,
        output_dir=tmp_path,
        server_host="127.0.0.1",
        server_port=8765,
        auto_open_browser=False,
        config_path=None,
        terms_acknowledged=True,
        acknowledged_at="2026-05-16T00:00:00Z",
    )


def _runners():
    def fetch_and_persist(parent_naid, paths, *, limit, client):
        return {
            "source": {"parent_naid": parent_naid},
            "file_units": [{"naid": "U", "digital_object_count": 0, "digital_objects": []}],
        }

    def download_all(
        paths,
        *,
        rate,
        client,
        metadata,
        progress_callback=None,
        cancel_event=None,
        show_progress_bars=False,
    ):
        return {"downloaded": 0, "skipped": 0, "failed": 0}

    def build_pdfs(
        paths,
        *,
        metadata,
        force=False,
        recompress=False,
        ocr=False,
        ocr_language="eng+deu",
        progress_callback=None,
        cancel_event=None,
        show_progress_bars=False,
    ):
        return [{"naid": "U", "status": "ok", "pdf_path": "pdfs/x.pdf"}]

    return {
        "fetch_and_persist": fetch_and_persist,
        "download_all": download_all,
        "build_pdfs": build_pdfs,
        "write_manifest": lambda *a, **kw: {},
        "make_client": lambda cfg: object(),
        "apply_filter": lambda paths, **kw: (
            paths.root / "metadata-x.json",
            {"filter": {"total_source_count": 0, "matched_count": 0}, "file_units": []},
        ),
    }


def _app_with_mocked_manager(tmp_path):
    """Create an app where the lifespan installs a JobManager with mocked runners."""
    from contextlib import asynccontextmanager

    cfg = _config(tmp_path)
    runners = _runners()

    @asynccontextmanager
    async def fake_lifespan(app):
        manager = JobManager(config=cfg, runners=runners)
        await manager.startup()
        app.state.jobs = manager
        try:
            yield
        finally:
            await manager.shutdown()

    # Build the real app, then swap its router_lifespan-stored state by
    # constructing fresh via create_app and overriding state in startup.
    app = create_app(cfg)
    # Force lifespan replacement by re-attaching. FastAPI stores lifespan on
    # router; easiest path is just to reuse the real one with mocked runners
    # via dependency injection at the JobManager level. We do that by
    # monkey-patching DEFAULT_RUNNERS for the duration of the test.
    return app, runners


def test_full_jobs_lifecycle(tmp_path, monkeypatch):
    # Patch the manager factory so any JobManager created inside the lifespan
    # gets the fast runners instead of the real downloader / pdfbuild.
    import actari.jobs as jobs_mod

    monkeypatch.setattr(jobs_mod, "DEFAULT_RUNNERS", _runners())

    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        # Empty list initially.
        r = c.get("/api/jobs")
        assert r.status_code == 200
        assert r.json() == {"jobs": []}

        # Create a job.
        r = c.post("/api/jobs", json={"parent_naid": "7840517", "name": "smoke", "rate": 0.01})
        assert r.status_code == 201, r.text
        job = r.json()
        job_id = job["job_id"]
        assert job["status"] == "queued"
        assert job["parent_naid"] == "7840517"

        # Wait for completion.
        deadline = time.time() + 5
        final = None
        while time.time() < deadline:
            final = c.get(f"/api/jobs/{job_id}").json()
            if final["status"] == "done":
                break
            time.sleep(0.05)
        assert final and final["status"] == "done", final

        # Restart yields a new job.
        r = c.post(f"/api/jobs/{job_id}/restart")
        assert r.status_code == 201
        new_id = r.json()["job_id"]
        assert new_id != job_id

        # Wait for the restarted job to finish so we can delete cleanly.
        deadline = time.time() + 5
        while time.time() < deadline:
            if c.get(f"/api/jobs/{new_id}").json()["status"] == "done":
                break
            time.sleep(0.05)

        # DELETE on a terminal job → 204 + removed.
        r = c.delete(f"/api/jobs/{new_id}")
        assert r.status_code == 204, r.text
        assert c.get(f"/api/jobs/{new_id}").status_code == 404


def test_delete_unknown_returns_404(tmp_path, monkeypatch):
    import actari.jobs as jobs_mod

    monkeypatch.setattr(jobs_mod, "DEFAULT_RUNNERS", _runners())
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        r = c.delete("/api/jobs/does-not-exist")
        assert r.status_code == 404


def test_post_validation_filter_requires_name(tmp_path, monkeypatch):
    import actari.jobs as jobs_mod

    monkeypatch.setattr(jobs_mod, "DEFAULT_RUNNERS", _runners())
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        r = c.post("/api/jobs", json={"parent_naid": "X", "filter_query": "x"})
        assert r.status_code == 400
        assert "name is required" in r.json()["detail"]
