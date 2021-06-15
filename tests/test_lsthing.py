#!/usr/bin/env python

"""Tests for `acasclient` package."""

import unittest
from acasclient import acasclient
from acasclient.lsthing import SimpleLsThing, CodeValue, BlobValue
from pathlib import Path
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
                'procedure document': BlobValue(procedure_document)
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
        data = newProject.metadata['project metadata']['procedure document'].get_data(self.client)
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
        data = newProject.metadata['project metadata']['procedure document'].get_data(self.client)
        self.assertEqual(data, file_bytes)
