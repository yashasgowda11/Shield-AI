from fastapi.testclient import TestClient
from backend.main import app


client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "shield-ai"


def test_contracts_list_endpoint_works():
    response = client.get("/contracts/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_query_endpoint_accepts_post():
    response = client.post("/query/", json={"question": "test"})
    assert response.status_code == 200
    body = response.json()
    assert body["question"] == "test"


def test_graph_endpoint_returns_nodes_and_edges():
    response = client.get("/graph/")
    assert response.status_code == 200
    body = response.json()
    assert "nodes" in body
    assert "edges" in body
