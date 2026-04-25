"""
ProductService — digital product CRUD, publication attachment,
mock sale seeding, and revenue reporting.

Revenue tracking
────────────────
  record_sale()        logs ProductSale event; bumps Product lifetime counters
                       and per-video ProductLink counters.
  generate_mock_sales() seeds realistic time-series events (dev / demo).

Revenue reporting
─────────────────
  revenue_summary()    per-product breakdown: sales, revenue, RPM, trend.
  publication_revenue() all products + totals for a single video.
  channel_revenue()    rolled-up channel-level totals by product type.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import Product, ProductLink, ProductSale, ProductType

log = structlog.get_logger(__name__)

# Mock conversion rate: ~0.5% of publication views buy a product
_MOCK_CVR = 0.005
# Mock click-through from description to product page
_MOCK_CTR = 0.02


def _seed_float(product_id: uuid.UUID, suffix: str) -> float:
    raw = hashlib.md5(f"{product_id}:{suffix}".encode()).hexdigest()
    return int(raw[:8], 16) / 0xFFFFFFFF


class ProductService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Product CRUD ──────────────────────────────────────────────────────────

    async def list_products(
        self,
        channel_id: uuid.UUID,
        *,
        product_type: ProductType | None = None,
        active_only: bool = True,
        featured_only: bool = False,
        limit: int = 100,
    ) -> list[Product]:
        q = select(Product).where(Product.channel_id == channel_id)
        if product_type:
            q = q.where(Product.product_type == product_type)
        if active_only:
            q = q.where(Product.is_active.is_(True))
        if featured_only:
            q = q.where(Product.is_featured.is_(True))
        q = q.order_by(Product.total_revenue_usd.desc()).limit(limit)
        return list((await self._db.execute(q)).scalars().all())

    async def get_product(self, product_id: uuid.UUID) -> Product | None:
        return (
            await self._db.execute(
                select(Product).where(Product.id == product_id)
            )
        ).scalar_one_or_none()

    async def create_product(
        self, *, channel_id: uuid.UUID, data: dict[str, Any]
    ) -> Product:
        product = Product(channel_id=channel_id, **data)
        self._db.add(product)
        await self._db.flush()
        return product

    async def update_product(
        self, product_id: uuid.UUID, data: dict[str, Any]
    ) -> Product | None:
        product = await self.get_product(product_id)
        if not product:
            return None
        for k, v in data.items():
            setattr(product, k, v)
        return product

    async def delete_product(self, product_id: uuid.UUID) -> bool:
        product = await self.get_product(product_id)
        if not product:
            return False
        await self._db.delete(product)
        return True

    # ── Publication attachment ─────────────────────────────────────────────────

    async def attach_product(
        self,
        *,
        publication_id: uuid.UUID,
        product_id: uuid.UUID,
        position: int = 0,
        description_text: str | None = None,
    ) -> ProductLink:
        existing = (
            await self._db.execute(
                select(ProductLink).where(
                    ProductLink.publication_id == publication_id,
                    ProductLink.product_id == product_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.position = position
            if description_text is not None:
                existing.description_text = description_text
            return existing

        pl = ProductLink(
            publication_id=publication_id,
            product_id=product_id,
            position=position,
            description_text=description_text,
        )
        self._db.add(pl)
        await self._db.flush()
        return pl

    async def detach_product(
        self, *, publication_id: uuid.UUID, product_id: uuid.UUID
    ) -> bool:
        result = await self._db.execute(
            delete(ProductLink).where(
                ProductLink.publication_id == publication_id,
                ProductLink.product_id == product_id,
            )
        )
        return result.rowcount > 0

    async def list_publication_products(
        self, publication_id: uuid.UUID
    ) -> list[ProductLink]:
        q = (
            select(ProductLink)
            .where(ProductLink.publication_id == publication_id)
            .order_by(ProductLink.position)
        )
        return list((await self._db.execute(q)).scalars().all())

    # ── Sale recording ────────────────────────────────────────────────────────

    async def record_sale(
        self,
        product_id: uuid.UUID,
        *,
        publication_id: uuid.UUID | None = None,
        amount_usd: float | None = None,
        is_mock: bool = False,
    ) -> ProductSale:
        product = await self.get_product(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        sale_amount = amount_usd if amount_usd is not None else product.price_usd

        sale = ProductSale(
            product_id=product_id,
            publication_id=publication_id,
            sold_at=datetime.now(tz=timezone.utc),
            amount_usd=round(sale_amount, 4),
            is_mock=is_mock,
        )
        self._db.add(sale)

        # Bump product lifetime counters
        product.total_sales += 1
        product.total_revenue_usd = float(product.total_revenue_usd) + sale_amount

        # Bump per-video counters
        if publication_id:
            pl = (
                await self._db.execute(
                    select(ProductLink).where(
                        ProductLink.publication_id == publication_id,
                        ProductLink.product_id == product_id,
                    )
                )
            ).scalar_one_or_none()
            if pl:
                pl.sales += 1
                pl.revenue_usd = float(pl.revenue_usd) + sale_amount

        await self._db.flush()
        return sale

    async def record_click(
        self, *, publication_id: uuid.UUID, product_id: uuid.UUID
    ) -> ProductLink | None:
        pl = (
            await self._db.execute(
                select(ProductLink).where(
                    ProductLink.publication_id == publication_id,
                    ProductLink.product_id == product_id,
                )
            )
        ).scalar_one_or_none()
        if pl:
            pl.clicks += 1
        return pl

    # ── Mock sale generation ──────────────────────────────────────────────────

    async def generate_mock_sales(
        self,
        product_id: uuid.UUID,
        *,
        count: int = 20,
        days_back: int = 30,
    ) -> int:
        """Seed `count` mock sales spread over the past `days_back` days."""
        product = await self.get_product(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        now = datetime.now(tz=timezone.utc)
        sales: list[ProductSale] = []
        total_rev = 0.0

        for i in range(count):
            # Spread evenly with slight variance
            offset_hours = int((i / count) * days_back * 24)
            sold_at = now - timedelta(hours=offset_hours)
            # Amount varies ±10% around price
            variance = 1.0 + (_seed_float(product_id, f"amt_{i}") - 0.5) * 0.2
            amount = round(product.price_usd * variance, 4)
            total_rev += amount
            sales.append(ProductSale(
                product_id=product_id,
                publication_id=product.pub_links[0].publication_id if product.pub_links else None,
                sold_at=sold_at,
                amount_usd=amount,
                is_mock=True,
            ))

        self._db.add_all(sales)
        product.total_sales += count
        product.total_revenue_usd = float(product.total_revenue_usd) + total_rev

        await self._db.flush()
        return count

    # ── Revenue reporting ─────────────────────────────────────────────────────

    async def revenue_summary(
        self,
        channel_id: uuid.UUID,
        *,
        days: int = 30,
        include_mock: bool = True,
    ) -> list[dict[str, Any]]:
        """Per-product revenue breakdown for the given window."""
        since = datetime.now(tz=timezone.utc) - timedelta(days=days)

        products = await self.list_products(channel_id, active_only=False)
        if not products:
            return []

        product_ids = [p.id for p in products]

        # Aggregate sales per product in the window
        q = (
            select(
                ProductSale.product_id,
                func.count(ProductSale.id).label("sales"),
                func.sum(ProductSale.amount_usd).label("revenue"),
            )
            .where(
                ProductSale.product_id.in_(product_ids),
                ProductSale.sold_at >= since,
            )
        )
        if not include_mock:
            q = q.where(ProductSale.is_mock.is_(False))
        q = q.group_by(ProductSale.product_id)

        rows = (await self._db.execute(q)).all()
        period_data = {r.product_id: {"sales": r.sales, "revenue": float(r.revenue)} for r in rows}

        # Prior period for trend
        prior_since = since - timedelta(days=days)
        q_prior = (
            select(
                ProductSale.product_id,
                func.sum(ProductSale.amount_usd).label("revenue"),
            )
            .where(
                ProductSale.product_id.in_(product_ids),
                ProductSale.sold_at >= prior_since,
                ProductSale.sold_at < since,
            )
        )
        if not include_mock:
            q_prior = q_prior.where(ProductSale.is_mock.is_(False))
        q_prior = q_prior.group_by(ProductSale.product_id)
        prior_rows = (await self._db.execute(q_prior)).all()
        prior_data = {r.product_id: float(r.revenue) for r in prior_rows}

        result = []
        for product in products:
            curr = period_data.get(product.id, {"sales": 0, "revenue": 0.0})
            prior_rev = prior_data.get(product.id, 0.0)
            trend_pct = (
                round((curr["revenue"] - prior_rev) / prior_rev * 100, 1)
                if prior_rev > 0
                else None
            )
            result.append({
                "product_id": str(product.id),
                "name": product.name,
                "product_type": product.product_type.value,
                "platform": product.platform.value,
                "price_usd": product.price_usd,
                "period_sales": curr["sales"],
                "period_revenue_usd": round(curr["revenue"], 4),
                "revenue_trend_pct": trend_pct,
                "lifetime_sales": product.total_sales,
                "lifetime_revenue_usd": float(product.total_revenue_usd),
                "revenue_per_sale": product.revenue_per_sale,
                "is_active": product.is_active,
                "is_featured": product.is_featured,
            })

        result.sort(key=lambda x: x["period_revenue_usd"], reverse=True)
        return result

    async def publication_revenue(
        self, publication_id: uuid.UUID
    ) -> dict[str, Any]:
        """Per-product revenue breakdown for a single publication."""
        links = await self.list_publication_products(publication_id)
        if not links:
            return {
                "publication_id": str(publication_id),
                "total_sales": 0,
                "total_revenue_usd": 0.0,
                "products": [],
            }

        rows = []
        total_sales = 0
        total_rev = 0.0

        for link in links:
            product = await self.get_product(link.product_id)
            if not product:
                continue
            total_sales += link.sales
            total_rev += float(link.revenue_usd)
            rows.append({
                "product_id": str(link.product_id),
                "name": product.name,
                "product_type": product.product_type.value,
                "price_usd": product.price_usd,
                "clicks": link.clicks,
                "sales": link.sales,
                "revenue_usd": float(link.revenue_usd),
                "cvr_pct": round(link.cvr * 100, 2) if link.cvr else None,
                "position": link.position,
                "description_text": link.description_text,
            })

        rows.sort(key=lambda x: x["revenue_usd"], reverse=True)

        return {
            "publication_id": str(publication_id),
            "total_sales": total_sales,
            "total_revenue_usd": round(total_rev, 4),
            "products": rows,
        }

    async def channel_revenue(
        self,
        channel_id: uuid.UUID,
        *,
        days: int = 30,
    ) -> dict[str, Any]:
        """Channel-level revenue totals by product type."""
        since = datetime.now(tz=timezone.utc) - timedelta(days=days)
        products = await self.list_products(channel_id, active_only=False)
        product_ids = [p.id for p in products]

        if not product_ids:
            return {
                "channel_id": str(channel_id),
                "period_days": days,
                "total_revenue_usd": 0.0,
                "total_sales": 0,
                "by_type": [],
                "top_products": [],
            }

        q = (
            select(
                ProductSale.product_id,
                func.count(ProductSale.id).label("sales"),
                func.sum(ProductSale.amount_usd).label("revenue"),
            )
            .where(
                ProductSale.product_id.in_(product_ids),
                ProductSale.sold_at >= since,
            )
            .group_by(ProductSale.product_id)
        )
        rows = (await self._db.execute(q)).all()
        sale_map = {r.product_id: {"sales": r.sales, "revenue": float(r.revenue)} for r in rows}

        by_type: dict[str, dict] = {}
        for product in products:
            t = product.product_type.value
            d = sale_map.get(product.id, {"sales": 0, "revenue": 0.0})
            if t not in by_type:
                by_type[t] = {"sales": 0, "revenue": 0.0, "count": 0}
            by_type[t]["sales"]   += d["sales"]
            by_type[t]["revenue"] += d["revenue"]
            by_type[t]["count"]   += 1

        total_rev   = sum(v["revenue"] for v in by_type.values())
        total_sales = sum(v["sales"]   for v in by_type.values())

        by_type_list = [
            {
                "product_type": t,
                "product_count": v["count"],
                "period_sales": v["sales"],
                "period_revenue_usd": round(v["revenue"], 4),
                "share_pct": round(v["revenue"] / total_rev * 100, 1) if total_rev > 0 else 0.0,
            }
            for t, v in sorted(by_type.items(), key=lambda x: x[1]["revenue"], reverse=True)
        ]

        # Top 5 earners in period
        top_products = sorted(
            [
                {
                    "product_id": str(p.id),
                    "name": p.name,
                    "product_type": p.product_type.value,
                    "period_revenue_usd": round(sale_map.get(p.id, {}).get("revenue", 0.0), 4),
                    "period_sales": sale_map.get(p.id, {}).get("sales", 0),
                }
                for p in products
            ],
            key=lambda x: x["period_revenue_usd"],
            reverse=True,
        )[:5]

        return {
            "channel_id": str(channel_id),
            "period_days": days,
            "total_revenue_usd": round(total_rev, 4),
            "total_sales": total_sales,
            "by_type": by_type_list,
            "top_products": top_products,
        }

    async def sales_history(
        self,
        product_id: uuid.UUID,
        *,
        days: int = 30,
        include_mock: bool = True,
    ) -> list[dict[str, Any]]:
        """Daily sales buckets for chart rendering."""
        since = datetime.now(tz=timezone.utc) - timedelta(days=days)
        q = select(ProductSale).where(
            ProductSale.product_id == product_id,
            ProductSale.sold_at >= since,
        )
        if not include_mock:
            q = q.where(ProductSale.is_mock.is_(False))
        q = q.order_by(ProductSale.sold_at)
        sales = list((await self._db.execute(q)).scalars().all())

        buckets: dict[str, dict] = {}
        for sale in sales:
            day = sale.sold_at.date().isoformat()
            if day not in buckets:
                buckets[day] = {"date": day, "sales": 0, "revenue_usd": 0.0}
            buckets[day]["sales"] += 1
            buckets[day]["revenue_usd"] += float(sale.amount_usd)

        for v in buckets.values():
            v["revenue_usd"] = round(v["revenue_usd"], 4)

        return [buckets[d] for d in sorted(buckets)]
