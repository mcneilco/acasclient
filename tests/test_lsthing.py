#!/usr/bin/env python

"""Tests for `acasclient` package."""

import unittest
from acasclient import acasclient
from acasclient.lsthing import SimpleLsThing, CodeValue, BlobValue
from pathlib import Path
import tempfile
import time
import uuid
# SETUP
# "bob" user name registered
# "PROJ-00000001" registered


class Project(SimpleLsThing):
    ls_type = 'project'
    ls_kind = 'project'
    preferred_label_kind = 'project name'

    def __init__(self, name=None, alias=None, start_date=None, status=None, is_restricted=True, procedure_document=None, recorded_by=None):
        names = {'project name': name, "project alias": alias}
        metadata = {
            'project metadata': {
                'start date': start_date,
                'project status': CodeValue(status, "project", "status", "ACAS DDICT"),
                'is restricted': CodeValue(str(is_restricted).lower(), "project", "restricted", "ACAS DDICT"),
                'procedure document': BlobValue(file_path=procedure_document)
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

    def test_000_simple_ls_thing_save(self):
        """Test saving simple ls thing."""
        name = str(uuid.uuid4())
        meta_dict = {
            "name": name,
            "is_restricted": True,
            "status": "active",
            "start_date": time.time()
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
            "name": name,
            "is_restricted": True,
            "status": "active",
            "start_date": time.time(),
            "procedure_document": blob_test_path
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        newProject.save(self.client)
        self.assertEqual(newProject.metadata['project metadata']['procedure document'].comments, file_name)
        data = newProject.metadata['project metadata']['procedure document'].download_data(self.client)
        self.assertEqual(data, file_bytes)

        # Save with string path
        meta_dict = {
            "name": name,
            "is_restricted": True,
            "status": "active",
            "start_date": time.time(),
            "procedure_document": str(blob_test_path)
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        newProject.save(self.client)
        self.assertEqual(newProject.metadata['project metadata']['procedure document'].comments, file_name)
        data = newProject.metadata['project metadata']['procedure document'].download_data(self.client)
        self.assertEqual(data, file_bytes)

        # Write to a file by providing a full file path
        custom_file_name = "my.png"
        output_file = newProject.metadata['project metadata']['procedure document'].write_to_file(full_file_path=Path(self.tempdir, custom_file_name))
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.name, custom_file_name)

        # Write to a file by providing a full file path as a string
        custom_file_name = "my.png"
        output_file = newProject.metadata['project metadata']['procedure document'].write_to_file(full_file_path=str(Path(self.tempdir, custom_file_name)))
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.name, custom_file_name)

        # Write to a file by providing a folder
        output_file = newProject.metadata['project metadata']['procedure document'].write_to_file(folder_path=self.tempdir)
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.name, file_name)

        # Write to a file by providing a folder as a string
        output_file = newProject.metadata['project metadata']['procedure document'].write_to_file(folder_path=str(self.tempdir))
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.name, file_name)
        

        # Write to a file by providing a folder and custom file name 
        output_file = newProject.metadata['project metadata']['procedure document'].write_to_file(folder_path=self.tempdir, file_name=custom_file_name)
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.name, custom_file_name)

        # Write to a bad folder path fails gracefully
        with self.assertRaises(ValueError):
            output_file = newProject.metadata['project metadata']['procedure document'].write_to_file(folder_path="GARBAGE")
        try:
            output_file = newProject.metadata['project metadata']['procedure document'].write_to_file(folder_path="GARBAGE")
        except ValueError as err:
            self.assertIn("does not exist", err.args[0])
        
        # Make sure a bad path fails gracefully
        meta_dict = {
            "name": name,
            "is_restricted": True,
            "status": "active",
            "start_date": time.time(),
            "procedure_document": "SOMEGARBAGEPATH"
        }
        with self.assertRaises(ValueError):
            newProject = Project(recorded_by=self.client.username, **meta_dict)
        try:
            newProject = Project(recorded_by=self.client.username, **meta_dict)
        except ValueError as err:
            self.assertIn("does not exist", err.args[0])

        # Make sure passing a directory fails gracefully
        meta_dict = {
            "name": name,
            "is_restricted": True,
            "status": "active",
            "start_date": time.time(),
            "procedure_document": self.tempdir
        }
        with self.assertRaises(ValueError):
            newProject = Project(recorded_by=self.client.username, **meta_dict)
        try:
            newProject = Project(recorded_by=self.client.username, **meta_dict)
        except ValueError as err:
            self.assertIn("not a file", err.args[0])


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
