"""Market data API routes."""

from __future__ import annotations

from flask import Blueprint, request

from backend.application.market_api_service import MarketApiService
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context

bp = Blueprint("api_v1_market", __name__)
service = MarketApiService()


@bp.get("/stocks")
def list_stocks():
    get_authenticated_tenant_context()
    limit = request.args.get("limit", 20, type=int)
    keyword = request.args.get("keyword")
    return success(service.list_stocks(keyword=keyword, limit=limit))


@bp.get("/stocks/<symbol>/kline")
def get_stock_kline(symbol: str):
    get_authenticated_tenant_context()
    return success(
        service.get_kline(
            symbol=symbol,
            start_date=request.args.get("start_date"),
            end_date=request.args.get("end_date"),
            adjust=request.args.get("adjust", "qfq"),
        )
    )


@bp.get("/stocks/<symbol>/context")
def get_stock_context(symbol: str):
    context = get_authenticated_tenant_context()
    return success(service.get_stock_context(context.tenant_id, symbol, limit=request.args.get("limit", 20, type=int)))
