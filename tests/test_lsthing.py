#!/usr/bin/env python

"""Tests for `acasclient` package."""

import os
from datetime import datetime
import uuid
import logging
from pathlib import Path

from acasclient.ddict import ACASDDict, ACASLsThingDDict
from acasclient.lsthing import (BlobValue, CodeValue, FileValue, LsThingValue,
                                SimpleLsThing, get_lsKind_to_lsvalue)
from acasclient.validation import ValidationResult, get_validation_response
from tests.test_acasclient import BaseAcasClientTest


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Constants
from tests.project_thing import (
    PROJECT_METADATA, PROJECT, STATUS, PROJECT_STATUS,PROCEDURE_DOCUMENT,PDF_DOCUMENT, 
    NAME_KEY, IS_RESTRICTED_KEY, STATUS_KEY, START_DATE_KEY, DESCRIPTION_KEY, 
    PDF_DOCUMENT_KEY, PROCEDURE_DOCUMENT_KEY, PARENT_PROJECT_KEY, ACTIVE, INACTIVE,
    Project
)

FWD_ITX = 'relates to'
BACK_ITX = 'is related to'

class TestLsThing(BaseAcasClientTest):
    """Tests for `acasclient lsthing` package model."""

    # See test_acasclient.BaseAcasClientTest for setUp

    def tearDown(self):
        """Tear down test fixtures, if any."""
        files_to_delete = ['dummy.pdf', 'dummy2.pdf']
        for f in files_to_delete:
            file = Path(f)
            if file.exists():
                os.remove(file)
        super().tearDown()

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

    def _test_codevalue_missing_error(self, message, value, code_type, code_kind, code_origin):
        base_msg = "'{code}' is not yet in the database as a valid '{code_kind}'. Please double-check the spelling and correct your data if you expect this to match an existing term. If this is a novel valid term, please contact your administrator to add it to the following dictionary: Code Type: {code_type}, Code Kind: {code_kind}, Code Origin: {code_origin}"
        expected_msg = base_msg.format(code=value, code_type=code_type, code_kind=code_kind, code_origin=code_origin)
        self.assertEqual(message, expected_msg)


    # Tests
    def test_000_simple_ls_thing_save(self):
        """Test saving simple ls thing."""
        name = str(uuid.uuid4())
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: ACTIVE,
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
            STATUS_KEY: ACTIVE,
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
            STATUS_KEY: ACTIVE,
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
            STATUS_KEY: ACTIVE,
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
            STATUS_KEY: ACTIVE,
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
            STATUS_KEY: ACTIVE,
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
            STATUS_KEY: ACTIVE,
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
            STATUS_KEY: ACTIVE,
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
            STATUS_KEY: ACTIVE,
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
            STATUS_KEY: ACTIVE,
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
        STATUS_DDICT = ACASDDict(PROJECT, STATUS)
        saved_project.metadata[PROJECT_METADATA][PROJECT_STATUS] = CodeValue(INACTIVE, ddict=STATUS_DDICT)
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
            STATUS_KEY: ACTIVE,
            START_DATE_KEY: datetime.now()
        }
        name_2 = str(uuid.uuid4())
        meta_dict_2 = {
            NAME_KEY: name_2,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: ACTIVE,
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

    def test_007_advanced_search_interactions(self):

        # Create project 1
        name = str(uuid.uuid4())
        status_1 = str(uuid.uuid4())
        desc_1 = str(uuid.uuid4())
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: status_1,
            START_DATE_KEY: datetime.now(),
            DESCRIPTION_KEY: desc_1
        }

        proj_1 = Project(recorded_by=self.client.username, **meta_dict)
        # skip CodeValue validation since this is not a valid status
        proj_1.save(self.client, skip_validation=True)

        # Create project 2
        name_2 = str(uuid.uuid4())
        status_2 = str(uuid.uuid4())
        desc_2 = str(uuid.uuid4())
        meta_dict_2 = {
            NAME_KEY: name_2,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: status_2,
            START_DATE_KEY: datetime.now(),
            DESCRIPTION_KEY: desc_2
        }
        proj_2 = Project(recorded_by=self.client.username, **meta_dict_2)
        # skip CodeValue validation since this is not a valid status
        proj_2.save(self.client, skip_validation=True)

        # Add interactions between projects
        proj_1.add_link(FWD_ITX, proj_2, recorded_by=self.client.username)
        assert len(proj_1.links) == 1
        # skip CodeValue validation since this is not a valid status
        proj_1.save(self.client, skip_validation=True)

        # Run advanced search by interaction w/value matching on the interaction thing
        # Forward interaction query w/interaction thing values
        # Code value search
        second_itx_listings = [
            {
                "lsType": FWD_ITX,
                "lsKind": "project_project",
                "thingType": Project.ls_type,
                "thingKind": Project.ls_kind,
                "thingValues": [
                    {
                    	"value": status_2,
						"stateType": "metadata",
						"stateKind": "project metadata",
						"valueType": "codeValue",
						"valueKind": "project status",
						"operator": "~"
                    }
                ]
            }
        ]
        results = self.client\
            .advanced_search_ls_things('project', 'project', None,
                                       second_itx_listings=second_itx_listings,
                                       format="nestedfull",
                                       max_results=1000,
                                       combine_terms_with_and=True)
        assert len(results) == 1
        assert results[0]["codeName"] == proj_1.code_name

        # String value search
        second_itx_listings = [
            {
                "interactionType": FWD_ITX,
                "thingType": Project.ls_type,
                "thingKind": Project.ls_kind,
                "thingCodeName": proj_2.code_name,
                "thingValues": [
                    {
                    	"value": desc_2,
						"stateType": "metadata",
						"stateKind": "project metadata",
						"valueType": "stringValue",
						"valueKind": "description",
						"operator": "~"
                    }
                ]
            }
        ]
        results = self.client\
            .advanced_search_ls_things('project', 'project', None,
                                       second_itx_listings=second_itx_listings,
                                       format="nestedfull",
                                       max_results=1000,
                                       combine_terms_with_and=True)
        assert len(results) == 1
        assert results[0]["codeName"] == proj_1.code_name

        # Upper case search using ~ which should still match
        second_itx_listings = [
            {
                "interactionType": FWD_ITX,
                "thingType": Project.ls_type,
                "thingKind": Project.ls_kind,
                "thingCodeName": proj_2.code_name,
                "thingValues": [
                    {
                    	"value": desc_2.upper(),
						"stateType": "metadata",
						"stateKind": "project metadata",
						"valueType": "stringValue",
						"valueKind": "description",
						"operator": "~"
                    }
                ]
            }
        ]
        results = self.client\
            .advanced_search_ls_things('project', 'project', None,
                                       second_itx_listings=second_itx_listings,
                                       format="nestedfull",
                                       max_results=1000,
                                       combine_terms_with_and=True)
        assert len(results) == 1
        assert results[0]["codeName"] == proj_1.code_name

        # String value search make sure it doesn't return the wrong project (this should not return any results)
        second_itx_listings = [
            {
                "interactionType": FWD_ITX,
                "thingType": Project.ls_type,
                "thingKind": Project.ls_kind,
                "thingCodeName": proj_2.code_name,
                "thingValues": [
                    {
                    	"value": desc_1,
						"stateType": "metadata",
						"stateKind": "project metadata",
						"valueType": "stringValue",
						"valueKind": "description",
						"operator": "~"
                    }
                ]
            }
        ]
        results = self.client\
            .advanced_search_ls_things('project', 'project', None,
                                       second_itx_listings=second_itx_listings,
                                       format="nestedfull",
                                       max_results=1000,
                                       combine_terms_with_and=True)
        assert len(results) == 0

    def test_008_validate_codevalue(self):
        """Test creating CodeValues using code + code_type + code_kind + code_origin
        Confirm that invalid code values are rejected by validate method.
        """
        # Create project 1
        name = str(uuid.uuid4())
        status_1 = str(uuid.uuid4())
        desc_1 = str(uuid.uuid4())
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: status_1,
            START_DATE_KEY: datetime.now(),
            DESCRIPTION_KEY: desc_1
        }
        proj_1 = Project(recorded_by=self.client.username, **meta_dict)
        valid = proj_1.validate(self.client)
        assert not valid
        messages = valid.get_messages()
        assert len(messages) == 1
        self._test_codevalue_missing_error(messages[0], status_1, PROJECT, STATUS, 'ACAS DDict')
        # Now test timing of one-by-one validation with 20 projects versus doing it in bulk
        # Create 20 valid projects
        meta_dict[STATUS_KEY] = ACTIVE
        projects = [Project(recorded_by=self.client.username, **meta_dict) for i in range(20)]
        single_start = datetime.now()
        for proj in projects:
            valid = proj.validate(self.client)
            assert valid
        single_end = datetime.now()
        single_duration = single_end - single_start
        logger.info(f"Single validation took {single_duration}")
        valid = Project.validate_list(self.client, projects)
        assert valid
        bulk_end = datetime.now()
        bulk_duration = bulk_end - single_end
        logger.info(f"Bulk validation took {bulk_duration}")
        assert single_duration > bulk_duration

    def test_009_validate_ddicts(self):
        """Test creating CodeValues using code + DDict
        Confirm that invalid code values are rejected by validate method.
        """
        # Create project 1
        name = str(uuid.uuid4())
        desc_1 = str(uuid.uuid4())
        meta_dict = {
            NAME_KEY: name,
            IS_RESTRICTED_KEY: True,
            START_DATE_KEY: datetime.now(),
            DESCRIPTION_KEY: desc_1
        }

        proj_1 = Project(recorded_by=self.client.username, **meta_dict)
        # set status to a CodeValue constructed with a DDict
        STATUS_DDICT = ACASDDict(PROJECT, STATUS)
        proj_1.metadata[PROJECT_METADATA][PROJECT_STATUS] = CodeValue(ACTIVE, ddict=STATUS_DDICT)
        # Because we are referencing a valid status, this should not raise an error
        valid = proj_1.validate(self.client)
        assert valid
        assert len(valid.get_messages()) == 0
        # Now try setting status to an invalid CodeValue
        status_1 = str(uuid.uuid4())
        proj_1.metadata[PROJECT_METADATA][PROJECT_STATUS] = CodeValue(status_1, ddict=STATUS_DDICT)
        valid = proj_1.validate(self.client)
        assert not valid
        assert len(valid.get_messages()) == 1
        self._test_codevalue_missing_error(valid.get_messages()[0], status_1, PROJECT, STATUS, 'ACAS DDict')
        # Now try adding a CodeValue that references an LsThing
        # First we create and save a new LsThing so we can get a code_name
        proj_1.metadata[PROJECT_METADATA][PROJECT_STATUS] = CodeValue(ACTIVE, ddict=STATUS_DDICT)
        proj_1.save(self.client)
        # Then we create a new project 2 and set PARENT_PROJECT_KEY to reference `proj_1`
        name_2 = str(uuid.uuid4())
        desc_2 = str(uuid.uuid4())
        PARENT_PROJECT_DDICT = ACASLsThingDDict(PROJECT, PROJECT)
        meta_dict = {
            NAME_KEY: name_2,
            IS_RESTRICTED_KEY: True,
            START_DATE_KEY: datetime.now(),
            DESCRIPTION_KEY: desc_2
        }
        proj_2 = Project(recorded_by=self.client.username, **meta_dict)
        proj_2.metadata[PROJECT_METADATA][PARENT_PROJECT_KEY] = CodeValue(proj_1.code_name, ddict=PARENT_PROJECT_DDICT)
        # Because we are referencing a valid LsThing, this should be valid
        valid = proj_2.validate(self.client)
        assert valid
        # Now try setting parent project to an invalid CodeValue and confirm validation fails
        bad_project_code = str(uuid.uuid4())
        proj_2.metadata[PROJECT_METADATA][PARENT_PROJECT_KEY] = CodeValue(bad_project_code, ddict=PARENT_PROJECT_DDICT)
        valid = proj_2.validate(self.client)
        assert not valid
        self._test_codevalue_missing_error(valid.get_messages()[0], bad_project_code, PROJECT, PROJECT, 'ACAS LsThing')
        # Generate validation response and check it
        validation_response = get_validation_response(valid, ls_thing=proj_2)
        # Confirm the structure of the response body
        assert validation_response.get("commit") is False
        self.assertEqual(validation_response.get("transaction_id"), -1)
        assert validation_response.get("hasError") is True
        assert validation_response.get("hasWarning") is False
        assert validation_response.get("results") is not None
        assert validation_response.get("results").get("thing") is not None
        # Check we have one message and it is an error
        self.assertEqual(len(validation_response.get("errorMessages")), 1)
        msg = validation_response.get("errorMessages")[0]
        self.assertEqual(msg.get("errorLevel"), "error")
        # Do a loose check of the html summary and confirm it contains mention of our bad code
        assert bad_project_code in validation_response['results']['htmlSummary']


    def test_008_get_by_code(self):
        """
        If no lsthing entry is found for the given `code_name`, `ls_type` and
        `ls_kind` then `get_by_code` should raise KeyError.
        """

        with self.assertRaises(KeyError):
            _ = SimpleLsThing.get_by_code(code_name='baz', client=self.client,
            ls_type='foo', ls_kind='bar')


class TestBlobValue(BaseAcasClientTest):

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

class TestValidationResponse(BaseAcasClientTest):

    def test_001_response_with_errors_and_warnings(self):
        """
        Test creating a ValidationResponse with errors and warnings.
        """
        ERR_MSG = 'error 1'
        WARN_MSG = 'warning 1'
        SUMM_MSG = 'summary 1'
        # Create a warning
        warn = ValidationResult(True, [WARN_MSG])
        assert warn
        assert len(warn.get_messages()) == 1
        assert len(warn.get_warnings()) == 1
        assert warn.get_warnings()[0] == WARN_MSG
        assert len(warn.get_errors()) == 0

        # Create an error
        err = ValidationResult(False, [ERR_MSG])
        assert not err
        assert len(err.get_messages()) == 1
        assert len(err.get_warnings()) == 0
        assert len(err.get_errors()) == 1
        assert err.get_errors()[0] == ERR_MSG

        # Create a summary
        summary = ValidationResult(True, summaries=[SUMM_MSG])

        # Add them
        valid = warn + err
        assert not valid
        assert len(valid.get_messages()) == 2
        assert valid.get_messages()[0] == ERR_MSG
        assert valid.get_messages()[1] == WARN_MSG
        assert len(valid.get_errors()) == 1
        assert valid.get_errors()[0] == ERR_MSG
        assert len(valid.get_warnings()) == 1
        assert valid.get_warnings()[0] == WARN_MSG

        # Add in the summary
        valid = valid + summary
        assert not valid
        assert len(valid.get_messages()) == 3
        assert valid.get_messages()[2] == SUMM_MSG
        assert len(valid.get_summaries()) == 1
        assert valid.get_summaries()[0] == SUMM_MSG

        # Generate and check a response
        response = get_validation_response(valid)
        # Confirm the structure of the response body
        assert response.get("commit") is False
        self.assertEqual(response.get("transaction_id"), -1)
        assert response.get("hasError") is True
        assert response.get("hasWarning") is True
        assert response.get("results") is not None
        # Check we have two messages: one error, one warning
        self.assertEqual(len(response.get("errorMessages")), 2)
        self.assertEqual(response.get("errorMessages")[0].get("errorLevel"), "error")
        self.assertEqual(response.get("errorMessages")[1].get("errorLevel"), "warning")
        # Confirm HTML summary contains both messages
        assert ERR_MSG in response['results']['htmlSummary']
        assert WARN_MSG in response['results']['htmlSummary']

        # Create a ValidationResult with error and warning at once
        valid = ValidationResult(False, errors=[ERR_MSG], warnings=[WARN_MSG])
        assert len(valid.get_messages()) == 2

        # Create an invalid ValidationResult by giving an error message but saying it is valid
        try:
            invalid = ValidationResult(True, errors=[ERR_MSG], warnings=[WARN_MSG])
            assert False
        except ValueError as e:
            assert str(e) == "ValidationResult cannot be valid and contain error messages"

    def test_002_html_summary(self):
        """
        Test the HTML Summary generated by ValidationResult
        """
        ERR_INSTRUCT = "<p>Please fix the following errors and use the 'Back' button at the bottom of this screen to upload a new version of the data.</p>"
        WARN_INSTRUCT = "<p>Please review the warnings and summary before uploading.</p>"
        SUCCESS_INSTRUCT = "<p>Please review the summary before uploading.</p>"
        COMMIT_INSTRUCT = "<p>Upload completed.</p>"
        ERR_1 = 'error 1'
        ERR_2 = 'error 2'
        WARN_1 = 'warning 1'
        WARN_2 = 'warning 2'
        SUMM_1 = 'summary 1'
        SUMM_2 = 'summary 2'
        # No errors or warnings
        res = ValidationResult(True)
        html = get_validation_response(res).get('results').get('htmlSummary')
        self.assertEqual(html.strip(), SUCCESS_INSTRUCT)
        # 1 errors 1 warning
        res = ValidationResult(False, errors=[ERR_1], warnings=[WARN_1])
        html = get_validation_response(res).get('results').get('htmlSummary')
        self.assertIn(ERR_INSTRUCT, html)
        self.assertIn('<h4 style="color:red">Errors: 1 </h4>', html)
        self.assertIn('<h4>Warnings: 1 </h4>', html)
        self.assertIn(f"<li>{ERR_1}</li>", html)
        self.assertIn(f"<li>{WARN_1}</li>", html)
        # Multiple errors & warnings, including dupes
        res = ValidationResult(False, errors=[ERR_1, ERR_2, ERR_1], warnings=[WARN_1, WARN_1, WARN_2])
        html = get_validation_response(res).get('results').get('htmlSummary')
        self.assertIn('<h4 style="color:red">Errors: 2 </h4>', html)
        self.assertIn('<h4>Warnings: 2 </h4>', html)
        self.assertIn(f'<li>2 occurrences of: {ERR_1}</li>', html)
        self.assertNotIn(f"<li>{ERR_1}</li>", html)
        self.assertIn(f"<li>{ERR_2}</li>", html)
        self.assertIn(f'<li>2 occurrences of: {WARN_1}</li>', html)
        self.assertIn(f"<li>{WARN_2}</li>", html)
        # Warnings, no errors
        res = ValidationResult(True, warnings=[WARN_1, WARN_2])
        html = get_validation_response(res).get('results').get('htmlSummary')
        self.assertIn(WARN_INSTRUCT, html)
        self.assertIn('<h4>Warnings: 2 </h4>', html)
        self.assertNotIn('<h4 style="color:red">Errors:', html)
        # Errors, no warnings
        res = ValidationResult(False, errors=[ERR_1, ERR_2])
        html = get_validation_response(res).get('results').get('htmlSummary')
        self.assertIn(ERR_INSTRUCT, html)
        self.assertIn('<h4 style="color:red">Errors: 2 </h4>', html)
        self.assertNotIn('<h4>Warnings:', html)
        # Errors, warnings, and summaries
        res = ValidationResult(False, errors=[ERR_1, ERR_2], warnings=[WARN_1, WARN_2], summaries=[SUMM_1, SUMM_2])
        html = get_validation_response(res).get('results').get('htmlSummary')
        self.assertIn(ERR_INSTRUCT, html)
        self.assertIn('<h4 style="color:red">Errors: 2 </h4>', html)
        self.assertIn('<h4>Warnings: 2 </h4>', html)
        self.assertIn('<h4>Summary</h4>', html)
        self.assertIn(f"<li>{SUMM_1}</li>", html)
        self.assertIn(f"<li>{SUMM_2}</li>", html)
        # Commit should hide warnings and show a different message
        res = ValidationResult(True, warnings=[WARN_1], summaries=[SUMM_1])
        html = get_validation_response(res, commit=True).get('results').get('htmlSummary')
        self.assertIn(COMMIT_INSTRUCT, html)
        self.assertNotIn(ERR_INSTRUCT, html)
        self.assertNotIn('<h4 style="color:red">Errors:', html)
        self.assertNotIn('<h4>Warnings:', html)
        self.assertIn('<h4>Summary</h4>', html)
        self.assertIn(f"<li>{SUMM_1}</li>", html)
