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

    def __init__(self, client, name=None, alias=None, start_date=None, status=None, is_restricted=True, procedure_document=None, recorded_by=None,
                    ls_thing=None):
        names = {'project name': name, "project alias": alias}
        metadata = {
            'project metadata': {
                'start date': start_date,
                'project status': CodeValue(status, "project", "status", "ACAS DDICT"),
                'is restricted': CodeValue(str(is_restricted).lower(), "project", "restricted", "ACAS DDICT"),
                'procedure document': BlobValue(file_path=procedure_document)
            }
        }
        super(Project, self).__init__(client, ls_type=self.ls_type, ls_kind=self.ls_kind, names=names, recorded_by=recorded_by,
                                      preferred_label_kind=self.preferred_label_kind, metadata=metadata, ls_thing=ls_thing)


class TestLsThing(unittest.TestCase):
    """Tests for `acasclient lsthing` package model."""

    def setUp(self):
        """Set up test fixtures, if any."""
        creds = acasclient.get_default_credentials()
        self.client = acasclient.client(creds)
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        """Tear down test fixtures, if any."""
    
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

    # Tests
    def test_000_simple_ls_thing_save(self):
        """Test saving simple ls thing."""
        name = str(uuid.uuid4())
        meta_dict = {
            "name": name,
            "is_restricted": True,
            "status": "active",
            "start_date": time.time()
        }
        newProject = Project(self.client, **meta_dict)
        self.assertIsNone(newProject.code_name)
        self.assertIsNone(newProject._ls_thing.id)
        newProject.save()
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
        newProject = Project(self.client, recorded_by=self.client.username, **meta_dict)
        newProject.save()
        self._check_blob_equal(newProject.metadata['project metadata']['procedure document'], file_name, file_bytes)

        # Save with string path
        meta_dict = {
            "name": name,
            "is_restricted": True,
            "status": "active",
            "start_date": time.time(),
            "procedure_document": str(blob_test_path)
        }
        newProject = Project(self.client, **meta_dict)
        newProject.save()
        self._check_blob_equal(newProject.metadata['project metadata']['procedure document'], file_name, file_bytes)

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
            newProject = Project(self.client, **meta_dict)
        try:
            newProject = Project(self.client, **meta_dict)
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
            newProject = Project(self.client, **meta_dict)
        try:
            newProject = Project(self.client, **meta_dict)
        except ValueError as err:
            self.assertIn("not a file", err.args[0])
    
    def test_001_simple_ls_thing_save_list(self):
        """Test saving simple ls thing as list."""
        name = str(uuid.uuid4())
        meta_dict = {
            "name": name,
            "is_restricted": True,
            "status": "active",
            "start_date": time.time()
        }
        proj = Project(self.client, **meta_dict)
        self.assertIsNone(proj.code_name)
        self.assertIsNone(proj._ls_thing.id)
        new_projects = Project.save_list(self.client, [proj])
        new_project = new_projects[0]
        self.assertIsNotNone(new_project.code_name)
        self.assertIsNotNone(new_project._ls_thing.id)
        self.assertIsNotNone(new_project._client)
    
    def test_002_get_by_code(self):
        """Test saving simple ls thing and fetching it by code_name."""
        name = str(uuid.uuid4())
        meta_dict = {
            "name": name,
            "is_restricted": True,
            "status": "active",
            "start_date": time.time()
        }
        proj = Project(self.client, **meta_dict)
        proj.save()
        self.assertIsNotNone(proj.code_name)
        self.assertIsNotNone(proj._ls_thing.id)
        # Fetch by codename
        new_proj = Project.get_by_code(proj.code_name, client=self.client)
        self.assertIsNotNone(new_proj._ls_thing.id)
        self.assertEqual(proj.code_name, new_proj.code_name)
        self.assertIsNotNone(new_proj._client)
    
    def test_003_update_blob_value(self):
        """Test saving simple ls thing with blob value, then updating the blobValue."""
        
        # Create a project with first blobValue
        name = str(uuid.uuid4())
        file_name = 'blob_test.png'
        file_path = self._get_path(file_name)
        file_bytes = self._get_bytes(file_path)

        # Save with Path path
        meta_dict = {
            "name": name,
            "is_restricted": True,
            "status": "active",
            "start_date": time.time(),
            "procedure_document": file_path
        }
        newProject = Project(self.client, **meta_dict)
        newProject.save()
        self._check_blob_equal(newProject.metadata['project metadata']['procedure document'], file_name, file_bytes)
        
        # Then update with a different file
        file_name = '1_1_Generic.xlsx'
        file_path = self._get_path(file_name)
        file_bytes = self._get_bytes(file_path)
        new_blob_val = BlobValue(file_path=file_path)
        newProject.metadata['project metadata']['procedure document'] = new_blob_val
        newProject.save()
        self._check_blob_equal(newProject.metadata['project metadata']['procedure document'], file_name, file_bytes)


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

class TestOfflineLsThing(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures, if any."""
        self.client = acasclient.client(creds=None, offline=True)
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        """Tear down test fixtures, if any."""
    
    def test_001_instantiate_thing(self):
        """Test creating a SimpleLsThing in offline mode"""
        name = str(uuid.uuid4())
        meta_dict = {
            "name": name,
            "is_restricted": True,
            "status": "active",
            "start_date": time.time()
        }
        newProject = Project(self.client, **meta_dict)
        self.assertIsNone(newProject.code_name)
        self.assertIsNone(newProject._ls_thing.id)
        self.assertTrue(newProject.metadata["project metadata"]["is restricted"].code)
        try:
            newProject.save()
        except NotImplementedError:
            pass