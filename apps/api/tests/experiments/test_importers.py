"""Controlled CSV/XLSX experiment import contracts."""

import importlib.util

import pytest

from app.experiments.importers import ExperimentImporter
from app.experiments.repository import ExperimentDatasetRepository
from app.experiments.schemas import DatasetImportMetadata
from app.storage.sqlite_store import SQLiteStore


def test_experiment_importer_module_exposes_the_p3_boundary():
    try:
        module = importlib.util.find_spec("app.experiments.importers")
    except ModuleNotFoundError:
        module = None

    assert module is not None


def _metadata(dataset_id: str = "dataset-1") -> DatasetImportMetadata:
    return DatasetImportMetadata(
        dataset_id=dataset_id,
        project_id="project-a",
        group_chat_id="group-a",
        source_document_id="doc-exp-1",
        data_space="desensitized_real",
        source_mode="live",
        sample_schema={"sample_id": "sample_id", "density": "number", "strength": "number"},
        units={"density": "kg/m3", "strength": "MPa"},
        conditions={"curing_days": 28, "temperature_c": 20},
    )


def test_csv_import_creates_immutable_versioned_dataset_with_source_rows(tmp_path):
    store = SQLiteStore(tmp_path / "experiments.db")
    store.initialize()
    repository = ExperimentDatasetRepository(store)
    importer = ExperimentImporter(repository, source_root=tmp_path / "sources")
    first = importer.import_bytes(
        b"sample_id,density,strength\nS-1,600,3.2\nS-2,650,3.8\n",
        filename="results.csv",
        metadata=_metadata(),
    )
    second = importer.import_bytes(
        b"sample_id,density,strength\nS-1,610,3.4\nS-2,660,4.0\n",
        filename="results-v2.csv",
        metadata=_metadata(),
    )

    assert first.version == 1
    assert second.version == 2
    assert repository.get("dataset-1", 1).rows[0].values["strength"] == 3.2
    assert second.rows[0].source_document_id == "doc-exp-1"
    assert second.rows[0].source_location == "doc-exp-1:row:2"
    assert second.rows[0].data_space == "desensitized_real"
    assert second.rows[0].verification_status == "verified"
    assert (tmp_path / "sources").joinpath("doc-exp-1").exists()
    source_files = list((tmp_path / "sources" / "doc-exp-1").iterdir())
    assert {path.name for path in source_files} == {first.source_sha256, second.source_sha256}

    appended = repository.append(first.model_copy(deep=True))

    assert appended.version == 3
    assert repository.get("dataset-1", 1).rows[0].values["strength"] == 3.2
    assert repository.get("dataset-1", 3).rows[0].values["strength"] == 3.2


def test_xlsx_import_reads_first_sheet_without_external_parser_dependency(tmp_path):
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    def cell(ref, value):
        return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'

    sheet = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>"
        f"<row r=\"1\">{cell('A1', 'sample_id')}{cell('B1', 'density')}{cell('C1', 'strength')}</row>"
        f"<row r=\"2\">{cell('A2', 'S-1')}{cell('B2', '600')}{cell('C2', '3.2')}</row>"
        "</sheetData></worksheet>"
    )
    workbook = "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheets><sheet name=\"Sheet1\" sheetId=\"1\" r:id=\"rId1\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"/></sheets></workbook>"
    rels = "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/></Relationships>"
    content_types = "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/><Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/></Types>"
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)

    store = SQLiteStore(tmp_path / "xlsx.db")
    store.initialize()
    dataset = ExperimentImporter(ExperimentDatasetRepository(store)).import_bytes(
        stream.getvalue(), filename="results.xlsx", metadata=_metadata("dataset-xlsx")
    )

    assert dataset.rows[0].values == {"sample_id": "S-1", "density": 600.0, "strength": 3.2}


def test_source_write_failure_does_not_consume_a_dataset_version(tmp_path):
    store = SQLiteStore(tmp_path / "atomic.db")
    store.initialize()
    repository = ExperimentDatasetRepository(store)
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "doc-exp-1").write_text("not a directory", encoding="utf-8")
    importer = ExperimentImporter(repository, source_root=source_root)

    with pytest.raises(OSError):
        importer.import_bytes(
            b"sample_id,density,strength\nS-1,600,3.2\n",
            filename="results.csv",
            metadata=_metadata("dataset-atomic"),
        )

    assert repository.get("dataset-atomic", 1) is None
