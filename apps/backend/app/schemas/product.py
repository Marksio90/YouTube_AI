import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ProductTypeStr    = Literal["ebook", "course", "template", "software", "membership", "bundle", "other"]
ProductPlatformStr = Literal["gumroad", "lemon_squeezy", "payhip", "teachable", "podia", "custom"]


# ── Product ───────────────────────────────────────────────────────────────────

class ProductRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    name: str
    description: str | None
    product_type: ProductTypeStr
    platform: ProductPlatformStr
    price_usd: float
    currency: str
    sales_page_url: str | None
    checkout_url: str | None
    thumbnail_url: str | None
    niche_tags: list[str]
    total_sales: int
    total_revenue_usd: float
    revenue_per_sale: float
    is_active: bool
    is_featured: bool
    launched_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    product_type: ProductTypeStr = "other"
    platform: ProductPlatformStr = "custom"
    price_usd: float = Field(ge=0, default=0.0)
    currency: str = Field(default="USD", max_length=3)
    sales_page_url: str | None = None
    checkout_url: str | None = None
    thumbnail_url: str | None = None
    niche_tags: list[str] = Field(default_factory=list)
    is_active: bool = True
    is_featured: bool = False
    launched_at: datetime | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    product_type: ProductTypeStr | None = None
    platform: ProductPlatformStr | None = None
    price_usd: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    sales_page_url: str | None = None
    checkout_url: str | None = None
    thumbnail_url: str | None = None
    niche_tags: list[str] | None = None
    is_active: bool | None = None
    is_featured: bool | None = None
    launched_at: datetime | None = None


# ── ProductLink ───────────────────────────────────────────────────────────────

class ProductLinkRead(BaseModel):
    publication_id: uuid.UUID
    product_id: uuid.UUID
    position: int
    description_text: str | None
    clicks: int
    sales: int
    revenue_usd: float
    cvr: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AttachProductRequest(BaseModel):
    product_id: uuid.UUID
    position: int = Field(default=0, ge=0)
    description_text: str | None = Field(default=None, max_length=500)


# ── Sale ──────────────────────────────────────────────────────────────────────

class ProductSaleRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    publication_id: uuid.UUID | None
    sold_at: datetime
    amount_usd: float
    is_mock: bool

    model_config = {"from_attributes": True}


class RecordSaleRequest(BaseModel):
    publication_id: uuid.UUID | None = None
    amount_usd: float | None = Field(default=None, ge=0)


class MockSalesRequest(BaseModel):
    count: int = Field(default=20, ge=1, le=500)
    days_back: int = Field(default=30, ge=1, le=365)


# ── Revenue reporting ─────────────────────────────────────────────────────────

class ProductRevenueSummaryRow(BaseModel):
    product_id: str
    name: str
    product_type: str
    platform: str
    price_usd: float
    period_sales: int
    period_revenue_usd: float
    revenue_trend_pct: float | None
    lifetime_sales: int
    lifetime_revenue_usd: float
    revenue_per_sale: float
    is_active: bool
    is_featured: bool


class PublicationProductRow(BaseModel):
    product_id: str
    name: str
    product_type: str
    price_usd: float
    clicks: int
    sales: int
    revenue_usd: float
    cvr_pct: float | None
    position: int
    description_text: str | None


class PublicationRevenueRead(BaseModel):
    publication_id: str
    total_sales: int
    total_revenue_usd: float
    products: list[PublicationProductRow]


class TypeBreakdownRow(BaseModel):
    product_type: str
    product_count: int
    period_sales: int
    period_revenue_usd: float
    share_pct: float


class TopProductRow(BaseModel):
    product_id: str
    name: str
    product_type: str
    period_revenue_usd: float
    period_sales: int


class ChannelRevenueRead(BaseModel):
    channel_id: str
    period_days: int
    total_revenue_usd: float
    total_sales: int
    by_type: list[TypeBreakdownRow]
    top_products: list[TopProductRow]


# ── Sales history ─────────────────────────────────────────────────────────────

class SalesHistoryRow(BaseModel):
    date: str
    sales: int
    revenue_usd: float
