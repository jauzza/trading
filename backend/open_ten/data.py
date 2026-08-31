from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataRequest:
    dataset: str = "GLBX.MDP3"
    symbol: str = "NQ.v.0"
    schema: str = "ohlcv-1m"
    stype_in: str = "continuous"
    start: str = "2018-01-01"
    end: str = "2026-01-01"

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


class DataVault:
    """Guardrail: download is impossible without a matching prior estimate and approval."""
    def __init__(self, root: Path):
        self.root = root
        self.estimate_dir = root / "estimates"
        self.manifest_path = root / "manifest.json"

    def estimate(self, request: DataRequest) -> dict:
        if not os.getenv("DATABENTO_API_KEY"):
            return {"status": "unavailable", "reason": "DATABENTO_API_KEY is not configured", "fingerprint": request.fingerprint}
        try:
            import databento as db
        except ImportError:
            return {"status": "unavailable", "reason": "databento SDK is not installed", "fingerprint": request.fingerprint}
        client = db.Historical(os.environ["DATABENTO_API_KEY"])
        cost = client.metadata.get_cost(
            dataset=request.dataset,
            symbols=[request.symbol],
            schema=request.schema,
            stype_in=request.stype_in,
            start=request.start,
            end=request.end,
        )
        self.estimate_dir.mkdir(parents=True, exist_ok=True)
        record = {"fingerprint": request.fingerprint, "cost_usd": float(cost), "request": asdict(request)}
        (self.estimate_dir / f"{request.fingerprint}.json").write_text(json.dumps(record, indent=2))
        return {"status": "estimated", **record}

    def download(self, request: DataRequest, approved_fingerprint: str | None) -> dict:
        if request.fingerprint != approved_fingerprint:
            raise PermissionError("paid download requires explicit approval of the matching cost estimate")
        estimate_file = self.estimate_dir / f"{request.fingerprint}.json"
        if not estimate_file.exists():
            raise PermissionError("cost estimate must be recorded before download")
        estimate = json.loads(estimate_file.read_text())
        if estimate.get("request") != asdict(request):
            raise PermissionError("recorded estimate does not match this exact request")
        if not os.getenv("DATABENTO_API_KEY"):
            raise RuntimeError("DATABENTO_API_KEY is not configured")
        try:
            import databento as db
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError("databento and pyarrow must be installed") from exc

        target = self.root / "raw" / request.fingerprint
        target.mkdir(parents=True, exist_ok=True)
        manifest = self._read_manifest()
        dataset_entry = manifest.setdefault("datasets", {}).setdefault(request.fingerprint, {
            "request": asdict(request), "estimated_cost_usd": estimate["cost_usd"],
            "licensed_private_data": True, "partitions": [],
        })
        client = db.Historical(os.environ["DATABENTO_API_KEY"])
        start_date, end_date = date.fromisoformat(request.start[:10]), date.fromisoformat(request.end[:10])
        completed = {item["year"] for item in dataset_entry["partitions"] if item.get("status") == "complete"}
        for year in range(start_date.year, end_date.year + 1):
            part_start = max(start_date, date(year, 1, 1))
            part_end = min(end_date, date(year + 1, 1, 1))
            if part_start >= part_end or year in completed:
                continue
            parquet_path = target / f"year={year}" / "bars.parquet"
            metadata_path = target / f"year={year}" / "mapping.json"
            parquet_path.parent.mkdir(parents=True, exist_ok=True)
            if parquet_path.exists() and metadata_path.exists():
                rows = pq.ParquetFile(parquet_path).metadata.num_rows
            else:
                dbn_tmp = target / f".{request.symbol.replace('.', '_')}-{year}.dbn.zst"
                parquet_tmp = parquet_path.with_suffix(".parquet.tmp")
                if dbn_tmp.exists():
                    from databento.common.dbnstore import DBNStore
                    print(f"Resuming cached partition {request.symbol} {year}", flush=True)
                    store = DBNStore.from_file(dbn_tmp)
                else:
                    print(f"Downloading approved partition {request.symbol} {year}", flush=True)
                    store = client.timeseries.get_range(
                        dataset=request.dataset, symbols=[request.symbol], schema=request.schema,
                        stype_in=request.stype_in, stype_out="instrument_id",
                        start=part_start.isoformat(), end=part_end.isoformat(), path=dbn_tmp,
                    )
                if not parquet_tmp.exists():
                    store.to_parquet(parquet_tmp, map_symbols=False, compression="zstd")
                metadata_path.write_text(json.dumps(self._metadata_dict(store.metadata), indent=2, default=str))
                parquet_tmp.replace(parquet_path)
                rows = pq.ParquetFile(parquet_path).metadata.num_rows
                dbn_tmp.unlink(missing_ok=True)
            dataset_entry["partitions"] = [p for p in dataset_entry["partitions"] if p.get("year") != year]
            dataset_entry["partitions"].append({
                "year": year, "start": part_start.isoformat(), "end": part_end.isoformat(),
                "path": str(parquet_path), "mapping_path": str(metadata_path),
                "rows": rows, "status": "complete",
            })
            dataset_entry["partitions"].sort(key=lambda item: item["year"])
            self._write_manifest(manifest)
        return {"status": "downloaded", "fingerprint": request.fingerprint, "path": str(target), "partitions": dataset_entry["partitions"]}

    def _read_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {"version": 1, "datasets": {}}
        return json.loads(self.manifest_path.read_text())

    def _write_manifest(self, manifest: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        tmp.replace(self.manifest_path)

    @staticmethod
    def _metadata_dict(metadata) -> dict:
        result = {}
        for name in ("version", "dataset", "schema", "start", "end", "limit", "stype_in", "stype_out", "ts_out", "symbols", "partial", "not_found"):
            value = getattr(metadata, name, None)
            if value is not None:
                result[name] = value
        mappings = []
        source_mappings = getattr(metadata, "mappings", {}) or {}
        if isinstance(source_mappings, dict):
            for raw_symbol, intervals in source_mappings.items():
                mappings.append({"raw_symbol": raw_symbol, "intervals": [
                    {"start_date": item.get("start_date"), "end_date": item.get("end_date"), "symbol": item.get("symbol")}
                    if isinstance(item, dict) else
                    {"start_date": item.start_date, "end_date": item.end_date, "symbol": item.symbol}
                    for item in intervals
                ]})
        else:
            for mapping in source_mappings:
                mappings.append({
                    "raw_symbol": mapping.raw_symbol,
                    "intervals": [{"start_date": interval.start_date, "end_date": interval.end_date, "symbol": interval.symbol} for interval in mapping.intervals],
                })
        result["mappings"] = mappings
        return result
