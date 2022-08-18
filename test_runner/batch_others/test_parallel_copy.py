import asyncio
from io import BytesIO

from fixtures.log_helper import log
from fixtures.neon_fixtures import NeonEnv, Postgres


async def repeat_bytes(buf, repetitions: int):
    for i in range(repetitions):
        yield buf


async def copy_test_data_to_table(pg: Postgres, worker_id: int, table_name: str):
    buf = BytesIO()
    for i in range(1000):
        buf.write(
            f"{i}\tLoaded by worker {worker_id}. Long string to consume some space.\n".encode()
        )
    buf.seek(0)

    copy_input = repeat_bytes(buf.read(), 5000)

    pg_conn = await pg.connect_async()

    # PgProtocol.connect_async sets statement_timeout to 2 minutes.
    # That's not enough for this test, on a slow system in debug mode.
    await pg_conn.execute("SET statement_timeout='300s'")

    await pg_conn.copy_to_table(table_name, source=copy_input)


async def parallel_load_same_table(pg: Postgres, n_parallel: int):
    workers = []
    for worker_id in range(n_parallel):
        worker = copy_test_data_to_table(pg, worker_id, f"copytest")
        workers.append(asyncio.create_task(worker))

    # await all workers
    await asyncio.gather(*workers)


# Load data into one table with COPY TO from 5 parallel connections
def test_parallel_copy(neon_simple_env: NeonEnv, n_parallel=5):
    env = neon_simple_env
    env.neon_cli.create_branch("test_parallel_copy", "empty")
    pg = env.postgres.create_start("test_parallel_copy")
    log.info("postgres is running on 'test_parallel_copy' branch")

    # Create test table
    conn = pg.connect()
    cur = conn.cursor()
    cur.execute(f"CREATE TABLE copytest (i int, t text)")

    # Run COPY TO to load the table with parallel connections.
    asyncio.run(parallel_load_same_table(pg, n_parallel))
