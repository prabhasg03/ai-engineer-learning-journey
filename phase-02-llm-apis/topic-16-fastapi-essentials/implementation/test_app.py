"""pytest tests for the Topic 16 invoice service.

Run from this directory: ``python -m pytest``

The tests import the service from ``app.py`` and exercise the FastAPI app via
``TestClient``. The store is reset between tests to keep them order-independent.
"""

import pytest
from fastapi.testclient import TestClient

import app as service
from app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_store():
    """Give every test a clean store so they are order-independent."""
    service.reset_state()
    yield


def test_create_invoice():
    response = client.post(
        "/invoices",
        json={"invoice_number": "INV-001", "vendor": "Acme Corp", "total": 1234.56},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["invoice_number"] == "INV-001"
    assert body["vendor"] == "Acme Corp"
    assert body["total"] == 1234.56
    assert body["id"] == 1


def test_create_invoice_rejects_negative_total():
    response = client.post(
        "/invoices",
        json={"invoice_number": "INV-BAD", "vendor": "Acme Corp", "total": -5},
    )
    assert response.status_code == 422


def test_read_invoice():
    created = client.post(
        "/invoices",
        json={"invoice_number": "INV-002", "vendor": "Widgets Inc", "total": 99.0},
    )
    invoice_id = created.json()["id"]
    response = client.get(f"/invoices/{invoice_id}")
    assert response.status_code == 200
    assert response.json()["invoice_number"] == "INV-002"


def test_read_invoice_not_found():
    response = client.get("/invoices/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Invoice not found"


def test_list_invoices_with_query_params():
    for i in range(3):
        client.post(
            "/invoices",
            json={
                "invoice_number": f"INV-10{i}",
                "vendor": f"Vendor {i}",
                "total": 10.0 * (i + 1),
            },
        )
    response = client.get("/invoices", params={"skip": 1, "limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["invoice_number"] == "INV-101"


def test_update_invoice_partial():
    created = client.post(
        "/invoices",
        json={"invoice_number": "INV-003", "vendor": "Old Vendor", "total": 50.0},
    )
    invoice_id = created.json()["id"]
    response = client.patch(f"/invoices/{invoice_id}", json={"total": 75.0})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 75.0
    assert body["vendor"] == "Old Vendor"


def test_delete_invoice():
    created = client.post(
        "/invoices",
        json={"invoice_number": "INV-DELETE", "vendor": "Temp", "total": 5.0},
    )
    invoice_id = created.json()["id"]
    assert client.delete(f"/invoices/{invoice_id}").status_code == 204
    assert client.get(f"/invoices/{invoice_id}").status_code == 404


def test_docs_and_openapi_available():
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/invoices" in schema["paths"]
