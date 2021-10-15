#!/usr/bin/env python

"""Tests for `acasclient` package."""

import os
import tempfile
from datetime import datetime
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

FWD_ITX = 'relates to'
BACK_ITX = 'is related to'


class Project(SimpleLsThing):
    ls_type = PROJECT
    ls_kind = PROJECT
    preferred_label_kind = PROJECT_NAME

    def __init__(self, name=None, alias=None, start_date=None, status=None, is_restricted=True, procedure_document=None, pdf_document=None, recorded_by=None,
                 ls_thing=None):
        names = {PROJECT_NAME: name, PROJECT_ALIAS: alias}
        metadata = {
            PROJECT_METADATA: {
                START_DATE: start_date,
                PROJECT_STATUS: CodeValue(status, PROJECT, STATUS, ACAS_DDICT),
                IS_RESTRICTED: CodeValue(str(is_restricted).lower(), PROJECT, RESTRICTED, ACAS_DDICT),
                PROCEDURE_DOCUMENT: BlobValue(file_path=procedure_document),
                PDF_DOCUMENT: FileValue(file_path=pdf_document)
            }
        }
        super(Project, self).__init__(ls_type=self.ls_type, ls_kind=self.ls_kind, names=names, recorded_by=recorded_by,
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
        files_to_delete = ['dummy.pdf', 'dummy2.pdf']
        for f in files_to_delete:
            file = Path(f)
            if file.exists():
                os.remove(file)

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
            START_DATE_KEY: datetime.now()
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
            START_DATE_KEY: datetime.now(),
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
            START_DATE_KEY: datetime.now(),
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
            START_DATE_KEY: datetime.now(),
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
            START_DATE_KEY: datetime.now(),
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
            START_DATE_KEY: datetime.now(),
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
        file_name_2 = 'dummy2.pdf'
        file_test_path_2 = Path(__file__).resolve().parent\
            .joinpath('test_acasclient', file_name_2)

        # Save with Path value
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: datetime.now(),
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
            START_DATE_KEY: datetime.now(),
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
            START_DATE_KEY: datetime.now(),
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
            START_DATE_KEY: datetime.now(),
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
            fv.download_to_disk(self.client, folder_path="GARBAGE")
        try:
            fv.download_to_disk(self.client, folder_path="GARBAGE")
        except ValueError as err:
            self.assertIn("does not exist", err.args[0])

        # Test updating other values on a saved Thing
        saved_project = Project.get_by_code(newProject.code_name, self.client, Project.ls_type, Project.ls_kind)
        saved_project.metadata[PROJECT_METADATA][STATUS_KEY] = 'inactive'
        saved_project.save(self.client)

        # Test updating FileValue on a saved Thing
        saved_project = Project.get_by_code(newProject.code_name, self.client, Project.ls_type, Project.ls_kind)
        saved_project.metadata[PROJECT_METADATA][PDF_DOCUMENT] = FileValue(file_path=file_test_path_2)
        saved_project.save(self.client)
        fv = saved_project.metadata[PROJECT_METADATA][PDF_DOCUMENT]
        downloaded_path = fv.download_to_disk(self.client)
        self._check_file(downloaded_path, file_name_2, file_test_path_2)

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

    def test_005_create_interactions(self):
        name = str(uuid.uuid4())
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: datetime.now()
        }
        name_2 = str(uuid.uuid4())
        meta_dict_2 = {
            NAME_KEY: name_2,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: "active",
            START_DATE_KEY: datetime.now()
        }
        proj_1 = Project(recorded_by=self.client.username, **meta_dict)
        proj_1.save(self.client)
        proj_2 = Project(recorded_by=self.client.username, **meta_dict_2)
        proj_2.save(self.client)
        # add an interaction
        proj_1.add_link(FWD_ITX, proj_2, recorded_by=self.client.username)
        assert len(proj_1.links) == 1
        # save the interaction
        proj_1.save(self.client)
        # Fetch project 1 and look at the interaction
        fresh_proj_1 = Project.get_by_code(proj_1.code_name, self.client, Project.ls_type, Project.ls_kind)
        assert len(fresh_proj_1.links) == 1
        assert len(fresh_proj_1._ls_thing.second_ls_things) == 1
        assert fresh_proj_1._ls_thing.second_ls_things[0].ls_kind == f'{Project.ls_type}_{Project.ls_type}'
        # check if save populated second_ls_things properly
        # FIXME: save is not properly populating second_ls_things
        # assert len(proj_1._ls_thing.second_ls_things) == 1
        itx_ls_thing_ls_thing = fresh_proj_1._ls_thing.second_ls_things[0]
        assert itx_ls_thing_ls_thing.id is not None
        # Fetch project 2 again and look at the interaction in reverse
        fresh_proj_2 = Project.get_by_code(proj_2.code_name, self.client, Project.ls_type, Project.ls_kind)
        assert len(fresh_proj_2.links) == 1
        back_itx = fresh_proj_2.links[0]
        assert back_itx.verb == BACK_ITX
        # Run advanced search by interaction
        # Forward interaction query
        second_itx_listings = [
            {
                "interactionType": FWD_ITX,
                "thingType": Project.ls_type,
                "thingKind": Project.ls_kind,
                "operator": "=",
                "thingCodeName": proj_2.code_name
            }]
        results = self.client\
            .advanced_search_ls_things('project', 'project', None,
                                       second_itx_listings=second_itx_listings,
                                       codes_only=True,
                                       max_results=1000,
                                       combine_terms_with_and=True)
        assert len(results) == 1
        assert results[0] == proj_1.code_name
        # Backwards interaction query
        first_itx_listings = [
            {
                "interactionType": FWD_ITX,
                "thingType": Project.ls_type,
                "thingKind": Project.ls_kind,
                "operator": "=",
                "thingCodeName": proj_1.code_name
            }]
        results = self.client\
            .advanced_search_ls_things('project', 'project', None,
                                       first_itx_listings=first_itx_listings,
                                       codes_only=True,
                                       max_results=1000,
                                       combine_terms_with_and=True)
        assert len(results) == 1
        assert results[0] == proj_2.code_name

        # Save new ls things to test interaction subject and object type customization
        name_3 = str(uuid.uuid4())
        name_4 = str(uuid.uuid4())
        meta_dict.update({'name': name_3})
        meta_dict_2.update({'name': name_4})
        proj_1 = Project(recorded_by=self.client.username, **meta_dict)
        proj_1.save(self.client)
        proj_2 = Project(recorded_by=self.client.username, **meta_dict_2)
        proj_2.save(self.client)
        # add an interaction and override the subject and object types
        subject_type = 'test'
        object_type = 'me'
        proj_1.add_link(FWD_ITX, proj_2, recorded_by=self.client.username, subject_type=subject_type, object_type=object_type)
        assert len(proj_1.links) == 1
        # save the interaction
        proj_1.save(self.client)
        # Fetch project 1 and look at the interaction
        fresh_proj_1 = Project.get_by_code(proj_1.code_name, self.client, Project.ls_type, Project.ls_kind)
        assert len(fresh_proj_1.links) == 1
        assert len(fresh_proj_1._ls_thing.second_ls_things) == 1
        assert fresh_proj_1._ls_thing.second_ls_things[0].ls_kind == f'{subject_type}_{object_type}'

    def test_006_simple_thing_overide_label_and_state_types(self):
        class ExampleThing(SimpleLsThing):
            ls_type = "parent"
            ls_kind = "Example Thing"
            ID_LS_TYPE = "corpName"
            NAME_LS_TYPE = "MyNameType"
            ALIAS_LS_TYPE = "MyAliasType"
            METADATA_LS_TYPE = "MyMetaDataType"
            RESULTS_LS_TYPE = "MyResultsType"

            def __init__(self, name=None, alias=None, id=None, recorded_by=None, metadata={}, results={}, ls_thing=None):
                # ID "corpName" "Example Thing" will be created on save because
                # it cooresponds to a saved label sequence with matching type and kind attributes
                # Its important to send in a '' on initial save
                ids = {'Example Thing': ''}
                names = {'MyNameKind': name}
                aliases = {'MyAliasKind': alias}

                super().__init__(ls_type=self.ls_type, ls_kind=self.ls_kind, names=names, aliases=aliases, ids=ids, recorded_by=recorded_by,
                                 metadata=metadata, results=results, ls_thing=ls_thing)

        name = str(uuid.uuid4())
        alias = str(uuid.uuid4())
        meta_dict = {
            'alias': alias,
            'name': name,
            'results': {
                'experimental': {
                    'My Result': 134,
                    'My Result Date': datetime.now()
                }
            },
            'metadata': {
                'general': {
                    'Species': "Rat",
                    'Description': "This is an in vitro pharamacology assay"
                }
            }
        }
        newExampleThing = ExampleThing(recorded_by=self.client.username, **meta_dict)
        newExampleThing.save(self.client)
        # Confirm that the label types are being saved correctly
        assert len(newExampleThing._ls_thing.ls_labels) == 3
        assert newExampleThing._ls_thing.ls_labels[0].ls_type in [ExampleThing.ID_LS_TYPE, ExampleThing.NAME_LS_TYPE, ExampleThing.ALIAS_LS_TYPE]
        assert newExampleThing._ls_thing.ls_labels[1].ls_type in [ExampleThing.ID_LS_TYPE, ExampleThing.NAME_LS_TYPE, ExampleThing.ALIAS_LS_TYPE]
        assert newExampleThing._ls_thing.ls_labels[2].ls_type in [ExampleThing.ID_LS_TYPE, ExampleThing.NAME_LS_TYPE, ExampleThing.ALIAS_LS_TYPE]

        # Confirm that the state types are being saved correctly
        assert newExampleThing._ls_thing.ls_states[0].ls_type in [ExampleThing.METADATA_LS_TYPE, ExampleThing.RESULTS_LS_TYPE]
        assert newExampleThing._ls_thing.ls_states[1].ls_type in [ExampleThing.METADATA_LS_TYPE, ExampleThing.RESULTS_LS_TYPE]

        # Verify that the example thing picked up a corpName label sequence
        fresh_example_thing = ExampleThing.get_by_code(newExampleThing.code_name, self.client, ExampleThing.ls_type, ExampleThing.ls_kind)
        # The label sequence for example thing is in the format ET-000001 so check it fetched a new label and is in the ids field
        assert fresh_example_thing.ids['Example Thing'].startswith('ET-')


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
