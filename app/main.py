"""
Scaffale API
============
Un'API REST per catalogare libri, film e serie TV: cosa hai letto/visto,
cosa vuoi ancora recuperare, con quale voto lo ricordi.

Documentazione interattiva generata automaticamente da FastAPI su /docs.
"""

from datetime import date
from enum import Enum
from typing import List, Optional

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from sqlmodel import Field, Session, SQLModel, create_engine, select


# ---------------------------------------------------------------------------
# Modelli
# ---------------------------------------------------------------------------

class MediaType(str, Enum):
    libro = "libro"
    film = "film"
    serie = "serie"


class Status(str, Enum):
    da_iniziare = "da_iniziare"
    in_corso = "in_corso"
    completato = "completato"


class ItemBase(SQLModel):
    title: str = Field(index=True, description="Titolo del libro, film o serie")
    type: MediaType = Field(description="Tipo di contenuto")
    creator: Optional[str] = Field(default=None, description="Autore o regista")
    status: Status = Field(default=Status.da_iniziare, description="Stato di avanzamento")
    rating: Optional[int] = Field(default=None, ge=1, le=5, description="Voto da 1 a 5")
    notes: Optional[str] = Field(default=None, description="Note personali")


class Item(ItemBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    added_on: date = Field(default_factory=date.today)


class ItemCreate(ItemBase):
    pass


class ItemUpdate(SQLModel):
    title: Optional[str] = None
    type: Optional[MediaType] = None
    creator: Optional[str] = None
    status: Optional[Status] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASE_URL = "sqlite:///./catalogo.db"
connect_args = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Scaffale API",
    description=(
        "Un catalogo personale di libri, film e serie TV. "
        "Aggiungi titoli, segna cosa hai completato, dai un voto e ritrova tutto quando vuoi."
    ),
    version="1.0.0",
    docs_url=None,  # sostituito da un endpoint che serve gli asset in locale (vedi sotto)
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/docs", include_in_schema=False)
def custom_swagger_ui_html():
    # Gli asset di Swagger UI sono serviti localmente (non da CDN esterni),
    # così la documentazione interattiva funziona anche offline o dietro proxy restrittivi.
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} — Documentazione",
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
        swagger_favicon_url="/static/favicon-32x32.png",
    )


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()


@app.get("/", tags=["Info"])
def root() -> dict:
    return {
        "name": "Scaffale API",
        "description": "Catalogo personale di libri, film e serie TV",
        "docs": "/docs",
        "endpoints": ["/items", "/items/{id}", "/stats"],
    }


@app.post("/items", response_model=Item, status_code=201, tags=["Items"])
def create_item(item: ItemCreate) -> Item:
    with Session(engine) as session:
        db_item = Item.model_validate(item)
        session.add(db_item)
        session.commit()
        session.refresh(db_item)
        return db_item


@app.get("/items", response_model=List[Item], tags=["Items"])
def list_items(
    type: Optional[MediaType] = None,
    status: Optional[Status] = None,
    q: Optional[str] = Query(default=None, description="Cerca nel titolo"),
) -> List[Item]:
    with Session(engine) as session:
        query = select(Item)
        if type:
            query = query.where(Item.type == type)
        if status:
            query = query.where(Item.status == status)
        if q:
            query = query.where(Item.title.contains(q))
        return list(session.exec(query).all())


@app.get("/items/{item_id}", response_model=Item, tags=["Items"])
def get_item(item_id: int) -> Item:
    with Session(engine) as session:
        item = session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        return item


@app.put("/items/{item_id}", response_model=Item, tags=["Items"])
def update_item(item_id: int, item_update: ItemUpdate) -> Item:
    with Session(engine) as session:
        item = session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        data = item_update.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(item, key, value)
        session.add(item)
        session.commit()
        session.refresh(item)
        return item


@app.delete("/items/{item_id}", status_code=204, tags=["Items"])
def delete_item(item_id: int) -> None:
    with Session(engine) as session:
        item = session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        session.delete(item)
        session.commit()


@app.get("/stats", tags=["Info"])
def stats() -> dict:
    with Session(engine) as session:
        items = list(session.exec(select(Item)).all())
        by_type: dict = {}
        by_status: dict = {}
        for i in items:
            by_type[i.type] = by_type.get(i.type, 0) + 1
            by_status[i.status] = by_status.get(i.status, 0) + 1
        rated = [i.rating for i in items if i.rating is not None]
        avg_rating = round(sum(rated) / len(rated), 2) if rated else None
        return {
            "totale": len(items),
            "per_tipo": by_type,
            "per_stato": by_status,
            "voto_medio": avg_rating,
        }
