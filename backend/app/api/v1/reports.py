from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api.deps import get_db, require_user
from app.models.user import User
from app.models.report import Report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
async def list_reports(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    result = await db.execute(
        select(Report)
        .where(Report.user_id == current_user.id)
        .order_by(Report.created_at.desc())
    )
    reports = result.scalars().all()
    return [
        {"id": r.id, "title": r.title, "type": r.type, "summary": r.summary,
         "created_at": r.created_at.isoformat()}
        for r in reports
    ]


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == current_user.id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return {
        "id": report.id, "title": report.title, "type": report.type,
        "content": report.content, "products": report.products,
        "summary": report.summary, "created_at": report.created_at.isoformat(),
    }
