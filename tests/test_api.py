from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.backend.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.db")) as c:
        yield c


def headers(key="one", cart="cart-a"):
    return {"Idempotency-Key": key, "X-Cart-ID": cart}


def test_product_and_cart(client):
    data = client.get("/api/products/1").json()
    assert len(data["skus"]) == 8
    assert any(s["stock"] == 0 for s in data["skus"])
    assert client.get("/api/products/missing").status_code == 404
    assert client.get("/api/cart", headers=headers()).json()["total_item_count"] == 0
    r = client.post(
        "/api/cart/items", headers=headers(), json={"sku_id": "ocean-s", "quantity": 2}
    )
    assert r.status_code == 200
    assert r.json()["cart"]["total_item_count"] == 2
    assert r.json()["available_quantity"] == 6
    assert (
        client.get("/api/cart", headers=headers(cart="other")).json()[
            "total_item_count"
        ]
        == 0
    )


def test_validation_and_replay(client):
    for qty in [0, -1, 1.5, True, "1"]:
        r = client.post(
            "/api/cart/items",
            headers=headers(),
            json={"sku_id": "ocean-s", "quantity": qty},
        )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INVALID_INPUT"
    body = {"sku_id": "ocean-s", "quantity": 2}
    first = client.post("/api/cart/items", headers=headers(), json=body)
    second = client.post("/api/cart/items", headers=headers(), json=body)
    assert first.json() == second.json()
    assert second.headers["Idempotency-Replayed"] == "true"
    assert (
        client.post(
            "/api/cart/items", headers=headers(), json={**body, "quantity": 1}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/cart/items",
            headers=headers("missing"),
            json={"sku_id": "missing", "quantity": 1},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/cart/items",
            headers=headers("empty"),
            json={"sku_id": "sand-m", "quantity": 1},
        ).status_code
        == 409
    )


def test_last_unit_concurrency(client):
    def buy(i):
        return client.post(
            "/api/cart/items",
            headers=headers(str(i), str(i)),
            json={"sku_id": "ocean-m", "quantity": 1},
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(buy, range(8)))
    assert statuses.count(200) == 1
    assert statuses.count(409) == 7
    assert (
        next(
            s
            for s in client.get("/api/products/1").json()["skus"]
            if s["id"] == "ocean-m"
        )["stock"]
        == 0
    )


def test_concurrent_same_key(client):
    def buy(_):
        return client.post(
            "/api/cart/items",
            headers=headers(),
            json={"sku_id": "ocean-s", "quantity": 1},
        ).json()

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(buy, range(5)))
    assert all(r == results[0] for r in results)
    assert client.get("/api/cart", headers=headers()).json()["total_item_count"] == 1


def test_unexpected_failure_is_structured(tmp_path):
    import sqlite3

    path = tmp_path / "broken.db"
    app = create_app(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE cart")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/cart", headers=headers())
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "DROP" not in response.text and "sqlite" not in response.text
