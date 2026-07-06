"""Client + normalization for the ClinicalTrials.gov API v2 (/studies endpoint).

Field paths were verified against the live API. Each study is normalized to a flat
`TrialRecord` so downstream aggregation never has to know the nested JSON shape.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog
from pydantic import BaseModel

from ..config import settings
from ..errors import UpstreamError
from ..schemas.query import QuerySpec

log = structlog.get_logger(__name__)

# Transient HTTP statuses worth retrying (mirrors the retryable set in app/agent/llm.py).
_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})

# Normalize the API's phase tokens to friendly labels.
PHASE_LABELS = {
    "EARLY_PHASE1": "Early Phase 1",
    "PHASE1": "Phase 1",
    "PHASE2": "Phase 2",
    "PHASE3": "Phase 3",
    "PHASE4": "Phase 4",
    "NA": "Not Applicable",
}
# Reverse map (friendly label -> API token), used to build phase filters.
PHASE_TOKENS = {label: token for token, label in PHASE_LABELS.items()}

# Valid ClinicalTrials.gov InterventionType enum tokens. `intervention_type` is free text that
# gets interpolated into the Essie `filter.advanced` string, so we allowlist it: only a known
# token is ever emitted, which both validates the input and blocks Essie-syntax injection.
INTERVENTION_TYPES = frozenset(
    {
        "DRUG",
        "BIOLOGICAL",
        "DEVICE",
        "PROCEDURE",
        "BEHAVIORAL",
        "DIETARY_SUPPLEMENT",
        "GENETIC",
        "RADIATION",
        "COMBINATION_PRODUCT",
        "DIAGNOSTIC_TEST",
        "OTHER",
    }
)


# The exact set of study fields `normalize_study` reads. Passing this as the API's `fields`
# projection means the upstream returns only these leaves instead of the full study payload —
# smaller responses, less parsing. Keep in sync with `normalize_study`.
STUDY_FIELDS = (
    "protocolSection.identificationModule.nctId",
    "protocolSection.identificationModule.briefTitle",
    "protocolSection.statusModule.overallStatus",
    "protocolSection.statusModule.startDateStruct",
    "protocolSection.statusModule.completionDateStruct",
    "protocolSection.statusModule.primaryCompletionDateStruct",
    "protocolSection.designModule.studyType",
    "protocolSection.designModule.phases",
    "protocolSection.designModule.enrollmentInfo",
    "protocolSection.conditionsModule.conditions",
    # Only the leaves we read — skips each location's facility/geo/contact bloat and the
    # interventions' descriptions/arm labels.
    "protocolSection.armsInterventionsModule.interventions.type",
    "protocolSection.armsInterventionsModule.interventions.name",
    "protocolSection.sponsorCollaboratorsModule.leadSponsor.name",
    "protocolSection.contactsLocationsModule.locations.country",
)


def intervention_type_token(value: str) -> str | None:
    """Normalize free-text intervention type to a valid enum token, or None if unrecognized."""
    token = "_".join(value.strip().upper().split())
    return token if token in INTERVENTION_TYPES else None


class TrialRecord(BaseModel):
    nct_id: str
    title: str
    overall_status: str | None = None
    study_type: str | None = None
    phases: list[str] = []
    start_date: str | None = None
    start_year: int | None = None
    conditions: list[str] = []
    interventions: list[dict[str, str]] = []  # {"type": ..., "name": ...}
    lead_sponsor: str | None = None
    countries: list[str] = []
    enrollment: int | None = None
    completion_date: str | None = None
    duration_months: int | None = None


def _dig(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def _parse_year(date_str: str | None) -> int | None:
    if not date_str:
        return None
    # Dates come as "2019-04" or "2019-04-01" or "2019".
    head = date_str.strip()[:4]
    return int(head) if head.isdigit() else None


def _parse_ym(date_str: str | None) -> tuple[int, int] | None:
    """(year, month) from a 'YYYY', 'YYYY-MM', or 'YYYY-MM-DD' date string."""
    if not date_str:
        return None
    parts = date_str.strip().split("-")
    if not parts[0].isdigit():
        return None
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    return year, month


def _duration_months(start: str | None, end: str | None) -> int | None:
    """Whole months between two trial dates (None if unknown or non-positive)."""
    a, b = _parse_ym(start), _parse_ym(end)
    if a is None or b is None:
        return None
    months = (b[0] - a[0]) * 12 + (b[1] - a[1])
    return months if months > 0 else None


def normalize_study(study: dict[str, Any]) -> TrialRecord | None:
    """Flatten one API study object into a TrialRecord (None if no NCT id)."""
    ps = study.get("protocolSection", {})
    nct_id = _dig(ps, "identificationModule", "nctId")
    if not nct_id:
        return None

    phases_raw = _dig(ps, "designModule", "phases", default=[]) or []
    phases = [PHASE_LABELS.get(p, p.title()) for p in phases_raw]

    interventions = []
    for itv in _dig(ps, "armsInterventionsModule", "interventions", default=[]) or []:
        name = itv.get("name")
        if name:
            interventions.append({"type": itv.get("type", "") or "", "name": name})

    countries: list[str] = []
    for loc in _dig(ps, "contactsLocationsModule", "locations", default=[]) or []:
        country = loc.get("country")
        if country and country not in countries:
            countries.append(country)

    start_date = _dig(ps, "statusModule", "startDateStruct", "date")
    completion_date = _dig(ps, "statusModule", "completionDateStruct", "date") or _dig(
        ps, "statusModule", "primaryCompletionDateStruct", "date"
    )
    enrollment = _dig(ps, "designModule", "enrollmentInfo", "count")
    enrollment = int(enrollment) if isinstance(enrollment, (int, float)) else None

    return TrialRecord(
        nct_id=nct_id,
        title=_dig(ps, "identificationModule", "briefTitle", default="") or "",
        overall_status=_dig(ps, "statusModule", "overallStatus"),
        study_type=_dig(ps, "designModule", "studyType"),
        phases=phases,
        start_date=start_date,
        start_year=_parse_year(start_date),
        conditions=_dig(ps, "conditionsModule", "conditions", default=[]) or [],
        interventions=interventions,
        lead_sponsor=_dig(ps, "sponsorCollaboratorsModule", "leadSponsor", "name"),
        countries=countries,
        enrollment=enrollment,
        completion_date=completion_date,
        duration_months=_duration_months(start_date, completion_date),
    )


def build_params(
    spec: QuerySpec,
    page_size: int,
    page_token: str | None = None,
    *,
    project: bool = True,
) -> dict[str, Any]:
    """Translate a QuerySpec into ClinicalTrials.gov v2 query/filter parameters.

    `project=True` restricts the response to `STUDY_FIELDS` (the leaves we normalize). A count
    query passes `project=False` since it reads only `totalCount` and pulls no records.
    """
    params: dict[str, Any] = {
        "format": "json",
        "pageSize": page_size,
        "countTotal": "true",
    }
    if project:
        params["fields"] = ",".join(STUDY_FIELDS)
    if spec.condition:
        params["query.cond"] = spec.condition
    if spec.intervention:
        params["query.intr"] = spec.intervention
    if spec.sponsor:
        params["query.spons"] = spec.sponsor
    if spec.country:
        params["query.locn"] = spec.country
    if spec.status:
        params["filter.overallStatus"] = ",".join(s.upper() for s in spec.status)

    advanced: list[str] = []
    if spec.study_type:
        advanced.append(f"AREA[StudyType]{spec.study_type.value.upper()}")
    if spec.intervention_type and (it := intervention_type_token(spec.intervention_type)):
        advanced.append(f"AREA[InterventionType]{it}")
    if spec.phase and (token := PHASE_TOKENS.get(spec.phase.strip().title())):
        advanced.append(f"AREA[Phase]{token}")
    if spec.start_year or spec.end_year:
        lo = f"{spec.start_year}-01-01" if spec.start_year else "MIN"
        hi = f"{spec.end_year}-12-31" if spec.end_year else "MAX"
        advanced.append(f"AREA[StartDate]RANGE[{lo},{hi}]")
    if advanced:
        params["filter.advanced"] = " AND ".join(advanced)

    if page_token:
        params["pageToken"] = page_token
    return params


def filters_summary(spec: QuerySpec) -> str:
    """Human-readable description of the filters applied (for chart metadata)."""
    parts: list[str] = []
    if spec.condition:
        parts.append(f"condition={spec.condition}")
    if spec.intervention:
        parts.append(f"intervention={spec.intervention}")
    if spec.intervention_type:
        parts.append(f"intervention_type={spec.intervention_type}")
    if spec.study_type:
        parts.append(f"study_type={spec.study_type.value}")
    if spec.sponsor:
        parts.append(f"sponsor={spec.sponsor}")
    if spec.country:
        parts.append(f"country={spec.country}")
    if spec.phase:
        parts.append(f"phase={spec.phase}")
    if spec.status:
        parts.append(f"status={'/'.join(spec.status)}")
    if spec.start_year or spec.end_year:
        parts.append(f"years={spec.start_year or 'MIN'}-{spec.end_year or 'MAX'}")
    return ", ".join(parts) if parts else "none"


class ClinicalTrialsClient:
    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        page_size: int | None = None,
        max_records: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = base_url or settings.clinicaltrials_base_url
        self.page_size = page_size or settings.page_size
        self.max_records = max_records or settings.max_records
        self._timeout = timeout or settings.http_timeout
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> ClinicalTrialsClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _retry_delay(self, attempt: int, response: httpx.Response | None) -> float:
        """Backoff seconds for `attempt`; honors a numeric Retry-After header when present."""
        if response is not None:
            retry_after = response.headers.get("retry-after", "")
            if retry_after.isdigit():
                return min(float(retry_after), settings.upstream_backoff_cap)
        return min(settings.upstream_backoff_base * (2**attempt), settings.upstream_backoff_cap)

    async def _request_json(
        self, client: httpx.AsyncClient, params: dict[str, Any]
    ) -> dict[str, Any]:
        """GET + parse JSON with bounded retry/backoff on transient failures.

        Retries 429/5xx and timeout/transport errors (up to `upstream_max_retries`); fails fast on
        4xx (auth/bad-request). A non-JSON body raises UpstreamError rather than a raw exception.
        """
        last: Exception | None = None
        for attempt in range(settings.upstream_max_retries + 1):
            try:
                resp = await client.get(self.base_url, params=params)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                last, status = exc, exc.response.status_code
                if status in _RETRYABLE_STATUS and attempt < settings.upstream_max_retries:
                    log.warning("upstream.retry", status=status, attempt=attempt)
                    await asyncio.sleep(self._retry_delay(attempt, exc.response))
                    continue
                raise UpstreamError(
                    f"ClinicalTrials.gov returned {status}", status_code=status
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = exc
                if attempt < settings.upstream_max_retries:
                    log.warning("upstream.retry", error=str(exc), attempt=attempt)
                    await asyncio.sleep(self._retry_delay(attempt, None))
                    continue
                raise UpstreamError(f"ClinicalTrials.gov request failed: {exc}") from exc
            except httpx.HTTPError as exc:  # other, non-retryable transport errors
                raise UpstreamError(f"ClinicalTrials.gov request failed: {exc}") from exc
            try:
                return resp.json()
            except ValueError as exc:  # malformed / non-JSON body (JSONDecodeError ⊂ ValueError)
                raise UpstreamError(
                    "ClinicalTrials.gov returned a malformed (non-JSON) response"
                ) from exc
        raise UpstreamError(f"ClinicalTrials.gov request failed after retries: {last}")

    async def count(self, spec: QuerySpec, *, extra_advanced: str | None = None) -> int:
        """Exact number of trials matching a spec (+ optional extra Essie clause).

        Uses countTotal with pageSize=1, so it returns the true total without pulling records.
        """
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            params = build_params(spec, page_size=1, project=False)
            if extra_advanced:
                existing = params.get("filter.advanced")
                params["filter.advanced"] = (
                    f"{existing} AND {extra_advanced}" if existing else extra_advanced
                )
            payload = await self._request_json(client, params)
            return int(payload.get("totalCount", 0) or 0)
        finally:
            if owns:
                await client.aclose()

    async def search(self, spec: QuerySpec) -> tuple[list[TrialRecord], int]:
        """Fetch and normalize studies for a spec, paginating up to max_records."""
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        records: list[TrialRecord] = []
        total = 0
        page_token: str | None = None
        try:
            while len(records) < self.max_records:
                params = build_params(spec, self.page_size, page_token)
                payload = await self._request_json(client, params)
                total = payload.get("totalCount", total) or total
                for study in payload.get("studies", []):
                    if len(records) >= self.max_records:
                        break  # never overshoot the cap mid-page
                    rec = normalize_study(study)
                    if rec is not None:
                        records.append(rec)
                page_token = payload.get("nextPageToken")
                if not page_token or not payload.get("studies"):
                    break
        finally:
            if owns:
                await client.aclose()
        return records, total or len(records)

    async def fetch_sample(self, spec: QuerySpec, limit: int) -> list[TrialRecord]:
        """One page of up to `limit` normalized records — used to backfill citations for a bucket
        whose count is non-zero but that didn't surface in the main sample."""
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            payload = await self._request_json(client, build_params(spec, page_size=limit))
            out = [normalize_study(s) for s in payload.get("studies", [])]
            return [r for r in out if r is not None]
        finally:
            if owns:
                await client.aclose()
