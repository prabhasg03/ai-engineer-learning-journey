"""Topic 16 - Mini Invoice Tracker.

A small FastAPI service: typed routes, one dependency, Pydantic request/response
models, explicit status codes, and automatic OpenAPI docs.

The service lives in a module (rather than only inside the notebook) so that
test_app.py can import it and ``python -m pytest`` can collect the tests.
The notebook fastapi_essentials.ipynb imports this module.
"""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

app = FastAPI(title="Mini Invoice Tracker", version="0.1.0")

# In-memory store: id -> invoice dict.
invoices_db: dict[int, dict] = {}
next_id = 1


class InvoiceBase(BaseModel):
    """Fields shared by create and read."""

    invoice_number: str = Field(min_length=1)
    vendor: str = Field(min_length=1)
    total: float = Field(gt=0)


class InvoiceCreate(InvoiceBase):
    """Request body for POST /invoices."""


class InvoiceOut(InvoiceBase):
    """Response body: shared fields plus the assigned id."""

    id: int


class InvoiceUpdate(BaseModel):
    """Request body for PATCH /invoices/{id}. Absent fields stay unchanged."""

    invoice_number: str | None = None
    vendor: str | None = None
    total: float | None = Field(default=None, gt=0)


def get_invoice_store() -> dict[int, dict]:
    """Dependency that hands the route the shared store."""
    return invoices_db


# Annotated[dict, Depends(...)] is the modern way to declare a dependency.
StoreDep = Annotated[dict[int, dict], Depends(get_invoice_store)]


def reset_state() -> None:
    """Clear the store so tests and demos start from a known state."""
    global next_id
    invoices_db.clear()
    next_id = 1


@app.post("/invoices", status_code=status.HTTP_201_CREATED, response_model=InvoiceOut)
async def create_invoice(invoice: InvoiceCreate, store: StoreDep) -> InvoiceOut:
    global next_id
    invoice_id = next_id
    next_id += 1
    entry = {"id": invoice_id, **invoice.model_dump()}
    store[invoice_id] = entry
    return InvoiceOut(**entry)


@app.get("/invoices/{invoice_id}", response_model=InvoiceOut)
async def read_invoice(invoice_id: int, store: StoreDep) -> InvoiceOut:
    if invoice_id not in store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )
    return InvoiceOut(**store[invoice_id])


@app.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(
    store: StoreDep, skip: int = 0, limit: int = 10
) -> list[InvoiceOut]:
    items = list(store.values())[skip : skip + limit]
    return [InvoiceOut(**item) for item in items]


@app.patch("/invoices/{invoice_id}", response_model=InvoiceOut)
async def update_invoice(
    invoice_id: int, update: InvoiceUpdate, store: StoreDep
) -> InvoiceOut:
    if invoice_id not in store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )
    stored = store[invoice_id]
    stored.update(update.model_dump(exclude_unset=True))
    return InvoiceOut(**stored)


@app.delete("/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(invoice_id: int, store: StoreDep) -> None:
    if invoice_id not in store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )
    del store[invoice_id]
