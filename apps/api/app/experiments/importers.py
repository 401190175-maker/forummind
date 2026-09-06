"""CSV/XLSX parsing and validated dataset import."""

from __future__ import annotations

import csv
from io import BytesIO, StringIO
import hashlib
from pathlib import Path
from collections.abc import Mapping, Sequence
from time import time
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import ZipFile

from app.experiments.repository import ExperimentDatasetRepository
from app.experiments.schemas import DatasetImportMetadata, ExperimentDataset
from app.experiments.validation import validate_rows


class ExperimentImportError(ValueError):
    """The source file cannot be interpreted as an experiment table."""


class ExperimentImporter:
    """Parse tabular bytes, validate them, persist the source and append a version."""

    def __init__(self, repository: ExperimentDatasetRepository, *, source_root: str | Path | None = None) -> None:
        self.repository = repository
        self.source_root = Path(source_root).resolve() if source_root is not None else None

    def import_dataset(self, file_id: str, metadata: DatasetImportMetadata | Mapping[str, object]) -> ExperimentDataset:
        path = Path(file_id)
        if not path.is_file():
            raise ExperimentImportError(f"source file does not exist: {file_id}")
        return self.import_bytes(path.read_bytes(), filename=path.name, metadata=metadata)

    def import_bytes(
        self,
        content: bytes,
        *,
        filename: str,
        metadata: DatasetImportMetadata | Mapping[str, object],
    ) -> ExperimentDataset:
        if not content:
            raise ExperimentImportError("source file is empty")
        resolved = metadata if isinstance(metadata, DatasetImportMetadata) else DatasetImportMetadata.model_validate(metadata)
        headers, raw_rows = parse_table(content, filename)
        rows = validate_rows(
            headers,
            raw_rows,
            resolved.sample_schema,
            resolved.units,
            source_document_id=resolved.source_document_id,
            data_space=resolved.data_space,
            source_mode=resolved.source_mode,
        )
        timestamp = time()
        dataset = ExperimentDataset(
            dataset_id=resolved.dataset_id,
            version=self.repository.next_version(resolved.dataset_id),
            project_id=resolved.project_id,
            group_chat_id=resolved.group_chat_id,
            source_document_id=resolved.source_document_id,
            filename=filename,
            source_sha256=hashlib.sha256(content).hexdigest(),
            sample_schema=dict(resolved.sample_schema),
            units=dict(resolved.units),
            conditions=dict(resolved.conditions),
            rows=rows,
            data_space=resolved.data_space,
            source_mode=resolved.source_mode,
            verification_status="fixture" if resolved.source_mode in {"fixture", "replay"} else "verified",
            created_at=timestamp,
            updated_at=timestamp,
        )
        if self.source_root is None:
            return self.repository.append(dataset)

        self._validate_source_identifier(resolved.source_document_id)
        source_directory = self.source_root / resolved.source_document_id
        source_directory.mkdir(parents=True, exist_ok=True)
        source_path = source_directory / dataset.source_sha256
        existed = source_path.exists()
        try:
            source_path.write_bytes(content)
            return self.repository.append_with_source(
                dataset,
                source_id=resolved.source_document_id,
                storage_path=str(source_path),
            )
        except Exception:
            if not existed:
                source_path.unlink(missing_ok=True)
            raise

    def _persist_source(self, source_document_id: str, dataset: ExperimentDataset, content: bytes) -> None:
        if self.source_root is None:
            return
        self._validate_source_identifier(source_document_id)
        source_directory = self.source_root / source_document_id
        source_directory.mkdir(parents=True, exist_ok=True)
        source_path = source_directory / dataset.source_sha256
        source_path.write_bytes(content)
        self.repository.save_source(
            source_id=source_document_id,
            dataset=dataset,
            storage_path=str(source_path),
        )

    @staticmethod
    def _validate_source_identifier(source_document_id: str) -> None:
        if Path(source_document_id).name != source_document_id or source_document_id in {".", ".."}:
            raise ExperimentImportError("source_document_id must be a safe identifier")

    def preview(self, content: bytes, *, filename: str):
        if not content:
            raise ExperimentImportError("source file is empty")
        headers, raw_rows = parse_table(content, filename)
        columns = [str(value).strip() for value in headers]
        findings: list[dict[str, object]] = []
        if not columns or any(not column for column in columns) or len(set(columns)) != len(columns):
            findings.append({"code": "invalid_schema", "message": "column names must be non-empty and unique"})
        for offset, row in enumerate(raw_rows, start=2):
            if len(row) != len(columns):
                findings.append({"code": "column_count", "row_number": offset,
                                 "message": "row has a different number of values than the header"})
        inferred: dict[str, str] = {}
        for index, column in enumerate(columns):
            values = [str(row[index]).strip() for row in raw_rows if index < len(row) and str(row[index]).strip()]
            if index == 0:
                inferred[column] = "sample_id"
            else:
                try:
                    for value in values:
                        float(value)
                    inferred[column] = "number" if values else "text"
                except ValueError:
                    inferred[column] = "text"
        sample_rows = [
            {columns[index]: (row[index] if index < len(row) else "") for index in range(len(columns))}
            for row in raw_rows[:5]
        ]
        from app.experiments.schemas import ExperimentPreview
        return ExperimentPreview(
            filename=filename, columns=columns, inferred_field_types=inferred,
            sample_rows=sample_rows, validation_findings=findings,
        )


def parse_table(content: bytes, filename: str) -> tuple[list[str], list[list[str]]]:
    suffix = Path(filename).suffix.casefold()
    if suffix == ".csv":
        return _parse_csv(content)
    if suffix == ".xlsx":
        return _parse_xlsx(content)
    raise ExperimentImportError("only CSV and XLSX sources are supported")


def _parse_csv(content: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ExperimentImportError("CSV must be UTF-8") from exc
    rows = list(csv.reader(StringIO(text, newline="")))
    if not rows:
        raise ExperimentImportError("CSV has no header")
    return [str(value) for value in rows[0]], [[str(value) for value in row] for row in rows[1:] if any(row)]


def _parse_xlsx(content: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        with ZipFile(BytesIO(content)) as archive:
            shared_strings = _shared_strings(archive)
            sheet_name = _first_sheet_name(archive)
            root = ElementTree.fromstring(archive.read(sheet_name))
    except Exception as exc:
        raise ExperimentImportError("XLSX could not be parsed") from exc
    table: list[list[str]] = []
    for row_element in root.iter():
        if _local_name(row_element.tag) != "row":
            continue
        cells: dict[int, str] = {}
        for cell in row_element:
            if _local_name(cell.tag) != "c":
                continue
            ref = cell.attrib.get("r", "A1")
            value = _cell_value(cell, shared_strings)
            cells[_column_index(ref)] = value
        if cells:
            width = max(cells) + 1
            table.append([cells.get(index, "") for index in range(width)])
    if not table:
        raise ExperimentImportError("XLSX has no header")
    width = len(table[0])
    return table[0], [row + [""] * (width - len(row)) for row in table[1:] if any(row)]


def _shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values = []
    for item in root.iter():
        if _local_name(item.tag) == "si":
            values.append("".join(node.text or "" for node in item.iter() if _local_name(node.tag) == "t"))
    return values


def _first_sheet_name(archive: ZipFile) -> str:
    try:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        first_sheet = next(item for item in workbook.iter() if _local_name(item.tag) == "sheet")
        relationship_id = next(value for key, value in first_sheet.attrib.items() if key.casefold().endswith("}id"))
        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship = next(
            item for item in relationships.iter()
            if item.attrib.get("Id") == relationship_id
        )
        target = relationship.attrib["Target"].lstrip("/")
        return target if target.startswith("xl/") else f"xl/{target}"
    except (KeyError, StopIteration, ValueError):
        return "xl/worksheets/sheet1.xml"


def _cell_value(cell, shared_strings: Sequence[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter() if _local_name(node.tag) == "t")
    value_element = next((node for node in cell if _local_name(node.tag) == "v"), None)
    value = "" if value_element is None else (value_element.text or "")
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (IndexError, ValueError):
            raise ExperimentImportError("XLSX shared string index is invalid")
    return value


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha()).upper()
    index = 0
    for character in letters:
        index = index * 26 + ord(character) - ord("A") + 1
    return max(index - 1, 0)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
