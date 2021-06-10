#!/usr/bin/env python

"""Tests for `acasclient` package."""

import unittest
from acasclient import acasclient
from acasclient.lsthing import SimpleLsThing, CodeValue
import time
import uuid
# SETUP
# "bob" user name registered
# "PROJ-00000001" registered


class Project(SimpleLsThing):
    ls_type = 'project'
    ls_kind = 'project'
    preferred_label_kind = 'project name'

    def __init__(self, name=None, alias=None, start_date=None, status=None, is_restricted=True, recorded_by=None):
        names = {'project name': name, "project alias": alias}
        metadata = {
            'project metadata': {
                'start date': start_date,
                'project status': CodeValue(status, "project", "status", "ACAS DDICT"),
                'is restricted': CodeValue(str(is_restricted).lower(), "project", "restricted", "ACAS DDICT")
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
        """Test creds from file."""
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
