#!/usr/bin/env python

"""Tests for `acasclient` package."""

import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from acasclient import acasclient
from acasclient.lsthing import (BlobValue, CodeValue, FileValue, LsThingValue,
                                SimpleLsThing, get_lsKind_to_lsvalue)

# SETUP
# "bob" user name registered
# "PROJ-00000001" registered

# Constants
ACAS_DDICT = 'ACAS DDICT'
PROJECT_METADATA = 'project metadata'
PROJECT = 'project'
PROJECT_NAME = 'project name'
PROJECT_ALIAS = 'project alias'
STATUS = 'status'
PROJECT_STATUS = 'project status'
PROCEDURE_DOCUMENT = 'procedure document'
IS_RESTRICTED = 'is restricted'
RESTRICTED = 'restricted'
PDF_DOCUMENT = 'pdf document'
START_DATE = 'start date'
NAME_KEY = 'name'
IS_RESTRICTED_KEY = 'is_restricted'
STATUS_KEY = 'status'
START_DATE_KEY = 'start_date'
PDF_DOCUMENT_KEY = 'pdf_document'
PROCEDURE_DOCUMENT_KEY = 'procedure_document'

class Project(SimpleLsThing):
    ls_type = PROJECT
    ls_kind = PROJECT
    preferred_label_kind = PROJECT_NAME

    def __init__(self, name=None, alias=None, start_date=None, status=None, is_restricted=True, procedure_document=None, pdf_document=None, recorded_by=None):
        names = {PROJECT_NAME: name, PROJECT_ALIAS: alias}
        metadata = {
            PROJECT_METADATA: {
                START_DATE: start_date,
                PROJECT_STATUS: CodeValue(status, PROJECT, STATUS, ACAS_DDICT),
                IS_RESTRICTED: CodeValue(str(is_restricted).lower(), PROJECT, RESTRICTED, ACAS_DDICT),
                PROCEDURE_DOCUMENT: BlobValue(file_path=procedure_document),
                PDF_DOCUMENT: FileValue(value=pdf_document)
            }
        }
        super(Project, self).__init__(ls_type=self.ls_type, ls_kind=self.ls_kind, names=names, recorded_by=recorded_by,
                                      preferred_label_kind=self.preferred_label_kind, metadata=metadata)


class TestLsThing(unittest.TestCase):
    """Tests for `acasclient lsthing` package model."""

    def setUp(self):
        """Set up test fixtures, if any."""
        creds = acasclient.get_default_credentials()
        self.client = acasclient.client(creds)
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        """Tear down test fixtures, if any."""
        dummy_file = Path('dummy.pdf')
        if dummy_file.exists():
            os.remove(dummy_file)

    # Helpers
    def _get_path(self, file_name):
        path = Path(__file__).resolve().parent\
            .joinpath('test_acasclient', file_name)
        return path

    def _get_bytes(self, file_path):
        with open(file_path, "rb") as in_file:
            file_bytes = in_file.read()
        return file_bytes

    def _check_blob_equal(self, blob_value, orig_file_name, orig_bytes):
        self.assertEqual(blob_value.comments, orig_file_name)
        data = blob_value.download_data(self.client)
        self.assertEqual(data, orig_bytes)

    def _check_file(self, file_path, orig_file_name, orig_file_path):
        # Check file names match
        self.assertEqual(Path(file_path).name, orig_file_name)
        # Check file contents match
        new_bytes = self._get_bytes(file_path)
        orig_bytes = self._get_bytes(orig_file_path)
        self.assertEqual(new_bytes, orig_bytes)

    # Tests
    def test_000_simple_ls_thing_save(self):
        """Test saving simple ls thing."""
        name = str(uuid.uuid4())
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: time.time()
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        self.assertIsNone(newProject.code_name)
        self.assertIsNone(newProject._ls_thing.id)
        newProject.save(self.client)
        self.assertIsNotNone(newProject.code_name)
        self.assertIsNotNone(newProject._ls_thing.id)

    def test_001_simple_ls_thing_save_with_blob_value(self):
        """Test saving simple ls thing with blob value."""
        name = str(uuid.uuid4())
        file_name = 'blob_test.png'
        blob_test_path = Path(__file__).resolve().parent\
            .joinpath('test_acasclient', file_name)

        # Get the file bytes for testing
        in_file = open(blob_test_path, "rb")
        file_bytes = in_file.read()
        in_file.close()

        # Save with Path path
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: time.time(),
            PROCEDURE_DOCUMENT_KEY: blob_test_path
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        newProject.save(self.client)
        self._check_blob_equal(newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT], file_name, file_bytes)

        # Save with string path
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: time.time(),
            PROCEDURE_DOCUMENT_KEY: str(blob_test_path)
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        newProject.save(self.client)
        self._check_blob_equal(newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT], file_name, file_bytes)

        # Write to a file by providing a full file path
        custom_file_name = "my.png"
        output_file = newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT].write_to_file(full_file_path=Path(self.tempdir, custom_file_name))
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.name, custom_file_name)

        # Write to a file by providing a full file path as a string
        custom_file_name = "my.png"
        output_file = newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT].write_to_file(full_file_path=str(Path(self.tempdir, custom_file_name)))
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.name, custom_file_name)

        # Write to a file by providing a folder
        output_file = newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT].write_to_file(folder_path=self.tempdir)
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.name, file_name)

        # Write to a file by providing a folder as a string
        output_file = newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT].write_to_file(folder_path=str(self.tempdir))
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.name, file_name)

        # Write to a file by providing a folder and custom file name 
        output_file = newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT].write_to_file(folder_path=self.tempdir, file_name=custom_file_name)
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.name, custom_file_name)

        # Write to a bad folder path fails gracefully
        with self.assertRaises(ValueError):
            output_file = newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT].write_to_file(folder_path="GARBAGE")
        try:
            output_file = newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT].write_to_file(folder_path="GARBAGE")
        except ValueError as err:
            self.assertIn("does not exist", err.args[0])

        # Make sure a bad path fails gracefully
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: time.time(),
            PROCEDURE_DOCUMENT_KEY: "SOMEGARBAGEPATH"
        }
        with self.assertRaises(ValueError):
            newProject = Project(recorded_by=self.client.username, **meta_dict)
        try:
            newProject = Project(recorded_by=self.client.username, **meta_dict)
        except ValueError as err:
            self.assertIn("does not exist", err.args[0])

        # Make sure passing a directory fails gracefully
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: time.time(),
            PROCEDURE_DOCUMENT_KEY: self.tempdir
        }
        with self.assertRaises(ValueError):
            newProject = Project(recorded_by=self.client.username, **meta_dict)
        try:
            newProject = Project(recorded_by=self.client.username, **meta_dict)
        except ValueError as err:
            self.assertIn("not a file", err.args[0])

    def test_002_update_blob_value(self):
        """Test saving simple ls thing with blob value, then updating the blobValue."""

        # Create a project with first blobValue
        name = str(uuid.uuid4())
        file_name = 'blob_test.png'
        file_path = self._get_path(file_name)
        file_bytes = self._get_bytes(file_path)

        # Save with Path path
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: time.time(),
            PROCEDURE_DOCUMENT_KEY: file_path
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        newProject.save(self.client)
        self._check_blob_equal(newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT], file_name, file_bytes)
        
        # Then update with a different file
        file_name = '1_1_Generic.xlsx'
        file_path = self._get_path(file_name)
        file_bytes = self._get_bytes(file_path)
        new_blob_val = BlobValue(file_path=file_path)
        newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT] = new_blob_val
        newProject.save(self.client)
        self._check_blob_equal(newProject.metadata[PROJECT_METADATA][PROCEDURE_DOCUMENT], file_name, file_bytes)

    def test_003_simple_ls_thing_save_with_file_value(self):
        """Test saving simple ls thing with file value."""
        name = str(uuid.uuid4())
        file_name = 'dummy.pdf'
        file_test_path = Path(__file__).resolve().parent\
            .joinpath('test_acasclient', file_name)

        # Save with Path value
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: time.time(),
            PDF_DOCUMENT_KEY: file_test_path
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        newProject.save(self.client)
        # Write file locally and compare
        fv = newProject.metadata[PROJECT_METADATA][PDF_DOCUMENT]
        downloaded_path = fv.download_to_disk(self.client)
        self._check_file(downloaded_path, file_name, file_test_path)

        # Save with string value
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: time.time(),
            PDF_DOCUMENT_KEY: str(file_test_path)
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        newProject.save(self.client)
        # Write file locally and compare
        fv = newProject.metadata[PROJECT_METADATA][PDF_DOCUMENT]
        downloaded_path = fv.download_to_disk(self.client)
        self._check_file(downloaded_path, file_name, file_test_path)

        # Save with Path file_path
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: time.time(),
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        newProject.metadata[PROJECT_METADATA][PDF_DOCUMENT] = FileValue(file_path=file_test_path)
        self.assertIsNotNone(newProject.metadata[PROJECT_METADATA][PDF_DOCUMENT].value)
        self.assertIsNotNone(newProject.metadata[PROJECT_METADATA][PDF_DOCUMENT].comments)
        newProject.save(self.client)
        # Write file locally and compare
        fv = newProject.metadata[PROJECT_METADATA][PDF_DOCUMENT]
        downloaded_path = fv.download_to_disk(self.client)
        self._check_file(downloaded_path, file_name, file_test_path)

        # Save with string file_path
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: time.time(),
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        newProject.metadata[PROJECT_METADATA][PDF_DOCUMENT] = FileValue(file_path=str(file_test_path))
        self.assertIsNotNone(newProject.metadata[PROJECT_METADATA][PDF_DOCUMENT].value)
        self.assertIsNotNone(newProject.metadata[PROJECT_METADATA][PDF_DOCUMENT].comments)
        newProject.save(self.client)
        # Write file locally and compare
        fv = newProject.metadata[PROJECT_METADATA][PDF_DOCUMENT]
        downloaded_path = fv.download_to_disk(self.client)
        self._check_file(downloaded_path, file_name, file_test_path)

        # Write to a bad folder path fails gracefully
        with self.assertRaises(ValueError):
            output_file = fv.download_to_disk(self.client, folder_path="GARBAGE")
        try:
            output_file = fv.download_to_disk(self.client, folder_path="GARBAGE")
        except ValueError as err:
            self.assertIn("does not exist", err.args[0])

    def test_004_get_lskind_to_ls_values(self):
        """
        Verify `get_lskind_to_lsvalue` adds the `unit_kind` if present to the
        `lskind` value.
        """

        # No unit_kind in LsThingValue
        lsthing_value = LsThingValue(
            ls_type='foo',
            ls_kind='bar',
            numeric_value=4.5,
        )
        lskind_to_lsvalue = get_lsKind_to_lsvalue([lsthing_value])
        assert len(lskind_to_lsvalue) == 1
        assert 'bar' in lskind_to_lsvalue

        # No unit_kind in LsThingValue
        lsthing_value = LsThingValue(
            ls_type='foo',
            ls_kind='bar',
            numeric_value=4.5,
            unit_kind='baz')
        lskind_to_lsvalue = get_lsKind_to_lsvalue([lsthing_value])
        assert len(lskind_to_lsvalue) == 1
        assert 'bar (baz)' in lskind_to_lsvalue


class TestBlobValue(unittest.TestCase):

    def setUp(self) -> None:
        creds = acasclient.get_default_credentials()
        self.client = acasclient.client(creds)

    def test_as_dict(self):
        """
        Verify `as_dict` returns the instance attributes mapped to their value.
        """

        value, comments, id = [65, 67], "blob test", None
        blob_value = BlobValue(value=value, comments=comments, id=id)
        blob_value_dict = blob_value.as_dict()

        assert len(blob_value_dict) == len(BlobValue._fields)
        assert blob_value_dict['value'] == value
        assert blob_value_dict['comments'] == comments
        assert blob_value_dict['id'] == id
