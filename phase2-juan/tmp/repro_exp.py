import asyncio
import uuid

from benchmark.run_lab_eval import init_services, shutdown_services

from shared.models import Experiment as DBExperiment


async def main():
    svc = await init_services()
    exp_id = uuid.uuid4()
    try:
        async with svc.db.get_session() as s:
            s.add(
                DBExperiment(
                    id=exp_id, description="repro", status="created", spec={"k": 1}
                )
            )
            await s.commit()
        print("inserted", exp_id)
        # new session: read back
        async with svc.db.get_session() as s:
            from sqlalchemy import text

            n = (await s.execute(text("SELECT count(*) FROM experiments"))).scalar()
            got = (
                await s.execute(
                    text("SELECT count(*) FROM experiments WHERE id=:i"),
                    {"i": str(exp_id)},
                )
            ).scalar()
            print("total experiments:", n, "this id present:", got)
    finally:
        await shutdown_services(svc)


asyncio.run(main())
