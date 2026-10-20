"""FastAPI application: wires settings, storage, memory, the agent graph and the routes."""

import logging
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app import RULES_VERSION
from app.agent.graph import build_graph
from app.agent.state import Deps
from app.ai.llm import build_model_chains, check_models, model_label
from app.api import admin, cron, routes, telegram, tools
from app.api.service import RateLimiter
from app.auth import bootstrap_admin
from app.config import Settings, get_settings
from app.core.aio import postgres_loop_problem
from app.db.models import User
from app.db.session import init_db, make_engine, make_sessionmaker
from app.db.stats import seed_demo_analyses
from app.intel.official import load_extra_official
from app.intel.retention import purge
from app.memory.embeddings import build_embeddings
from app.memory.store import seed_pattern_library

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hoshiyar")


async def _postgres_memory(settings: Settings, index: dict, stack: AsyncExitStack):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.store.postgres import AsyncPostgresStore
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=1,
        max_size=5,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        check=AsyncConnectionPool.check_connection,
        open=False,
    )
    await pool.open()
    stack.push_async_callback(pool.close)
    store = AsyncPostgresStore(pool, index={**index, "distance_type": "cosine"})
    await store.setup()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    return store, saver


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings)
        await init_db(engine)
        sessionmaker = make_sessionmaker(engine)
        embeddings, provider = build_embeddings(settings)
        index = {"dims": settings.embedding_dims, "embed": embeddings, "fields": ["text"]}
        http = httpx.AsyncClient(
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": "Hoshiyar/0.2 (link safety check)"},
        )
        async with AsyncExitStack() as stack:
            if settings.uses_postgres:
                problem = postgres_loop_problem()
                if problem:
                    raise RuntimeError(problem)
                store, checkpointer = await _postgres_memory(settings, index, stack)
            else:
                store, checkpointer = InMemoryStore(index=index), InMemorySaver()

            added = await seed_pattern_library(store, provider)
            if added:
                log.info("Seeded %d scam patterns into memory (%s)", added, provider)
            if settings.seed_demo_data:
                rows = await seed_demo_analyses(sessionmaker)
                if rows:
                    log.info("Inserted %d labelled sample rows for the dashboard", rows)
            if await bootstrap_admin(sessionmaker, settings):
                log.info("Created the first admin account (%s)", settings.admin_email)
            extra = await load_extra_official(sessionmaker)
            if extra:
                log.info("Loaded %d admin-added official domains", extra)

            try:
                model_changes = await check_models(settings)
            except Exception as exc:  # never block start-up on this
                log.warning("Model check skipped: %s", type(exc).__name__)
                model_changes = []
            models, agent_models = build_model_chains(settings)
            deps = Deps(
                settings=settings,
                llm=models[0] if models else None,
                fallbacks=models[1:],
                agent_order=agent_models,
                store=store,
                embed_provider=provider,
                sessionmaker=sessionmaker,
                http=http,
                checkpointer=checkpointer,
            )
            app.state.settings = settings
            app.state.deps = deps
            app.state.graph = build_graph(deps, checkpointer)
            app.state.limiter = RateLimiter(settings.rate_limit_per_minute)
            app.state.model_label = model_label(settings)
            app.state.model_changes = model_changes
            app.state.bot_username = None
            async with sessionmaker() as session:
                from sqlalchemy import func, select

                app.state.has_users = bool((await session.execute(select(func.count(User.id)))).scalar_one())
            try:
                removed = await purge(deps)
                if any(removed.values()):
                    log.info("Retention purge removed %s", removed)
            except Exception as exc:
                log.warning("Retention purge failed: %s", exc)
            log.info(
                "Hoshiyar ready: model=%s embeddings=%s storage=%s rules=%s",
                app.state.model_label, provider, "postgres" if settings.uses_postgres else "local", RULES_VERSION,
            )
            yield
        await http.aclose()
        await engine.dispose()

    app = FastAPI(title="Hoshiyar API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )
    for module in (routes, tools, admin, cron, telegram):
        app.include_router(module.router)

    @app.get("/")
    async def root() -> dict:
        return {"name": "Hoshiyar API", "docs": "/docs", "health": "/api/health"}

    return app


app = create_app()
