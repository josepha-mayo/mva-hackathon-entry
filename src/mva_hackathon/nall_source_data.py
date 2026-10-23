"""Descriptive audit of one checksum-frozen public JCI source workbook.

Only Python's standard library is required. ROI values are not independent
biological replicates, and no inferential statistics are computed here.
"""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics
from typing import Any
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


SOURCE_SHA256 = "3bcd611735652efed3b72292ea0bbad1670741e0c30235be58f6756bbcb89001"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CELL_ADDRESS = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
EXPECTED_TARGETS = (
    ("Fig 3I", (("B", "L444P_NT", 89), ("C", "L444P_NALL", 59))),
    ("SFig7A", (("A", "R1441C_NT", 72), ("B", "R1441C_NALL", 83))),
)


class SourceDataError(ValueError):
    """A source identity, schema or observation cannot be validated."""


def describe(values: list[float]) -> dict[str, float | int]:
    """Pooled descriptive moments; SEM is arithmetic, not valid group uncertainty."""
    if len(values) < 2 or any(
        isinstance(x, bool) or not isinstance(x, (int, float))
        or not math.isfinite(x) or x <= 0 for x in values
    ):
        raise SourceDataError("At least two finite positive numeric values are required")
    sd = statistics.stdev(values)
    return {
        "n_ROIs": len(values),
        "mean_seconds": statistics.mean(values),
        "sample_SD_seconds": sd,
        "arithmetic_SEM_seconds": sd / math.sqrt(len(values)),
        "median_seconds": statistics.median(values),
        "minimum_seconds": min(values),
        "maximum_seconds": max(values),
    }


def load_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        actual = tuple(
            (t["sheet"], tuple((g["column"], g["header"], g["expected_n"]) for g in t["groups"]))
            for t in config["targets"]
        )
        schema = config["schema"]
        valid = (
            config["schema_version"] == 1
            and config["source"]["sha256"] == SOURCE_SHA256
            and actual == EXPECTED_TARGETS
            and (schema["header_row"], schema["first_value_row"], schema["last_value_row"])
            == (2, 3, 100)
        )
    except (KeyError, TypeError) as exc:
        raise SourceDataError("Incomplete source configuration") from exc
    if not valid:
        raise SourceDataError("Configuration does not match the frozen public source schema")
    return config


def _xml(archive: ZipFile, part: str) -> ET.Element:
    try:
        return ET.fromstring(archive.read(part))
    except (KeyError, ET.ParseError) as exc:
        raise SourceDataError(f"Missing or malformed XML part: {part}") from exc


def _read_sheet(archive: ZipFile, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    workbook = _xml(archive, "xl/workbook.xml")
    matches = [s for s in workbook.findall("m:sheets/m:sheet", NS) if s.get("name") == name]
    if len(matches) != 1:
        raise SourceDataError(f"Expected exactly one worksheet named {name}")
    relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
    rid = matches[0].get(f"{{{REL_NS}}}id")
    links = [r for r in relationships if r.get("Id") == rid]
    if len(links) != 1 or links[0].get("TargetMode") == "External":
        raise SourceDataError(f"Invalid worksheet relationship for {name}")
    target = links[0].get("Target", "")
    part = target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
    if ".." in PurePosixPath(part).parts:
        raise SourceDataError("Unexpected worksheet relationship path")
    root = _xml(archive, part)
    strings: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        strings = ["".join(si.itertext()) for si in _xml(archive, "xl/sharedStrings.xml")]
    cells: dict[str, Any] = {}
    formulas: list[str] = []
    for cell in root.findall(".//m:sheetData/m:row/m:c", NS):
        address = cell.get("r", "")
        if not CELL_ADDRESS.fullmatch(address) or address in cells:
            raise SourceDataError(f"Invalid or duplicate cell address: {address}")
        if cell.find("m:f", NS) is not None:
            formulas.append(address)
            cells[address] = {"formula": True}
            continue
        raw = cell.findtext("m:v", namespaces=NS)
        kind = cell.get("t", "n")
        if kind == "inlineStr":
            cells[address] = "".join(t.text or "" for t in cell.findall("m:is//m:t", NS))
        elif raw is None:
            cells[address] = None
        elif kind == "s":
            try:
                index = int(raw)
                if index < 0:
                    raise IndexError
                cells[address] = strings[index]
            except (ValueError, IndexError) as exc:
                raise SourceDataError(f"Invalid shared-string index in {address}") from exc
        elif kind == "n":
            try:
                cells[address] = float(raw)
            except ValueError as exc:
                raise SourceDataError(f"Malformed numeric value in {address}") from exc
        else:
            cells[address] = {"unsupported_type": kind, "raw": raw}
    metadata = {
        "worksheet_state": matches[0].get("state", "visible"),
        "hidden_rows": [r.get("r") for r in root.findall(".//m:row", NS) if r.get("hidden") == "1"],
        "hidden_column_ranges": [dict(c.attrib) for c in root.findall("m:cols/m:col", NS) if c.get("hidden") == "1"],
        "merged_cells": [c.get("ref") for c in root.findall("m:mergeCells/m:mergeCell", NS)],
        "formula_cells": formulas,
        "nonempty_text_cells": {k: v for k, v in cells.items() if isinstance(v, str) and v},
    }
    return cells, metadata


def _series(cells: dict[str, Any], column: str, header: str, expected_n: int) -> tuple[list[float], list[str]]:
    if cells.get(f"{column}2") != header:
        raise SourceDataError(f"Missing or unexpected header in {column}2")
    values, addresses = [], []
    for row in range(3, 101):
        address = f"{column}{row}"
        value = cells.get(address)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise SourceDataError(f"Non-positive, nonfinite, formula or nonnumeric observation in {address}")
        values.append(float(value))
        addresses.append(address)
    if len(values) != expected_n:
        raise SourceDataError(f"{header}: expected {expected_n} observations, found {len(values)}")
    return values, addresses


def audit_workbook(path: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    path = Path(path)
    data = path.read_bytes()
    checksum = sha256(data).hexdigest()
    if checksum != SOURCE_SHA256 or config["source"]["sha256"] != SOURCE_SHA256:
        raise SourceDataError(f"Source SHA-256 mismatch: expected {SOURCE_SHA256}, observed {checksum}")
    endpoints = []
    try:
        with ZipFile(BytesIO(data)) as archive:
            comments = [n for n in archive.namelist() if "comment" in n.lower()]
            names = _xml(archive, "xl/workbook.xml").find("m:definedNames", NS)
            defined_names = [] if names is None else [dict(n.attrib) for n in names]
            for target in config["targets"]:
                cells, metadata = _read_sheet(archive, target["sheet"])
                groups = []
                for group in target["groups"]:
                    values, addresses = _series(cells, group["column"], group["header"], group["expected_n"])
                    groups.append({
                        "condition": group["header"], "summary": describe(values),
                        "source_cells": addresses,
                        "observed_ROI_values_seconds": values,
                    })
                times = [cells.get(f"E{r}") for r in range(3, 101)]
                times = [x for x in times if isinstance(x, (int, float)) and math.isfinite(x)]
                endpoint = {
                    "id": target["id"], "publication_panel": target["publication_panel"],
                    "source_sheet": target["sheet"], "mapping_basis": target["mapping_basis"],
                    "groups": groups,
                    "pooled_ROI_mean_difference_NALL_minus_NT_seconds": groups[1]["summary"]["mean_seconds"] - groups[0]["summary"]["mean_seconds"],
                    "worksheet_metadata": metadata,
                    "trace_time_column": {"n": len(times), "minimum_seconds": min(times) if times else None,
                                          "maximum_seconds": max(times) if times else None,
                                          "post_stimulus_points_present": any(x >= 0 for x in times)},
                }
                if "published_summary" in target:
                    pub = target["published_summary"]
                    comparison = {}
                    for group, prefix in zip(groups, ("NT", "NALL")):
                        summary = group["summary"]
                        comparison[prefix] = {
                            "ROI_count_matches": summary["n_ROIs"] == pub[f"{prefix}_n"],
                            "rounded_mean_matches": round(summary["mean_seconds"], 1) == pub[f"{prefix}_mean"],
                            "rounded_sample_SD_matches_printed_plus_minus": round(summary["sample_SD_seconds"], 1) == pub[f"{prefix}_plus_minus"],
                            "rounded_arithmetic_SEM_matches_printed_plus_minus": round(summary["arithmetic_SEM_seconds"], 1) == pub[f"{prefix}_plus_minus"],
                        }
                    endpoint["published_caption_check"] = {"published": pub, "comparisons": comparison}
                endpoints.append(endpoint)
    except BadZipFile as exc:
        raise SourceDataError("Source is not a valid XLSX ZIP package") from exc
    return {
        "schema_version": 1,
        "status": "executed_descriptive_public_source_reanalysis",
        "source": {**config["source"], "local_workbook": str(path.resolve()), "verified_sha256": checksum},
        "endpoints": endpoints,
        "package_metadata": {"comment_parts": comments, "defined_names": defined_names},
        "limits": {
            "culture_run_donor_identifiers_available": False,
            "independent_biological_replicate_count": None,
            "row_alignment_is_pairing": False,
            "blank_cells_are_zero": False,
            "source_cells_are_biological_identifiers": False,
            "SEM_is_valid_biological_uncertainty": False,
            "cluster_aware_inference_performed": False,
            "P_values_or_confidence_intervals_computed": False,
            "decay_refitting_performed": False,
            "note": config["inference_boundary"],
        },
    }
