"""
Digital Products API.

Routes:
  # Products
  GET    /channels/{id}/products                     list products
  POST   /channels/{id}/products                     create product
  GET    /channels/{id}/products/{pid}               get product
  PATCH  /channels/{id}/products/{pid}               update product
  DELETE /channels/{id}/products/{pid}               delete product
  GET    /channels/{id}/products/revenue             channel revenue overview
  GET    /channels/{id}/products/revenue/summary     per-product breakdown

  # Sales
  POST   /products/{pid}/sales                       record sale (webhook / manual)
  POST   /products/{pid}/mock-sales                  seed mock sales
  GET    /products/{pid}/sales/history               daily sales history

  # Publication attachment
  GET    /publications/{id}/products                 list products on video
  POST   /publications/{id}/products                 attach product to video
  DELETE /publications/{id}/products/{pid}           detach product from video
  GET    /publications/{id}/products/revenue         per-video product revenue
  POST   /publications/{id}/products/{pid}/click     record product page click
"""
import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.repositories.channel import ChannelRepository
from app.schemas.product import (
    AttachProductRequest,
    ChannelRevenueRead,
    MockSalesRequest,
    ProductCreate,
    ProductLinkRead,
    ProductRead,
    ProductRevenueSummaryRow,
    ProductSaleRead,
    ProductUpdate,
    PublicationRevenueRead,
    RecordSaleRequest,
    SalesHistoryRow,
)
from app.services.product import ProductService

router = APIRouter(tags=["products"])


async def _owned_channel(channel_id: uuid.UUID, user_id: uuid.UUID, db) -> None:
    channel = await ChannelRepository(db).get_owned(channel_id, owner_id=user_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")


# ── Products ──────────────────────────────────────────────────────────────────

@router.get(
    "/channels/{channel_id}/products",
    response_model=list[ProductRead],
    summary="List digital products for a channel",
)
async def list_products(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    product_type: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    featured_only: bool = Query(default=False),
) -> list[ProductRead]:
    await _owned_channel(channel_id, current_user.id, db)
    svc = ProductService(db)
    from app.db.models.product import ProductType
    type_enum = ProductType(product_type) if product_type else None
    products = await svc.list_products(
        channel_id,
        product_type=type_enum,
        active_only=active_only,
        featured_only=featured_only,
    )
    return [ProductRead.model_validate(p) for p in products]


@router.post(
    "/channels/{channel_id}/products",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a digital product",
)
async def create_product(
    channel_id: uuid.UUID,
    payload: ProductCreate,
    current_user: CurrentUser,
    db: DB,
) -> ProductRead:
    await _owned_channel(channel_id, current_user.id, db)
    svc = ProductService(db)
    product = await svc.create_product(
        channel_id=channel_id,
        data=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    await db.refresh(product)
    return ProductRead.model_validate(product)


@router.get(
    "/channels/{channel_id}/products/revenue",
    response_model=ChannelRevenueRead,
    summary="Channel-level product revenue by type",
)
async def channel_revenue(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(default=30, ge=7, le=365),
) -> ChannelRevenueRead:
    await _owned_channel(channel_id, current_user.id, db)
    svc = ProductService(db)
    data = await svc.channel_revenue(channel_id, days=days)
    return ChannelRevenueRead.model_validate(data)


@router.get(
    "/channels/{channel_id}/products/revenue/summary",
    response_model=list[ProductRevenueSummaryRow],
    summary="Per-product revenue breakdown",
)
async def revenue_summary(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(default=30, ge=7, le=365),
    include_mock: bool = Query(default=True),
) -> list[ProductRevenueSummaryRow]:
    await _owned_channel(channel_id, current_user.id, db)
    svc = ProductService(db)
    rows = await svc.revenue_summary(channel_id, days=days, include_mock=include_mock)
    return [ProductRevenueSummaryRow.model_validate(r) for r in rows]


@router.get(
    "/channels/{channel_id}/products/{product_id}",
    response_model=ProductRead,
    summary="Get a product",
)
async def get_product(
    channel_id: uuid.UUID,
    product_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> ProductRead:
    await _owned_channel(channel_id, current_user.id, db)
    svc = ProductService(db)
    product = await svc.get_product(product_id)
    if not product or product.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductRead.model_validate(product)


@router.patch(
    "/channels/{channel_id}/products/{product_id}",
    response_model=ProductRead,
    summary="Update a product",
)
async def update_product(
    channel_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ProductUpdate,
    current_user: CurrentUser,
    db: DB,
) -> ProductRead:
    await _owned_channel(channel_id, current_user.id, db)
    svc = ProductService(db)
    product = await svc.update_product(product_id, payload.model_dump(exclude_none=True))
    if not product or product.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.commit()
    await db.refresh(product)
    return ProductRead.model_validate(product)


@router.delete(
    "/channels/{channel_id}/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product",
)
async def delete_product(
    channel_id: uuid.UUID,
    product_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    await _owned_channel(channel_id, current_user.id, db)
    svc = ProductService(db)
    product = await svc.get_product(product_id)
    if not product or product.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Product not found")
    await svc.delete_product(product_id)
    await db.commit()


# ── Sales ─────────────────────────────────────────────────────────────────────

@router.post(
    "/products/{product_id}/sales",
    response_model=ProductSaleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a sale (webhook or manual entry)",
)
async def record_sale(
    product_id: uuid.UUID,
    payload: RecordSaleRequest,
    db: DB,
) -> ProductSaleRead:
    svc = ProductService(db)
    try:
        sale = await svc.record_sale(
            product_id,
            publication_id=payload.publication_id,
            amount_usd=payload.amount_usd,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await db.commit()
    await db.refresh(sale)
    return ProductSaleRead.model_validate(sale)


@router.post(
    "/channels/{channel_id}/products/{product_id}/mock-sales",
    summary="Seed mock sale events for development",
)
async def seed_mock_sales(
    channel_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: MockSalesRequest,
    current_user: CurrentUser,
    db: DB,
) -> dict:
    await _owned_channel(channel_id, current_user.id, db)
    svc = ProductService(db)
    product = await svc.get_product(product_id)
    if not product or product.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Product not found")
    count = await svc.generate_mock_sales(
        product_id, count=payload.count, days_back=payload.days_back
    )
    await db.commit()
    return {"seeded": count}


@router.get(
    "/channels/{channel_id}/products/{product_id}/sales/history",
    response_model=list[SalesHistoryRow],
    summary="Daily sales history for chart rendering",
)
async def sales_history(
    channel_id: uuid.UUID,
    product_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(default=30, ge=7, le=365),
    include_mock: bool = Query(default=True),
) -> list[SalesHistoryRow]:
    await _owned_channel(channel_id, current_user.id, db)
    svc = ProductService(db)
    product = await svc.get_product(product_id)
    if not product or product.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Product not found")
    rows = await svc.sales_history(product_id, days=days, include_mock=include_mock)
    return [SalesHistoryRow.model_validate(r) for r in rows]


# ── Publication attachment ────────────────────────────────────────────────────

@router.get(
    "/publications/{publication_id}/products",
    response_model=list[ProductLinkRead],
    summary="List products attached to a publication",
)
async def list_publication_products(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> list[ProductLinkRead]:
    svc = ProductService(db)
    links = await svc.list_publication_products(publication_id)
    return [ProductLinkRead.model_validate(l) for l in links]


@router.post(
    "/publications/{publication_id}/products",
    response_model=ProductLinkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a product to a publication",
)
async def attach_product(
    publication_id: uuid.UUID,
    payload: AttachProductRequest,
    current_user: CurrentUser,
    db: DB,
) -> ProductLinkRead:
    svc = ProductService(db)
    pl = await svc.attach_product(
        publication_id=publication_id,
        product_id=payload.product_id,
        position=payload.position,
        description_text=payload.description_text,
    )
    await db.commit()
    await db.refresh(pl)
    return ProductLinkRead.model_validate(pl)


@router.delete(
    "/publications/{publication_id}/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a product from a publication",
)
async def detach_product(
    publication_id: uuid.UUID,
    product_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    svc = ProductService(db)
    removed = await svc.detach_product(
        publication_id=publication_id, product_id=product_id
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Attachment not found")
    await db.commit()


@router.get(
    "/publications/{publication_id}/products/revenue",
    response_model=PublicationRevenueRead,
    summary="Per-video product revenue breakdown",
)
async def publication_revenue(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> PublicationRevenueRead:
    svc = ProductService(db)
    data = await svc.publication_revenue(publication_id)
    return PublicationRevenueRead.model_validate(data)


@router.post(
    "/publications/{publication_id}/products/{product_id}/click",
    summary="Record a product page click from a publication",
)
async def record_click(
    publication_id: uuid.UUID,
    product_id: uuid.UUID,
    db: DB,
) -> dict:
    svc = ProductService(db)
    pl = await svc.record_click(
        publication_id=publication_id, product_id=product_id
    )
    await db.commit()
    if not pl:
        raise HTTPException(status_code=404, detail="Product not attached to publication")
    return {"clicks": pl.clicks}
