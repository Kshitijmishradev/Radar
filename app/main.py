"""HTTP interface for the deterministic remediation workflow."""

from __future__ import annotations

import os
import asyncio
import json
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.ai_costs import AICostService, AIUsageInput
from app.domain import AnomalyInput, RemediationService, Repository, WorkflowError
from app.events import EventBroker
from app.jobs import DurableJobQueue, RemediationWorker
from app.ollama_adapter import OllamaAdapter, OllamaRuntimeConfig, OllamaUnavailable
from app.security import Principal, Role, SESSION_COOKIE, current_principal, require_role, signer


class AnomalyRequest(BaseModel):
    tenant_id: str = Field(min_length=1, examples=["acme-health"])
    resource_id: str = Field(min_length=1, examples=["i-demo-001"])
    resource_type: str = Field(min_length=1, examples=["ec2"])
    environment: str = Field(min_length=1, examples=["nonprod"])
    owner: str | None = Field(default=None, examples=["data-platform"])
    auto_stop: bool
    idle_hours: float = Field(ge=0)
    current_daily_cost: float = Field(ge=0)
    expected_daily_cost: float = Field(ge=0)


class DemoLoginRequest(BaseModel):
    tenant_id: str = Field(min_length=1, examples=["acme-health"])
    user_id: str = Field(default="demo-user", min_length=1)
    role: Role = Role.ADMIN


class AIUsageRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    app: str = Field(min_length=1, examples=["support-assistant"])
    customer: str = Field(min_length=1, examples=["acme-corp"])
    end_user: str = Field(min_length=1, examples=["jane@acme.com"])
    provider: str = Field(min_length=1, examples=["openai"])
    model: str = Field(min_length=1, examples=["gpt-4o-mini"])
    input_tokens: int = Field(ge=0, examples=[1200])
    output_tokens: int = Field(ge=0, examples=[450])
    cached_input_tokens: int = Field(default=0, ge=0)
    compute_cost: float = Field(default=0, ge=0)
    data_cost: float = Field(default=0, ge=0)
    request_id: str | None = None
    allow_fallback: bool = False

    def usage_input(self) -> AIUsageInput:
        return AIUsageInput(**self.model_dump(exclude={"allow_fallback"}))


class AIBudgetRequest(BaseModel):
    app: str = Field(min_length=1)
    monthly_limit: float = Field(gt=0)
    warning_percent: int = Field(default=80, ge=1, le=100)


class OllamaGenerateRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    app: str = Field(min_length=1, examples=["support-assistant"])
    customer: str = Field(min_length=1, examples=["acme-corp"])
    end_user: str = Field(min_length=1, examples=["jane@acme.com"])
    model: str = Field(default="llama3.2:3b", min_length=1)
    prompt: str = Field(min_length=1, max_length=8_000)
    max_tokens: int = Field(default=120, ge=1, le=1_000)


database_path = os.getenv("DATABASE_PATH", str(Path("data") / "radar.db"))
inline_worker_enabled = os.getenv("RUN_LOCAL_WORKER", "true").lower() in {"1", "true", "yes"}
service = RemediationService(Repository(database_path))
ai_cost_service = AICostService(service.repository)
ollama_adapter = OllamaAdapter(OllamaRuntimeConfig(
    base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    hourly_capacity_cost=float(os.getenv("OLLAMA_HOURLY_CAPACITY_COST", "1.20")),
    effective_concurrency=int(os.getenv("OLLAMA_EFFECTIVE_CONCURRENCY", "1")),
))
event_broker = EventBroker()
job_queue = DurableJobQueue(service.repository)
worker = RemediationWorker(service.repository, service)


async def run_local_worker_loop() -> None:
    """Development worker. Deployments run this role in a separate process/service."""
    while True:
        outcome = worker.process_next()
        if outcome and outcome.action:
            await publish_action_event("action.succeeded", outcome.action)
        elif outcome and outcome.error:
            await event_broker.publish("job.failed", str(outcome.job["tenant_id"]), {
                "job": outcome.job, "error": outcome.error,
            })
        await asyncio.sleep(0.25)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(run_local_worker_loop()) if inline_worker_enabled else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="Radar Remediation Engine", version="0.2.0", lifespan=lifespan)
dashboard_dir = Path(__file__).parent / "dashboard"
app.mount("/assets", StaticFiles(directory=dashboard_dir), name="assets")


def actor_from_header(x_actor: str | None) -> str:
    return x_actor or "demo-user"


def scoped_action(action_id: str, principal: Principal) -> dict[str, object]:
    action = service.repository.get_action(action_id, principal.tenant_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found.")
    return action


def workflow_error(error: WorkflowError) -> HTTPException:
    message = str(error)
    code = status.HTTP_404_NOT_FOUND if message == "Action not found." else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=message)


async def publish_action_event(event_type: str, action: dict[str, object]) -> None:
    await event_broker.publish(event_type, str(action["tenant_id"]), {"action": action})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "adapter": "simulated"}


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(dashboard_dir / "index.html")


@app.get("/ai", include_in_schema=False)
def ai_dashboard() -> FileResponse:
    return FileResponse(dashboard_dir / "ai.html")


@app.post("/v1/auth/demo-login")
def demo_login(request: DemoLoginRequest, response: Response) -> dict[str, object]:
    if os.getenv("ALLOW_DEMO_AUTH", "true").lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=404, detail="Demo login is disabled.")
    principal = Principal(request.user_id, request.tenant_id, request.role)
    response.set_cookie(
        SESSION_COOKIE, signer.issue(principal), httponly=True, samesite="lax", secure=False, max_age=28_800,
    )
    return {"user_id": principal.user_id, "tenant_id": principal.tenant_id, "role": principal.role.value}


@app.post("/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/v1/session")
def session(principal: Principal = Depends(current_principal)) -> dict[str, str]:
    return {"user_id": principal.user_id, "tenant_id": principal.tenant_id, "role": principal.role.value}


@app.post("/v1/anomalies", status_code=status.HTTP_201_CREATED)
async def ingest_anomaly(request: AnomalyRequest, principal: Principal = Depends(current_principal)) -> dict[str, object]:
    require_role(principal, Role.OPERATOR)
    if principal.tenant_id != request.tenant_id:
        raise HTTPException(status_code=403, detail="You cannot submit anomalies for another tenant.")
    result = service.ingest_anomaly(AnomalyInput(**request.model_dump()))
    event_type = "action.approval_required" if result.get("action_id") else "anomaly.ineligible"
    await event_broker.publish(event_type, request.tenant_id, result)
    return result


@app.get("/v1/actions")
def list_actions(principal: Principal = Depends(current_principal)) -> list[dict[str, object]]:
    return service.repository.list_actions(principal.tenant_id)


@app.get("/v1/anomalies")
def list_anomalies(principal: Principal = Depends(current_principal)) -> list[dict[str, object]]:
    return service.repository.list_anomalies(principal.tenant_id)


@app.get("/v1/ai/overview")
def ai_overview(principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return ai_cost_service.overview(principal.tenant_id)


@app.get("/v1/ai/usage")
def list_ai_usage(principal: Principal = Depends(current_principal)) -> list[dict[str, object]]:
    return ai_cost_service.list_usage(principal.tenant_id)


@app.post("/v1/ai/preflight")
async def ai_preflight(request: AIUsageRequest, principal: Principal = Depends(current_principal)) -> dict[str, object]:
    require_role(principal, Role.OPERATOR)
    if principal.tenant_id != request.tenant_id:
        raise HTTPException(status_code=403, detail="You cannot estimate usage for another tenant.")
    try:
        result = ai_cost_service.preflight(request.usage_input(), allow_fallback=request.allow_fallback)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result["decision"] != "ALLOW":
        await event_broker.publish(f"ai.preflight_{str(result['decision']).lower()}", request.tenant_id, result)
    return result


@app.post("/v1/ai/usage", status_code=status.HTTP_201_CREATED)
async def record_ai_usage(request: AIUsageRequest, principal: Principal = Depends(current_principal)) -> dict[str, object]:
    require_role(principal, Role.OPERATOR)
    if principal.tenant_id != request.tenant_id:
        raise HTTPException(status_code=403, detail="You cannot record usage for another tenant.")
    try:
        event = ai_cost_service.record_usage(request.usage_input())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    await event_broker.publish("ai.usage_recorded", request.tenant_id, {"usage": event})
    return event


@app.post("/v1/ai/budgets")
async def set_ai_budget(request: AIBudgetRequest, principal: Principal = Depends(current_principal)) -> dict[str, object]:
    require_role(principal, Role.ADMIN)
    budget = ai_cost_service.set_budget(principal.tenant_id, request.app, request.monthly_limit, request.warning_percent)
    await event_broker.publish("ai.budget_updated", principal.tenant_id, {"budget": budget})
    return budget


@app.get("/v1/ai/ollama/health")
def ollama_health(principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return {"available": ollama_adapter.health(), "base_url": ollama_adapter.config.base_url}


@app.post("/v1/ai/ollama/generate")
async def ollama_generate(request: OllamaGenerateRequest, principal: Principal = Depends(current_principal)) -> dict[str, object]:
    require_role(principal, Role.OPERATOR)
    if principal.tenant_id != request.tenant_id:
        raise HTTPException(status_code=403, detail="You cannot submit Ollama usage for another tenant.")
    try:
        text, usage, telemetry = ollama_adapter.generate_usage(
            request.tenant_id, request.app, request.customer, request.end_user,
            request.model, request.prompt, request.max_tokens,
        )
        event = ai_cost_service.record_usage(usage)
    except OllamaUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    await event_broker.publish("ai.ollama_usage_recorded", request.tenant_id, {"usage": event, "telemetry": telemetry})
    return {"response": text, "usage": event, "telemetry": telemetry}


@app.get("/v1/actions/{action_id}")
def get_action(action_id: str, principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return scoped_action(action_id, principal)


@app.post("/v1/actions/{action_id}/approve")
async def approve(action_id: str, x_actor: str | None = Header(default=None), principal: Principal = Depends(current_principal)) -> dict[str, object]:
    try:
        require_role(principal, Role.APPROVER)
        scoped_action(action_id, principal)
        action = service.approve(action_id, x_actor or principal.user_id)
        job = job_queue.enqueue_execution(action)
        await publish_action_event("action.approved", action)
        await event_broker.publish("job.queued", str(action["tenant_id"]), {"job": job})
        return {"action": action, "job": job}
    except WorkflowError as error:
        raise workflow_error(error) from error


@app.post("/v1/actions/{action_id}/reject")
async def reject(action_id: str, x_actor: str | None = Header(default=None), principal: Principal = Depends(current_principal)) -> dict[str, object]:
    try:
        require_role(principal, Role.APPROVER)
        scoped_action(action_id, principal)
        action = service.reject(action_id, x_actor or principal.user_id)
        await publish_action_event("action.rejected", action)
        return action
    except WorkflowError as error:
        raise workflow_error(error) from error


@app.post("/v1/actions/{action_id}/execute")
async def execute(action_id: str, x_actor: str | None = Header(default=None), principal: Principal = Depends(current_principal)) -> dict[str, object]:
    try:
        require_role(principal, Role.OPERATOR)
        action = scoped_action(action_id, principal)
        if action["status"] != "APPROVED":
            raise WorkflowError("Only approved actions can be queued for execution.")
        job = job_queue.enqueue_execution(action)
        await event_broker.publish("job.queued", str(action["tenant_id"]), {"job": job})
        return {"action": action, "job": job}
    except WorkflowError as error:
        raise workflow_error(error) from error


@app.post("/v1/actions/{action_id}/rollback")
async def rollback(action_id: str, x_actor: str | None = Header(default=None), principal: Principal = Depends(current_principal)) -> dict[str, object]:
    try:
        require_role(principal, Role.OPERATOR)
        scoped_action(action_id, principal)
        action = service.rollback(action_id, x_actor or principal.user_id)
        await publish_action_event("action.rolled_back", action)
        return action
    except WorkflowError as error:
        raise workflow_error(error) from error


@app.get("/v1/actions/{action_id}/audit")
def audit(action_id: str, principal: Principal = Depends(current_principal)) -> list[dict[str, object]]:
    scoped_action(action_id, principal)
    return service.repository.get_audit_events(action_id)


@app.get("/v1/jobs")
def list_jobs(principal: Principal = Depends(current_principal)) -> list[dict[str, object]]:
    return service.repository.list_jobs(principal.tenant_id)


async def sse_stream(request: Request, tenant_id: str | None) -> AsyncIterator[str]:
    subscription_id, queue = await event_broker.subscribe(tenant_id)
    try:
        connected = {"subscription_id": subscription_id, "tenant_id": tenant_id}
        yield f"event: connected\ndata: {json.dumps(connected)}\n\n"
        while not await request.is_disconnected():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(event.as_dict())}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"
    finally:
        await event_broker.unsubscribe(subscription_id)


@app.get("/v1/events")
async def events(request: Request, principal: Principal = Depends(current_principal)) -> StreamingResponse:
    """Stream dashboard updates for the authenticated tenant only."""
    return StreamingResponse(
        sse_stream(request, principal.tenant_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
