import json
import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

LOG = logging.getLogger(__name__)
COLORS = ["Ocean", "Sand", "Forest"]
SIZES = ["S", "M", "L"]
STOCK = {
    ("Ocean", "S"): 8,
    ("Ocean", "M"): 1,
    ("Ocean", "L"): 5,
    ("Sand", "S"): 4,
    ("Sand", "M"): 0,
    ("Sand", "L"): 7,
    ("Forest", "M"): 3,
    ("Forest", "L"): 6,
}


class AddItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(strict=True, ge=1, le=2000)


class Failure(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = (
            status,
            code,
            message,
            details,
        )


def create_app(db_path=None):
    api = FastAPI(title="Variant Studio API", version="1.0.0")
    path = str(
        db_path or os.environ.get("DATABASE_PATH", Path(__file__).with_name("store.db"))
    )

    def connect():
        db = sqlite3.connect(path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    with closing(connect()) as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS skus(id TEXT PRIMARY KEY, color TEXT, size TEXT, price INTEGER, stock INTEGER CHECK(stock >= 0));
        CREATE TABLE IF NOT EXISTS cart(cart_id TEXT, sku_id TEXT REFERENCES skus(id), quantity INTEGER, PRIMARY KEY(cart_id, sku_id));
        CREATE TABLE IF NOT EXISTS requests(cart_id TEXT, key TEXT, fingerprint TEXT, status INTEGER, body TEXT, PRIMARY KEY(cart_id,key));
        """)
        for (color, size), stock in STOCK.items():
            db.execute(
                "INSERT OR IGNORE INTO skus VALUES(?,?,?,?,?)",
                (
                    f"{color.lower()}-{size.lower()}",
                    color,
                    size,
                    4900 + COLORS.index(color) * 500,
                    stock,
                ),
            )

        db.commit()

    @api.middleware("http")
    async def correlation(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def error(request, status, code, message, details=None):
        return JSONResponse(
            status_code=status,
            headers={"X-Request-ID": getattr(request.state, "request_id", "")},
            content={
                "error": {"code": code, "message": message, "details": details},
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @api.exception_handler(Failure)
    async def business_error(request, exc):
        return error(request, exc.status, exc.code, exc.message, exc.details)

    @api.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        details = [
            {"field": ".".join(map(str, e["loc"])), "message": e["msg"]}
            for e in exc.errors()
        ]
        return error(
            request, 422, "INVALID_INPUT", "Please check the submitted values.", details
        )

    @api.exception_handler(Exception)
    async def unexpected(request, exc):
        LOG.error(
            "Unhandled request %s (%s)",
            getattr(request.state, "request_id", None),
            type(exc).__name__,
        )
        return error(
            request, 500, "INTERNAL_ERROR", "Something went wrong. Please retry."
        )

    def cart_view(db, cart_id):
        rows = db.execute(
            "SELECT c.sku_id,c.quantity,s.price,s.color,s.size FROM cart c JOIN skus s ON c.sku_id=s.id WHERE c.cart_id=? ORDER BY c.sku_id",
            (cart_id,),
        ).fetchall()
        return {
            "items": [dict(r) for r in rows],
            "total_item_count": sum(r["quantity"] for r in rows),
            "total_price": sum(r["quantity"] * r["price"] for r in rows),
            "currency": "USD",
        }

    @api.get("/api/products/{product_id}")
    def product(product_id: str):
        if product_id != "1":
            raise Failure(404, "PRODUCT_NOT_FOUND", "Product not found.")
        with closing(connect()) as db:
            skus = [dict(r) for r in db.execute("SELECT * FROM skus ORDER BY id")]
        for sku in skus:
            sku["image"] = f"/images/{sku['color'].lower()}.svg"
        return {
            "id": "1",
            "name": "The Everyday Tee",
            "description": "A considered essential. Soft organic cotton, a relaxed fit, and colors inspired by the coast.",
            "currency": "USD",
            "options": {"color": COLORS, "size": SIZES},
            "skus": skus,
        }

    @api.get("/api/cart")
    def get_cart(x_cart_id: str = Header(min_length=1, max_length=100)):
        with closing(connect()) as db:
            return cart_view(db, x_cart_id)

    @api.post("/api/cart/items")
    def add_item(
        item: AddItem,
        idempotency_key: str = Header(min_length=1, max_length=128),
        x_cart_id: str = Header(min_length=1, max_length=100),
    ):
        fingerprint = json.dumps(item.model_dump(), sort_keys=True)
        db = connect()
        try:
            # The write lock covers replay lookup, conditional stock decrement,
            # cart update and response persistence across processes.
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT * FROM requests WHERE cart_id=? AND key=?",
                (x_cart_id, idempotency_key),
            ).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise Failure(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "This request key was used for different input.",
                    )
                return JSONResponse(
                    status_code=previous["status"],
                    content=json.loads(previous["body"]),
                    headers={"Idempotency-Replayed": "true"},
                )
            sku = db.execute("SELECT * FROM skus WHERE id=?", (item.sku_id,)).fetchone()
            if not sku:
                status, body = (
                    404,
                    {
                        "error": {
                            "code": "SKU_NOT_FOUND",
                            "message": "SKU not found.",
                            "details": None,
                        }
                    },
                )
            elif sku["stock"] < item.quantity:
                status, body = (
                    409,
                    {
                        "error": {
                            "code": "INSUFFICIENT_STOCK",
                            "message": "Stock changed. Please choose a smaller quantity.",
                            "details": {"available": sku["stock"]},
                        }
                    },
                )
            else:
                db.execute(
                    "UPDATE skus SET stock=stock-? WHERE id=? AND stock>=?",
                    (item.quantity, item.sku_id, item.quantity),
                )
                db.execute(
                    "INSERT INTO cart VALUES(?,?,?) ON CONFLICT(cart_id,sku_id) DO UPDATE SET quantity=quantity+excluded.quantity",
                    (x_cart_id, item.sku_id, item.quantity),
                )
                status, body = (
                    200,
                    {
                        "cart": cart_view(db, x_cart_id),
                        "sku_id": item.sku_id,
                        "available_quantity": sku["stock"] - item.quantity,
                    },
                )
            db.execute(
                "INSERT INTO requests VALUES(?,?,?,?,?)",
                (x_cart_id, idempotency_key, fingerprint, status, json.dumps(body)),
            )
            db.commit()
            return JSONResponse(status_code=status, content=body)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    frontend = Path(__file__).parents[1] / "frontend"
    if (frontend / "dist").exists():
        api.mount(
            "/", StaticFiles(directory=frontend / "dist", html=True), name="frontend"
        )
    return api


app = create_app()
