"""On-demand run-request queue (the dashboard 'Run now' button → local poller)."""

from boardroom.persistence.repository import InMemoryRepository


def test_claim_returns_none_when_empty():
    repo = InMemoryRepository()
    assert repo.claim_next_run_request() is None


def test_claim_then_complete_lifecycle():
    repo = InMemoryRepository()
    repo.run_requests.append({"id": 1, "status": "pending", "source": "dashboard"})

    claimed = repo.claim_next_run_request()
    assert claimed is not None
    assert claimed["id"] == 1
    # The stored row is now 'running' so a second poller can't grab it.
    assert repo.run_requests[0]["status"] == "running"
    assert repo.claim_next_run_request() is None

    repo.complete_run_request(1, "done", {"kind": "hold"}, decision_id="abc")
    assert repo.run_requests[0]["status"] == "done"
    assert repo.run_requests[0]["result"] == {"kind": "hold"}
    assert repo.run_requests[0]["decision_id"] == "abc"


def test_claims_oldest_first():
    repo = InMemoryRepository()
    repo.run_requests.append({"id": 1, "status": "done", "source": "dashboard"})
    repo.run_requests.append({"id": 2, "status": "pending", "source": "dashboard"})
    repo.run_requests.append({"id": 3, "status": "pending", "source": "dashboard"})

    claimed = repo.claim_next_run_request()
    assert claimed["id"] == 2  # first pending in order
