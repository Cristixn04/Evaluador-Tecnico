import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import hash_password, verify_password
from src.db.enums import Seniority, UserRole
from src.db.models import Membership, Organization, User, Vacancy
from src.db.session import async_session_maker

DEMO_ORG_NAME = "Tech Colombia"
DEMO_USER_EMAIL = "reclutador@tech-colombia.co"
DEMO_USER_PASSWORD = "demo123456"
DEMO_VACANCY_TITLE = "Ingeniero de Software Backend (Python / Fintech)"


async def seed_demo_data(session: AsyncSession) -> dict[str, Any]:
    """Aprovisiona de forma idempotente la organización, reclutador y vacante demo.

    Retorna un diccionario de resumen sin exponer contraseñas ni secretos.
    """
    summary: dict[str, Any] = {
        "organization_id": None,
        "organization_status": "reused",
        "user_id": None,
        "user_email": DEMO_USER_EMAIL,
        "user_status": "reused",
        "membership_status": "reused",
        "vacancies_linked": [],
    }

    # 1. Organización Demo
    stmt_org = select(Organization).where(Organization.name == DEMO_ORG_NAME)
    result_org = await session.execute(stmt_org)
    org = result_org.scalar_one_or_none()

    if org is None:
        org = Organization(name=DEMO_ORG_NAME)
        session.add(org)
        await session.flush()
        summary["organization_status"] = "created"

    summary["organization_id"] = str(org.id)

    # 2. Usuario Reclutador Demo
    stmt_user = select(User).where(User.email == DEMO_USER_EMAIL.lower())
    result_user = await session.execute(stmt_user)
    user = result_user.scalar_one_or_none()

    if user is None:
        user = User(
            email=DEMO_USER_EMAIL.lower(),
            hashed_password=hash_password(DEMO_USER_PASSWORD),
            is_active=True,
        )
        session.add(user)
        await session.flush()
        summary["user_status"] = "created"
    else:
        # Asegurar que esté activo y que la contraseña demo sea válida
        if not user.is_active:
            user.is_active = True
        if not verify_password(DEMO_USER_PASSWORD, user.hashed_password):
            user.hashed_password = hash_password(DEMO_USER_PASSWORD)
            summary["user_status"] = "updated_password"

    summary["user_id"] = str(user.id)

    # 3. Membresía Reclutador en la Organización Demo
    stmt_member = select(Membership).where(
        Membership.user_id == user.id,
        Membership.organization_id == org.id,
    )
    result_member = await session.execute(stmt_member)
    membership = result_member.scalar_one_or_none()

    if membership is None:
        membership = Membership(
            user_id=user.id,
            organization_id=org.id,
            role=UserRole.RECRUITER,
        )
        session.add(membership)
        await session.flush()
        summary["membership_status"] = "created"
    elif membership.role != UserRole.RECRUITER:
        membership.role = UserRole.RECRUITER
        summary["membership_status"] = "updated_role"

    # 4. Vacantes: vincular vacante huérfana existente y asegurar la vacante demo
    # 4a. Vincular vacante previa 'WS Test' si no tiene organización asignada
    stmt_orphan = select(Vacancy).where(
        Vacancy.title == "WS Test",
        Vacancy.organization_id.is_(None),
    )
    res_orphan = await session.execute(stmt_orphan)
    orphan_vac = res_orphan.scalar_one_or_none()
    if orphan_vac is not None:
        orphan_vac.organization_id = org.id
        summary["vacancies_linked"].append(f"{orphan_vac.title} (reassigned_from_none)")

    # 4b. Asegurar vacante principal Demo
    stmt_vac = select(Vacancy).where(
        Vacancy.organization_id == org.id,
        Vacancy.title == DEMO_VACANCY_TITLE,
    )
    res_vac = await session.execute(stmt_vac)
    demo_vac = res_vac.scalar_one_or_none()

    if demo_vac is None:
        demo_vac = Vacancy(
            organization_id=org.id,
            title=DEMO_VACANCY_TITLE,
            raw_description=(
                "Diseño e implementación de microservicios transaccionales con alta concurrencia, "
                "garantía de idempotencia en webhooks bancarios (PSE/Fintech Colombia), "
                "y optimización de complejidad algorítmica."
            ),
            role_category="Backend",
            seniority=Seniority.MID,
            profile={
                "primary_language": "python",
                "required_skills": ["python", "fastapi", "sql", "redis", "asyncio"],
                "preferred_skills": ["docker", "pytest", "weasyprint"],
            },
        )
        session.add(demo_vac)
        await session.flush()
        summary["vacancies_linked"].append(f"{DEMO_VACANCY_TITLE} (created)")
    else:
        summary["vacancies_linked"].append(f"{DEMO_VACANCY_TITLE} (reused)")

    return summary


async def main() -> None:
    db_target = settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else settings.DATABASE_URL
    print(f"[Seed] Iniciando aprovisionamiento en: {db_target}")

    async with async_session_maker() as session, session.begin():
        summary = await seed_demo_data(session)

    print("[Seed] Aprovisionamiento completado con éxito:")
    print(f" - Organización: {DEMO_ORG_NAME} (Status: {summary['organization_status']}, ID: {summary['organization_id']})")
    print(f" - Usuario: {summary['user_email']} (Status: {summary['user_status']}, ID: {summary['user_id']})")
    print(f" - Membresía: rol={UserRole.RECRUITER.value} (Status: {summary['membership_status']})")
    print(f" - Vacantes vinculadas: {', '.join(summary['vacancies_linked'])}")


if __name__ == "__main__":
    asyncio.run(main())
