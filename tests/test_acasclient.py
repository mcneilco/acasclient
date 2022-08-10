#!/usr/bin/env python

"""Tests for `acasclient` package."""

from functools import wraps
import unittest
from acasclient import acasclient
from pathlib import Path
import tempfile
import shutil
import uuid
import json
import operator
import signal
import requests

# Import project ls thing
from datetime import datetime
# Constants
from tests.project_thing import (
    NAME_KEY, IS_RESTRICTED_KEY, STATUS_KEY, START_DATE_KEY, ACTIVE, PROJECT_NAME,
    Project
)

EMPTY_MOL = """
  Mrv1818 02242010372D          

  0  0  0  0  0  0            999 V2000
M  END
"""

ACAS_NODEAPI_BASE_URL = "http://localhost:3001"

BASIC_EXPERIMENT_LOAD_EXPERIMENT_NAME = "BLAH"
STEREO_CATEGORY="Unknown"
class Timeout:
    def __init__(self, seconds=1, error_message='Timeout'):
        self.seconds = seconds
        self.error_message = error_message
    def handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)
    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)
    def __exit__(self, type, value, traceback):
        signal.alarm(0)

# Code to anonymize experiments for testing
def remove_common(object):
    # Remove fields which are subject to change and are commmon for groups, states, values classes
    object["id"] = None
    object["recordedDate"] = None
    object["modifiedDate"] = None
    object["lsTransaction"] = None
    object["version"] = None
    return object

def remove_common_group(group):
    # Remove fields which are subject to change and are in common for group classes
    remove_common(group)
    group["codeName"] = None
    return group

def remove_common_state(state):
    # Remove fields which are subject to change and are in common for all state classes
    remove_common(state)
    return state

def remove_common_value(value):
    # Remove fields which are subject to change and are in common for all value classes
    remove_common(value)
    value["analysisGroupCode"] = None
    value["analysisGroupId"] = None
    value["stateId"] = None 

    # Round numeric values to 5 digits for comparison on different systems where calculations like EC50 might be different
    if value['lsType'] == "numericValue":
        if value["numericValue"] is not None:
            value["numericValue"] = round(value["numericValue"], 5)
    
    # Round uncertainty values as their calculations may vary from system to system
    if 'uncertainty' in value and value['uncertainty'] is not None:
        value["uncertainty"] = round(value["uncertainty"], 5)

def clean_group(group):
    group['key'] =  None
    remove_common_group(group)
    for state in group["lsStates"]:
        remove_common_state(state)
        for value in state["lsValues"]:
            remove_common_value(value)
            # If key is curve id it is subject to change so just set it to a standard name for testing
            if value['lsKind'] == "curve id":
                value["stringValue"] = "FakeCurveIDJustForTesting"
            # If there is a "Key" lsKind in the lsValues then we set it on the groups so that we can sort the groups
            # later by the key (this is for diffing puroses as part of the test)
            elif value['lsKind'] == "Key":
                group['key'] = value['numericValue']
        state["lsValues"] = sorted(state["lsValues"], key=operator.itemgetter('lsKind','ignored'))

    group["lsStates"] = sorted(group["lsStates"], key=operator.itemgetter('lsType','lsKind','ignored'))
    return group
    
def anonymize_experiment_dict(experiment):
    # Anonymizes an experiment by removing keys which are subject to change each time the experiment is loaded
    # It also sorts the analysis groups by an analysis group value lsKind "Key" if present in the upload file
    # This key was added to the Dose Response upload file for these testing purposes
    for analysis_group in experiment["analysisGroups"]:
        clean_group(analysis_group)
        # TODO: Treatment and Subject groups are not included in the diff because it was difficult to get them sorted
        # correctly. One way to do this is might be to sort the keys by dose and response values.
        analysis_group["treatmentGroups"] = None
        # Leaving this code as reference for future when we want to sort the groups by some key
        # for tg in analysis_group["treatmentGroups"]:
        #     clean_group(tg)
        #     for sg in tg["subjects"]:
        #         clean_group(sg)
    experiment["analysisGroups"] = sorted(experiment["analysisGroups"], key=operator.itemgetter('key'))
    return experiment

def create_project_thing(code, name=None, alias=None):
    if name is None:
        name = code
    if alias is None:
        alias = name
    ls_thing = {
        "lsType": "project",
        "lsKind": "project",
        "recordedBy": "bob",
        "recordedDate": 1586877284571,
        "lsLabels": [
            {
                "lsType": "name",
                "lsKind": "project name",
                "labelText": name,
                "ignored": False,
                "preferred": True,
                "recordedDate": 1586877284571,
                "recordedBy": "bob",
                "physicallyLabled": False,
                "thingType": "project",
                "thingKind": "project"
            },
            {
                "lsType": "name",
                "lsKind": "project alias",
                "labelText": alias,
                "ignored": False,
                "preferred": False,
                "recordedDate": 1586877284571,
                "recordedBy": "bob",
                "physicallyLabled": False,
                "thingType": "project",
                "thingKind": "project"
            }
        ],
        "lsStates": [
            {
                "lsType": "metadata",
                "lsKind": "project metadata",
                "lsValues": [
                    {
                        "lsType": "dateValue",
                        "lsKind": "start date",
                        "ignored": False,
                        "recordedDate": 1586877284571,
                        "recordedBy": "bob",
                        "dateValue": 1586877284571
                    }, {
                        "lsType": "codeValue",
                        "lsKind": "project status",
                        "ignored": False,
                        "recordedDate": 1586877284571,
                        "recordedBy": "bob",
                        "codeKind": "status",
                        "codeType": "project",
                        "codeOrigin": "ACAS DDICT",
                        "codeValue": "active"
                    }, {
                        "lsType": "codeValue",
                        "lsKind": "is restricted",
                        "ignored": False,
                        "recordedDate": 1586877284571,
                        "recordedBy": "bob",
                        "codeKind": "restricted",
                        "codeType": "project",
                        "codeOrigin": "ACAS DDICT",
                        "codeValue": "false"
                    }
                ],
                "ignored": False,
                "recordedDate": 1586877284571,
                "recordedBy": "bob"
            }
        ],
        "lsTags": [],
        "codeName": code
    }
    return ls_thing


def create_thing_with_blob_value(code):
    # Function for creating a thing with a blob value
    # Returns a  thing, file name and bytes_array for unit testing purposes

    # Get a file to load
    file_name = 'blob_test.png'
    blob_test_path = Path(__file__).resolve().parent\
        .joinpath('test_acasclient', file_name)
    f = open(blob_test_path, "rb")
    bytes_array = f.read()

    # Need to save blob value as an int array not bytes
    int_array_to_save = [x for x in bytes_array]
    f.close()

    # Create an Ls thing and add the blob value
    # comments should be the file name
    code = str(uuid.uuid4())
    ls_thing = create_project_thing(code)
    blob_value = {
        "lsType": "blobValue",
        "blobValue": int_array_to_save,
        "lsKind": "my file",
        "ignored": False,
        "recordedDate": 1586877284571,
        "recordedBy": "bob",
        "comments": file_name
    }
    ls_thing["lsStates"][0]["lsValues"].append(blob_value)

    # Return thing file and bytes array for testing
    return ls_thing, file_name, bytes_array

def requires_node_api(func):
    """
    Decorator to skip tests if the node API is not available
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            requests.get(ACAS_NODEAPI_BASE_URL)
        except requests.exceptions.ConnectionError:
            print('WARNING: ACAS Node API is not available. Skipping tests which require it.')
            raise unittest.SkipTest("Node API is not available")
        return func(*args, **kwargs)
    return wrapper

@requires_node_api
def delete_backdoor_user(username):
    """ Deletes a backdoor user created for testing purposes """
    r = requests.delete(ACAS_NODEAPI_BASE_URL + "/api/systemTest/deleteTestUser/" + username)
    r.raise_for_status()

@requires_node_api
def create_backdoor_user(username, password, acas_user=True, acas_admin=False, creg_user=False, creg_admin=False, project_names=None):
    """ Creates a backdoor user for testing purposes """
    body = {
        "username": username,
        "password": password,
        "acasUser": acas_user,
        "acasAdmin": acas_admin,
        "cmpdregUser": creg_user,
        "cmpdregAdmin": creg_admin,
        "projectNames": project_names or []
    }
    r = requests.post(ACAS_NODEAPI_BASE_URL + "/api/systemTest/getOrCreateTestUser", json=body)
    r.raise_for_status()
    return r.json()

@requires_node_api
def get_or_create_global_project():
    """ Creates a global project for testing purposes """
    r = requests.get(ACAS_NODEAPI_BASE_URL + "/api/systemTest/getOrCreateGlobalProject")
    r.raise_for_status()
    output = r.json()
    return output["messages"]

def requires_basic_cmpd_reg_load(func):
    """
    Decorator to load the basic cmpdreg data if it is not already loaded
    """
    @wraps(func)
    def wrapper(self):
        if self.client.get_meta_lot('CMPD-0000001-001') is None or self.client.get_meta_lot('CMPD-0000002-001') is None:
            self.basic_cmpd_reg_load()
        return func(self)
    return wrapper

def requires_absent_basic_cmpd_reg_load(func):
    """
    Decorator to load the basic cmpdreg data if it is not already loaded
    """
    @wraps(func)
    def wrapper(self):
        meta_lot = self.client.get_meta_lot('CMPD-0000001-001')
        if meta_lot is not None:
            self.delete_all_experiments()
            self.delete_all_cmpd_reg_bulk_load_files()
        return func(self)   
    return wrapper

def requires_basic_experiment_load(func):
    """
    Decorator to load the basic experiment data if it is not already loaded, returns None as a fallback if the experiment is not loaded
    """
    @requires_basic_cmpd_reg_load
    @wraps(func)
    def wrapper(self):
        # Get experiments with the expected experiment name
        experiments = self.client.get_experiment_by_name(BASIC_EXPERIMENT_LOAD_EXPERIMENT_NAME)

        # If there is one already loaded then thats the one we want.
        current_experiment = None
        for experiment in experiments:
            if experiment['ignored'] == False and experiment['deleted'] == False:
                current_experiment = experiment
                break

        # If we don't have one already loaded, then load it
        if current_experiment is None:
            self.basic_experiment_load()
            experiments = self.client.get_experiment_by_name(BASIC_EXPERIMENT_LOAD_EXPERIMENT_NAME)
            # Verify that th eexperiment is loaded and return it
            for experiment in experiments:
                if experiment['ignored'] == False and experiment['deleted'] == False:
                    current_experiment = experiment
                    break
        return func(self, current_experiment)
    return wrapper

class BaseAcasClientTest(unittest.TestCase):
    """ Base class for ACAS Client tests """

    # To run before EVERY test using this class
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    # To run after EVERY test using this class
    def tearDown(self):
        """Tear down test fixtures, if any."""
        shutil.rmtree(self.tempdir)

    # To run ONCE before running tests using this class
    @classmethod
    def setUpClass(self):
        """Set up test fixtures, if any."""
        creds = acasclient.get_default_credentials()
        self.test_usernames = []
        try:
            self.client = acasclient.client(creds)
        except RuntimeError:
            # Create the default user if it doesn't exist
            if creds.get('username'):
                self.test_usernames.append(creds.get('username'))
                create_backdoor_user(creds.get('username'), creds.get('password'), acas_user=True, acas_admin=True, creg_user=True, creg_admin=True)
            # Login again
            self.client = acasclient.client(creds)
        # Ensure Global project is there
        projects = self.client.projects()
        global_project = [p for p in projects if p.get('name') == 'Global']
        if not global_project:
            # Create the global project
            global_project = get_or_create_global_project()
        else:
            global_project = global_project[0]
        self.global_project_code = global_project["code"]

        # Set TestCase - maxDiff to None to allow for a full diff output when comparing large dictionaries
        self.maxDiff = None
        
    # To run ONCE after running tests using this class
    @classmethod
    def tearDownClass(self):
        """ Delete all experiments and bulk load files
        """

        try:
            self.delete_all_experiments(self)
            print("Successfully deleted all experiments")
        except Exception as e:
            print("Error deleting experiments in tear down: " + str(e))

        try:
            self.delete_all_cmpd_reg_bulk_load_files(self)
            print("Successfully deleted all cmpdreg bulk load files")
        except Exception as e:
            print("Error deleting bulkloaded files in tear down: " + str(e))

        try:
            self.delete_all_projects(self)
            print("Successfully deleted all projects (except Global)")
        except Exception as e:
            print("Error deleting all projects in tear down: " + str(e))

        try:    
            for username in self.test_usernames:
                delete_backdoor_user(username)
        finally:
            self.client.close()

    @requires_node_api
    def create_and_connect_backdoor_user(self, username = None, password = None, **kwargs):
        """ Creates a backdoor user and connects them to the ACAS node API """
        if username is None:
            username = "acas-user-"+str(uuid.uuid4())
        if password is None:
            password = str(uuid.uuid4())
        create_backdoor_user(username = username, password = password, **kwargs)
        self.test_usernames.append(username)
        user_creds = {
            'username': username,
            'password': password,
            'url': self.client.url
        }
        user_client = acasclient.client(user_creds)
        return user_client

    # Helper for testing an experiment upload was successful
    def experiment_load_test(self, data_file_to_upload, dry_run_mode):
        response = self.client.\
            experiment_loader(data_file_to_upload, "bob", dry_run_mode)
        self.assertIn('results', response)
        self.assertIn('htmlSummary', response['results'])
        self.assertIn('errorMessages', response)
        self.assertIn('hasError', response)
        self.assertIn('hasWarning', response)
        self.assertIn('transactionId', response)
        if dry_run_mode:
            self.assertIsNone(response['transactionId'])
        else:
            self.assertIsNotNone(response['transactionId'])
        return response

    def delete_all_experiments(self):
        """ Deletes all experiments """
        # Currently search is the only way to get all protocols
        self.basic_experiment_load_code = None
        protocols = self.client.protocol_search("*")
        for protocol in protocols:
            for experiment in protocol["experiments"]:
                if experiment["ignored"] == False and experiment["deleted"] == False:
                    self.client.delete_experiment(experiment["codeName"])

            # Verify all experiments are now gone for this protocol
        all_protocols = self.client.protocol_search("*")
        not_deleted_experiments = []
        for protocol in all_protocols:
            # Loop through all experiments and make sure they are either deleted or ignored
            for experiment in protocol["experiments"]:
                if experiment["ignored"] == False and experiment["deleted"] == False:
                    not_deleted_experiments.append(experiment["codeName"])

        if len(not_deleted_experiments) > 0:
            raise Exception("Failed to delete all experiments: " + str(not_deleted_experiments))
                    

    def delete_all_cmpd_reg_bulk_load_files(self):
        """ Deletes all cmpdreg bulk load files in order by id """

        files = self.client.\
            get_cmpdreg_bulk_load_files()
        
        # sort by id in reverse order to delete most recent first
        files.sort(key=lambda x: x['id'], reverse=True)
        for file in files:
            response = self.client.purge_cmpdreg_bulk_load_file(file['id'])

        # Verify all files are now gone
        files = self.client.\
            get_cmpdreg_bulk_load_files()
        if len(files) > 0:
            # Get the ids of all the files
            ids = [file['id'] for file in files]
            # Throw exception not failure
            raise ValueError(f"Failed to delete some cmpd reg bulk load files: {ids}")


    def delete_all_projects(self):
        """ Deletes all projects except Global (PROJ-00000001) """
        # Currently search is the only way to get all protocols
        projects = self.client.get_ls_things_by_type_and_kind('project', 'project')
        projects_to_delete =  []
        for project in projects:
            if project['codeName'] != "PROJ-00000001" and project['deleted'] == False and project['ignored'] == False:
                project['deleted'] = True
                project['ignored'] = True
                projects_to_delete.append(project)

        if len(projects_to_delete) > 0:
            self.client.update_ls_thing_list(projects_to_delete)

        projects = self.client.get_ls_things_by_type_and_kind('project', 'project')
        not_deleted_projects = []
        for project in projects:
            if project['codeName'] != "PROJ-00000001" and project['deleted'] == False and project['ignored'] == False:
                not_deleted_projects.append(project['codeName'])
        
        if len(not_deleted_projects) > 0:
            raise Exception("Failed to delete all projects: " + str(not_deleted_projects))

    def create_basic_project_with_roles(self):
        """ Creates a basic project with roles """
        project_name = str(uuid.uuid4())
        meta_dict = {
            NAME_KEY: project_name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: ACTIVE,
            START_DATE_KEY: datetime.now()
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        newProject.save(self.client)

        # Create a new role to go along with the project
        role_kind = {
                "typeName": "Project",
                "kindName": newProject.code_name
        }
        self.client.setup_items("rolekinds", [role_kind])
        ls_role = {
                "lsType": "Project",
                "lsKind": newProject.code_name,
                "roleName": "User"
        }
        self.client.setup_items("lsroles", [ls_role])
        return newProject

    def basic_experiment_load(self):
        data_file_to_upload = Path(__file__).resolve()\
                        .parent.joinpath('test_acasclient', 'uniform-commas-with-quoted-text.csv')
        response = self.client.\
            experiment_loader(data_file_to_upload, "bob", False)
        return response

    def basic_cmpd_reg_load(self, project_code = None, file = None):
        """ Loads the basic cmpdreg data end result being CMPD-0000001-001 and CMPD-0000002-001 are loaded """
        if project_code is None:
            project_code = self.global_project_code
        
        if file is None:
            file = Path(__file__).resolve().parent\
                .joinpath('test_acasclient', 'test_012_register_sdf.sdf')


        mappings = [
                {
                    "dbProperty": "Parent Common Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Parent Common Name"
                },
                {
                    "dbProperty": "Parent Corp Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Parent Corp Name"
                },
                {
                    "dbProperty": "Lot Barcode",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Barcode"
                },
                {
                    "dbProperty": "Lot Amount",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Amount"
                },
                {
                    "dbProperty": "Lot Amount Units",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Amount Units"
                },
                {
                    "dbProperty": "Lot Color",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Appearance"
                },
                {
                    "dbProperty": "Lot Synthesis Date",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Date Prepared"
                },
                {
                    "dbProperty": "Lot Notebook Page",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Notebook"
                },
                {
                    "dbProperty": "Lot Corp Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Corp Name"
                },
                {
                    "dbProperty": "Lot Number",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Number"
                },
                {
                    "dbProperty": "Lot Purity",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Purity"
                },
                {
                    "dbProperty": "Lot Comments",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Register Comment"
                },
                {
                    "dbProperty": "Lot Chemist",
                    "defaultVal": "bob",
                    "required": True,
                    "sdfProperty": "Lot Scientist"
                },
                {
                    "dbProperty": "Lot Solution Amount",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Solution Amount"
                },
                {
                    "dbProperty": "Lot Solution Amount Units",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Solution Amount Units"
                },
                {
                    "dbProperty": "Lot Supplier",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Source"
                },
                {
                    "dbProperty": "Lot Supplier ID",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Source ID"
                },
                {
                    "dbProperty": "CAS Number",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "CAS"
                },
                {
                    "dbProperty": "Project",
                    "defaultVal": project_code,
                    "required": True,
                    "sdfProperty": "Project Code Name"
                },
                {
                    "dbProperty": "Parent Common Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Name"
                },
                {
                    "dbProperty": "Parent Stereo Category",
                    "defaultVal": STEREO_CATEGORY,
                    "required": True,
                    "sdfProperty": None
                },
                {
                    "dbProperty": "Parent Stereo Comment",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Structure Comment"
                },
                {
                    "dbProperty": "Lot Is Virtual",
                    "defaultVal": "False",
                    "required": False,
                    "sdfProperty": "Lot Is Virtual"
                },
                {
                    "dbProperty": "Lot Supplier Lot",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Sample ID2"
                },
                {
                    "dbProperty": "Lot Salt Abbrev",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Salt Name"
                },
                {
                    "dbProperty": "Lot Salt Equivalents",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Salt Equivalents"
                },
                {
                    "dbProperty": "Parent Alias",
                    "defaultVal": "unknown",
                    "required": True,
                    "sdfProperty": "Parent Alias"
                }
            ]

        response = self.client.register_sdf(file, "bob",
                                            mappings)
        return response


    def _get_or_create_codetable(self, get_method, create_method, code, name):
        """
        Utility function to test creation of simple entities
        """
        # Get all
        codetables = get_method()
        already_exists = code.lower() in [ct['code'].lower() for ct in codetables]
        # Return it if it already exists
        if already_exists:
            result = [ct for ct in codetables if ct['code'].lower() == code.lower()][0]
        else:
            # Create and expect success
            result = create_method(code=code, name=name)
            self.assertIsNotNone(result.get('id'))
        return result
    
    def _create_dupe_codetable(self, create_method, code, name):
        with self.assertRaises(requests.HTTPError) as context:
            resp = create_method(code=code, name=name)
        self.assertIn('409 Client Error: Conflict', str(context.exception))


class TestAcasclient(BaseAcasClientTest):
    """Tests for `acasclient` package."""

    def test_000_creds_from_file(self):
        """Test creds from file."""
        file_credentials = Path(__file__).resolve().\
            parent.joinpath('test_acasclient',
                            'test_000_creds_from_file_credentials')
        creds = acasclient.creds_from_file(
            file_credentials,
            'acas')
        self.assertIn("username", creds)
        self.assertIn("password", creds)
        self.assertIn("url", creds)
        self.assertEqual(creds['username'], 'bob')
        self.assertEqual(creds['password'], 'secret')
        creds = acasclient.creds_from_file(file_credentials,
                                           'different')
        self.assertIn("username", creds)
        self.assertIn("password", creds)
        self.assertIn("url", creds)
        self.assertEqual(creds['username'], 'differentuser')
        self.assertEqual(creds['password'], 'secret')

    def test_001_get_default_credentials(self):
        """Test get default credentials."""
        acasclient.get_default_credentials()

    def test_002_client_initialization(self):
        """Test initializing client."""
        creds = acasclient.get_default_credentials()
        client = acasclient.client(creds)
        client.close()

        # Verify bad creds 401 response
        bad_creds = acasclient.get_default_credentials()
        bad_creds['password'] = 'badpassword'
        with self.assertRaises(RuntimeError) as context:
            acasclient.client(bad_creds)
        self.assertIn('Failed to login. Please check credentials.', str(context.exception))


    def test_003_projects(self):
        """Test projects."""
        projects = self.client.projects()
        self.assertGreater(len(projects), 0)
        self.assertIn('active', projects[0])
        self.assertIn('code', projects[0])
        self.assertIn('id', projects[0])
        self.assertIn('isRestricted', projects[0])
        self.assertIn('name', projects[0])

    def test_004_upload_files(self):
        """Test upload files."""
        test_003_upload_file_file = Path(__file__).resolve().parent.\
            joinpath('test_acasclient', '1_1_Generic.xlsx')
        files = self.client.upload_files([test_003_upload_file_file])
        self.assertIn('files', files)
        self.assertIn('name', files['files'][0])
        self.assertIn('originalName', files['files'][0])
        self.assertEqual(files['files'][0]["originalName"], '1_1_Generic.xlsx')

    @requires_absent_basic_cmpd_reg_load
    def test_005_register_sdf_request(self):
        """Test register sdf request."""
        test_012_upload_file_file = Path(__file__).resolve().parent\
            .joinpath('test_acasclient', 'test_012_register_sdf.sdf')
        files = self.client.upload_files([test_012_upload_file_file])
        request = {
            "fileName": files['files'][0]["name"],
            "userName": "bob",
            "mappings": [
                {
                    "dbProperty": "Parent Common Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Name"
                },
                {
                    "dbProperty": "Parent Corp Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Parent Corp Name"
                },
                {
                    "dbProperty": "Lot Amount",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Amount Prepared"
                },
                {
                    "dbProperty": "Lot Amount Units",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Amount Units"
                },
                {
                    "dbProperty": "Lot Color",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Appearance"
                },
                {
                    "dbProperty": "Lot Synthesis Date",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Date Prepared"
                },
                {
                    "dbProperty": "Lot Notebook Page",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Notebook"
                },
                {
                    "dbProperty": "Lot Corp Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Corp Name"
                },
                {
                    "dbProperty": "Lot Number",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Number"
                },
                {
                    "dbProperty": "Lot Purity",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Purity"
                },
                {
                    "dbProperty": "Lot Comments",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Register Comment"
                },
                {
                    "dbProperty": "Lot Chemist",
                    "defaultVal": "bob",
                    "required": True,
                    "sdfProperty": "Lot Scientist"
                },
                {
                    "dbProperty": "Lot Solution Amount",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Solution Amount"
                },
                {
                    "dbProperty": "Lot Solution Amount Units",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Solution Amount Units"
                },
                {
                    "dbProperty": "Lot Supplier",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Source"
                },
                {
                    "dbProperty": "Lot Supplier ID",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Source ID"
                },
                {
                    "dbProperty": "CAS Number",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "CAS"
                },
                {
                    "dbProperty": "Project",
                    "defaultVal": self.global_project_code,
                    "required": True,
                    "sdfProperty": "Project Code Name"
                },
                {
                    "dbProperty": "Parent Common Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Name"
                },
                {
                    "dbProperty": "Parent Stereo Category",
                    "defaultVal": "Unknown",
                    "required": True,
                    "sdfProperty": None
                },
                {
                    "dbProperty": "Parent Stereo Comment",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Structure Comment"
                },
                {
                    "dbProperty": "Lot Is Virtual",
                    "defaultVal": "False",
                    "required": False,
                    "sdfProperty": "Lot Is Virtual"
                },
                {
                    "dbProperty": "Lot Supplier Lot",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Sample ID2"
                },
                {
                    "dbProperty": "Lot Salt Abbrev",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Salt Name"
                },
                {
                    "dbProperty": "Lot Salt Equivalents",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Salt Equivalents"
                }
            ]

        }
        response = self.client.register_sdf_request(request)
        self.assertIn('reportFiles', response[0])
        self.assertIn('summary', response[0])
        self.assertIn('Number of entries processed', response[0]['summary'])

    @requires_absent_basic_cmpd_reg_load
    def test_006_register_sdf(self):
        """Test register sdf."""
        response = self.basic_cmpd_reg_load()
        self.assertIn('report_files', response)
        self.assertIn('summary', response)
        self.assertIn('id', response)
        self.assertIn('Number of entries processed', response['summary'])
        # Confirm the report.log file is created and is plaintext
        report_log = [rf for rf in response['report_files'] if '_report.log' in rf['name']][0]
        report_log_contents = report_log['content'].decode('utf-8')
        self.assertIn('Number of entries processed', report_log_contents)
        self.assertNotIn('<div', report_log_contents)
        return response

    @requires_basic_cmpd_reg_load
    def test_007_cmpd_search_request(self):
        """Test cmpd search request."""

        searchRequest = {
            "corpNameList": "",
            "corpNameFrom": "",
            "corpNameTo": "",
            "aliasContSelect": "contains",
            "alias": "",
            "dateFrom": "",
            "dateTo": "",
            "searchType": "substructure",
            "percentSimilarity": 90,
            "chemist": "anyone",
            "maxResults": 100,
            "molStructure": (
                "NSC 1390\n"
                "\n"
                "\n"
                " 10 11  0  0  0  0  0  0  0  0999 V2000\n"
                "   -4.4591   -4.9405    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -2.6905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -7.1905    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -0.4344   -2.9770    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "    0.4473   -4.1905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -1.8610   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -1.8610   -4.9405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -5.6905    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -0.4344   -5.4040    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -4.4591   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "  1  8  1  0  0  0  0\n"
                "  1 10  1  0  0  0  0\n"
                "  2 10  2  0  0  0  0\n"
                "  2  6  1  0  0  0  0\n"
                "  3  8  2  0  0  0  0\n"
                "  4  5  1  0  0  0  0\n"
                "  4  6  1  0  0  0  0\n"
                "  5  9  2  0  0  0  0\n"
                "  6  7  2  0  0  0  0\n"
                "  7  8  1  0  0  0  0\n"
                "  7  9  1  0  0  0  0\n"
                "M  END")
        }
        search_results = self.client.\
            cmpd_search_request(searchRequest)
        self.assertGreater(len(search_results["foundCompounds"]), 0)

        searchRequest = {
            "molStructure": (
                "NSC 1390\n"
                "\n"
                "\n"
                " 10 11  0  0  0  0  0  0  0  0999 V2000\n"
                "   -4.4591   -4.9405    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -2.6905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -7.1905    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -0.4344   -2.9770    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "    0.4473   -4.1905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -1.8610   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -1.8610   -4.9405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -5.6905    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -0.4344   -5.4040    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -4.4591   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "  1  8  1  0  0  0  0\n"
                "  1 10  1  0  0  0  0\n"
                "  2 10  2  0  0  0  0\n"
                "  2  6  1  0  0  0  0\n"
                "  3  8  2  0  0  0  0\n"
                "  4  5  1  0  0  0  0\n"
                "  4  6  1  0  0  0  0\n"
                "  5  9  2  0  0  0  0\n"
                "  6  7  2  0  0  0  0\n"
                "  7  8  1  0  0  0  0\n"
                "  7  9  1  0  0  0  0\n"
                "M  END"),
        }
        search_results = self.client.\
            cmpd_search_request(searchRequest)
        self.assertGreater(len(search_results["foundCompounds"]), 0)

    @requires_basic_cmpd_reg_load
    def test_008_cmpd_search(self):
        """Test cmpd search request."""

        molStructure = (
            "NSC 1390\n"
            "\n"
            "\n"
            " 10 11  0  0  0  0  0  0  0  0999 V2000\n"
            "   -4.4591   -4.9405    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "   -3.1600   -2.6905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "   -3.1600   -7.1905    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "   -0.4344   -2.9770    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "    0.4473   -4.1905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "   -1.8610   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "   -1.8610   -4.9405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "   -3.1600   -5.6905    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "   -0.4344   -5.4040    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "   -4.4591   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "  1  8  1  0  0  0  0\n"
            "  1 10  1  0  0  0  0\n"
            "  2 10  2  0  0  0  0\n"
            "  2  6  1  0  0  0  0\n"
            "  3  8  2  0  0  0  0\n"
            "  4  5  1  0  0  0  0\n"
            "  4  6  1  0  0  0  0\n"
            "  5  9  2  0  0  0  0\n"
            "  6  7  2  0  0  0  0\n"
            "  7  8  1  0  0  0  0\n"
            "  7  9  1  0  0  0  0\n"
            "M  END")
        search_results = self.client.\
            cmpd_search(molStructure=molStructure)
        self.assertGreater(len(search_results["foundCompounds"]), 0)

    @requires_basic_cmpd_reg_load
    def test_009_export_cmpd_search_results(self):
        """Test export cmpd search results."""
        search_results = {
            "foundCompounds": [
                {
                    "lotIDs": [
                        {
                            "corpName": "CMPD-0000001-001"
                        }
                    ],
                }
            ]
        }
        # Full search results possibilities
        # search_results = {
        #     "foundCompounds": [
        #         {
        #             "corpName": "CMPD-0000001",
        #             "corpNameType": "Parent",
        #             "lotIDs": [
        #                 {
        #                     "buid": 0,
        #                     "corpName": "CMPD-0000001-001",
        #                     "lotNumber": 1,
        #                     "registrationDate": "01/29/2020",
        #                     "synthesisDate": "01/29/2020"
        #                 }
        #             ],
        #             "molStructure": "MOLFILE STRUCTURE"
        #             "parentAliases": [],
        #             "stereoCategoryName": "Achiral",
        #             "stereoComment": ""
        #         }
        #     ],
        #     "lotsWithheld": False
        # }
        search_results_export = self.client.\
            export_cmpd_search_results(search_results)
        self.assertIn('reportFilePath', search_results_export)
        self.assertIn('summary', search_results_export)

    @requires_basic_cmpd_reg_load
    def test_010_export_cmpd_search_results_get_file(self):
        """Test export cmpd search results get file."""
        search_results = {
            "foundCompounds": [
                {
                    "lotIDs": [
                        {
                            "corpName": "CMPD-0000001-001"
                        }
                    ],
                }
            ]
        }
        search_results_export = self.client.\
            export_cmpd_search_results(search_results)
        self.assertIn('reportFilePath', search_results_export)
        self.assertIn('summary', search_results_export)
        self.assertEquals(search_results_export['summary'], "Successfully exported 1 lots.")
        search_results_export = self.client.\
            get_file(search_results_export['reportFilePath'])

    @requires_basic_cmpd_reg_load
    def test_011_get_sdf_file_for_lots(self):
        """Test get sdf file for lots."""
        search_results_export = self.client.\
            get_sdf_file_for_lots(["CMPD-0000001-001"])
        self.assertIn('content', search_results_export)
        content = str(search_results_export['content'])
        self.assertIn('<Parent Corp Name>\\nCMPD-0000001', content)
        self.assertIn('<Lot Corp Name>\\nCMPD-0000001-001', content)
        self.assertIn(f'<Project>\\n{self.global_project_code}', content)
        self.assertIn('<Parent Stereo Category>\\nUnknown', content)
        self.assertIn('content-type', search_results_export)
        self.assertIn('name', search_results_export)
        self.assertIn('content-length', search_results_export)
        self.assertIn('last-modified', search_results_export)

    @requires_basic_cmpd_reg_load
    def test_012_write_sdf_file_for_lots(self):
        """Test get sdf file for lots."""
        out_file_path = self.client.\
            write_sdf_file_for_lots(["CMPD-0000001-001"], Path(self.tempdir))
        self.assertTrue(out_file_path.exists())
        out_file_path = self.client\
            .write_sdf_file_for_lots(["CMPD-0000001-001"],
                                     Path(self.tempdir, "output.sdf"))
        self.assertTrue(out_file_path.exists())
        self.assertEqual('output.sdf', out_file_path.name)

    @requires_basic_cmpd_reg_load
    def test_013_experiment_loader_request(self):
        """Test experiment loader request."""
        data_file_to_upload = Path(__file__).\
            resolve().parent.joinpath('test_acasclient', '1_1_Generic.xlsx')
        files = self.client.upload_files([data_file_to_upload])
        request = {"user": "bob",
                   "fileToParse": files['files'][0]["name"],
                   "reportFile": "",
                   "imagesFile": None,
                   "dryRunMode": True}
        response = self.client.experiment_loader_request(request)
        self.assertIn('results', response)
        self.assertIn('errorMessages', response)
        self.assertIn('hasError', response)
        self.assertIn('hasWarning', response)
        self.assertIn('transactionId', response)
        self.assertIsNone(response['transactionId'])
        request = {"user":
                   "bob",
                   "fileToParse": files['files'][0]["name"],
                   "reportFile": "", "imagesFile": None,
                   "dryRunMode": False}
        response = self.client.experiment_loader_request(request)
        self.assertIn('transactionId', response)
        self.assertIsNotNone(response['transactionId'])

    @requires_basic_experiment_load
    def test_015_get_protocols_by_label(self, experiment):
        """Test get protocols by label"""
        protocols = self.client.get_protocols_by_label("Test Protocol")
        self.assertGreater(len(protocols), 0)
        self.assertIn('codeName', protocols[0])
        self.assertIn('lsLabels', protocols[0])
        self.assertEqual(protocols[0]["lsLabels"][0]["labelText"],
                         "Test Protocol")
        fakeProtocols = self.client.get_protocols_by_label("Fake Protocol")
        self.assertEqual(len(fakeProtocols), 0)

    @requires_basic_experiment_load
    def test_016_get_experiments_by_protocol_code(self, experiment):
        """Test get experiments by protocol code."""
        protocols = self.client.get_protocols_by_label("Test Protocol")
        experiments = self.client.\
            get_experiments_by_protocol_code(protocols[0]["codeName"])
        self.assertGreater(len(experiments), 0)
        self.assertIn('codeName', experiments[0])
        self.assertIn('lsLabels', experiments[0])
        self.assertEqual(experiments[0]["lsLabels"][0]["labelText"],
                         "Test Experiment")
        experiments = self.client.\
            get_experiments_by_protocol_code("FAKECODE")
        self.assertIsNone(experiments)

    @requires_basic_experiment_load
    def test_017_get_experiment_by_code(self, experiment):
        """Test get experiment by code."""
        experiment = self.client.get_experiment_by_code(experiment['codeName'])
        self.assertIn('codeName', experiment)
        self.assertIn('lsLabels', experiment)
        experiment = self.client.get_experiment_by_code("FAKECODE")
        self.assertIsNone(experiment)

    @requires_basic_experiment_load
    def test_018_get_source_file_for_experient_code(self, experiment):
        """Test get source file for experiment code."""
        experiment = self.client.get_experiment_by_code(experiment['codeName'])
        source_file = self.client.\
            get_source_file_for_experient_code(experiment['codeName'])
        self.assertIn('content', source_file)
        self.assertIn('content-type', source_file)
        self.assertIn('name', source_file)
        self.assertIn('content-length', source_file)
        self.assertIn('last-modified', source_file)
        source_file = self.client.\
            get_source_file_for_experient_code("FAKECODE")
        self.assertIsNone(source_file)

    @requires_basic_experiment_load
    def test_019_write_source_file_for_experient_code(self, experiment):
        """Test get source file for experiment code."""
        source_file_path = self.client.\
            write_source_file_for_experient_code(experiment['codeName'], self.tempdir)
        self.assertTrue(source_file_path.exists())

    def test_020_setup_types(self):
        """Test setup types."""
        # Create a new project
        project_name = str(uuid.uuid4())
        meta_dict = {
            NAME_KEY: project_name,
            IS_RESTRICTED_KEY: True,
            STATUS_KEY: ACTIVE,
            START_DATE_KEY: datetime.now()
        }
        newProject = Project(recorded_by=self.client.username, **meta_dict)
        newProject.save(self.client)

        # Create a new role to go along with the project
        role_kind = {
            	"typeName": "Project",
				"kindName": newProject.code_name
        }
        saved_kinds = self.client.setup_items("rolekinds", [role_kind])
        self.assertEqual(len(saved_kinds), 1)
        self.assertIn("lsType", saved_kinds[0])
        self.assertEqual(saved_kinds[0]["lsType"]["typeName"], "Project")
        self.assertEqual(saved_kinds[0]['kindName'], newProject.code_name)

        ls_role = {
            	"lsType": "Project",
				"lsKind": newProject.code_name,
				"roleName": "User"
        }
        saved_ls_roles = self.client.setup_items("lsroles", [ls_role])
        self.assertEqual(len(saved_ls_roles), 1)
        self.assertEqual(saved_ls_roles[0]['lsType'], "Project")
        self.assertEqual(saved_ls_roles[0]['lsKind'], newProject.code_name)
        self.assertEqual(saved_ls_roles[0]['roleName'], "User")

    @requires_basic_experiment_load
    def test_021_experiment_search(self, experiment):
        """Test experiment generic search."""
        results = self.client.\
            experiment_search('EXPT')
        self.assertIsNotNone(results)
        self.assertGreater(len(results), 0)
        self.assertIn('codeName', results[0])

    @requires_basic_cmpd_reg_load
    def test_022_get_cmpdreg_bulk_load_files(self):
        """Test get cmpdreg bulk load files."""
        results = self.client.\
            get_cmpdreg_bulk_load_files()
        self.assertIsNotNone(results)
        self.assertGreater(len(results), 0)
        self.assertIn('fileDate', results[0])

    @requires_absent_basic_cmpd_reg_load
    @requires_basic_experiment_load
    def test_023_check_cmpdreg_bulk_load_file_dependency(self, experiment):
        """Test cmpdreg bulk load file dependency."""
        files = self.client.\
            get_cmpdreg_bulk_load_files()
        results = self.client.\
            check_cmpdreg_bulk_load_file_dependency(-1)
        self.assertIsNone(results)

        results = self.client.\
            check_cmpdreg_bulk_load_file_dependency(files[0]["id"])
        self.assertIsNotNone(results)
        self.assertIn('canPurge', results)
        self.assertFalse(results['canPurge'])
        self.assertIn('summary', results)

        # Now delete the experiment
        self.client.delete_experiment(experiment["codeName"])
        
        # Now check dependency again
        results = self.client.\
            check_cmpdreg_bulk_load_file_dependency(files[0]["id"])
        self.assertIsNotNone(results)
        self.assertIn('canPurge', results)
        self.assertTrue(results['canPurge'])
        self.assertIn('summary', results)

    @requires_basic_cmpd_reg_load
    def test_024_purge_cmpdreg_bulk_load_file(self):
        """Test cmpdreg bulk load file dependency."""

        results = self.client.\
            purge_cmpdreg_bulk_load_file(-1)
        self.assertIsNone(results)

        test_012_upload_file_file = Path(__file__).resolve().parent\
            .joinpath('test_acasclient', 'test_012_register_sdf.sdf')
        mappings = [{
            "dbProperty": "Parent Stereo Category",
            "defaultVal": "Unknown",
            "required": True,
            "sdfProperty": None
        }]
        registration_result = self.client.register_sdf(test_012_upload_file_file, "bob",
                                                       mappings)
        self.assertIn('New lots of existing compounds: 2', registration_result['summary'])

        # purge the bulk load file
        results = self.client.\
            purge_cmpdreg_bulk_load_file(registration_result["id"])
        self.assertIn('summary', results)
        self.assertIn('Successfully purged file', results['summary'])
        self.assertIn('success', results)
        self.assertTrue(results['success'])

    @requires_basic_experiment_load
    def test_025_delete_experiment(self, experiment):
        """Test delete experiment."""

        response = self.client.\
            delete_experiment(experiment['codeName'])
        self.assertIsNotNone(response)
        self.assertIn('codeValue', response)
        self.assertEqual('deleted', response['codeValue'])
        experiment = self.client.get_experiment_by_code(experiment['codeName'])
        self.assertIsNotNone(experiment)
        self.assertTrue(experiment['ignored'])
        experiment_status = acasclient.\
            get_entity_value_by_state_type_kind_value_type_kind(
                experiment,
                "metadata",
                "experiment metadata",
                "codeValue",
                "experiment status")
        self.assertIn('codeValue', experiment_status)
        self.assertEqual('deleted', experiment_status['codeValue'])

    def test_027_get_ls_thing(self):
        ls_thing = self.client.get_ls_thing("project",
                                            "project",
                                            self.global_project_code)
        self.assertIn('codeName', ls_thing)
        self.assertEqual(self.global_project_code, ls_thing["codeName"])
        ls_thing = self.client.get_ls_thing("project",
                                            "project",
                                            "FAKE")
        self.assertIsNone(ls_thing)

    def test_026_save_ls_thing(self):
        code = str(uuid.uuid4())
        ls_thing = create_project_thing(code)
        saved_ls_thing = self.client.save_ls_thing(ls_thing)
        self.assertIn('codeName', saved_ls_thing)
        self.assertEqual(code, saved_ls_thing["codeName"])

    def test_027_get_ls_things_by_codes(self):
        codes = []
        for n in range(3):
            code = str(uuid.uuid4())
            ls_thing = create_project_thing(code)
            self.client.save_ls_thing(ls_thing)
            codes.append(ls_thing["codeName"])

        ls_things = self.client.get_ls_things_by_codes("project",
                                                       "project",
                                                       codes)
        self.assertEqual(len(ls_things), len(codes))
        self.assertIn('codeName', ls_things[0])
        self.assertIn(ls_things[0]['codeName'], codes)

    def test_028_save_ls_thing_list(self):
        ls_things = []
        for n in range(3):
            code = str(uuid.uuid4())
            ls_things.append(create_project_thing(code))

        saved_ls_things = self.client.save_ls_thing_list(ls_things)
        self.assertEqual(len(saved_ls_things), len(ls_things))
        self.assertIn('codeName', saved_ls_things[0])

    def test_029_update_ls_thing_list(self):
        ls_things = []
        new_codes = []
        for n in range(3):
            code = str(uuid.uuid4())
            ls_thing = create_project_thing(code)
            saved_thing = self.client.save_ls_thing(ls_thing)
            new_code = str(uuid.uuid4())
            new_codes.append(new_code)
            saved_thing["codeName"] = new_code
            ls_things.append(saved_thing)

        updated_ls_things = self.client.update_ls_thing_list(ls_things)
        self.assertEqual(len(updated_ls_things), len(ls_things))
        self.assertIn('codeName', updated_ls_things[0])

    def test_030_get_thing_codes_by_labels(self):
        codes = []
        names = []
        aliases = []
        for n in range(3):
            code = str(uuid.uuid4())
            name = str(uuid.uuid4())
            alias = str(uuid.uuid4())
            ls_thing = create_project_thing(code, name, alias)
            self.client.save_ls_thing(ls_thing)
            codes.append(code)
            names.append(name)
            aliases.append(alias)

        # Verify search by code type and kind works without label filter
        results = self.client.get_thing_codes_by_labels('project',
                                                        'project',
                                                        codes)

        self.assertEqual(len(results), len(codes))
        self.assertIn('preferredName', results[0])
        # Preferred name should be the name sent to the service as preferred, not the code
        self.assertIn(results[0]["preferredName"], names)

        # Adding label type and label kind should not stop searching by code name
        # but the preferred ids should still be the names
        results = self.client.get_thing_codes_by_labels('project',
                                                        'project',
                                                        codes,
                                                        'garbageshouldnotexist',
                                                        'garbageshouldnotexist')
        self.assertEqual(len(results), len(codes))
        self.assertIn(results[0]["preferredName"], names)

        # Searching by labels without limiting by label type/kind  should give results
        results = self.client.get_thing_codes_by_labels('project',
                                                        'project',
                                                        names)
        self.assertEqual(len(results), len(names))
        self.assertIn(results[0]["preferredName"], names)

        # Searching by names and filtering label types and kinds should give no results when no matching
        results = self.client.get_thing_codes_by_labels('project',
                                                        'project',
                                                        names,
                                                        'garbageshouldnotexist',
                                                        'garbageshouldnotexist')
        self.assertEqual(len(results), len(names))
        self.assertEqual(results[0]["preferredName"], '')

        # Searching when code and label is the same should still produce a single response
        codeAndName = str(uuid.uuid4())
        alias = str(uuid.uuid4())
        ls_thing = create_project_thing(codeAndName, codeAndName, alias)
        self.client.save_ls_thing(ls_thing)
        results = self.client.get_thing_codes_by_labels('project',
                                                        'project',
                                                        [codeAndName])
        self.assertEqual(results[0]["preferredName"], codeAndName)

        # Searching by alias should work but still return preferredNames
        results = self.client.get_thing_codes_by_labels('project',
                                                        'project',
                                                        aliases)
        self.assertEqual(len(results), len(names))
        self.assertIn(results[0]["preferredName"], names)

        # Searching by alias should work but still return preferredNames even when specifying labeltype and kind
        results = self.client.get_thing_codes_by_labels('project',
                                                        'project',
                                                        aliases,
                                                        'name',
                                                        'project alias')
        self.assertEqual(len(results), len(names))
        self.assertIn(results[0]["preferredName"], names)

    def test_031_get_saved_entity_codes(self):
        labels = []
        for n in range(3):
            code = str(uuid.uuid4())
            label = str(uuid.uuid4())
            ls_thing = create_project_thing(code, label)
            self.client.save_ls_thing(ls_thing)
            labels.append(label)
        labels.append("FAKE")
        results = self.client.get_saved_entity_codes('project',
                                                     'project',
                                                     labels)
        self.assertEqual(len(results[0]), len(labels)-1)
        self.assertEqual(len(results[1]), 1)

        # Verify that limiting by label type/kind gives correct result
        results = self.client.get_saved_entity_codes('project',
                                                     'project',
                                                     labels,
                                                     'name',
                                                     'project name')
        self.assertEqual(len(results[0]), len(labels)-1)
        self.assertEqual(len(results[1]), 1)

        # Verify that limiting by nonexistant label type/kind give 0 results
        results = self.client.get_saved_entity_codes('project',
                                                     'project',
                                                     labels,
                                                     'badtype',
                                                     'badkind')
        self.assertEqual(len(results[0]), 0)
        self.assertEqual(len(results[1]), len(labels))

    def test_032_advanced_search_ls_things(self):
        codes = []
        for n in range(3):
            code = str(uuid.uuid4())
            ls_thing = create_project_thing(code)
            self.client.save_ls_thing(ls_thing)
            codes.append(code)

        value_listings = [{
            "stateType": "metadata",
            "stateKind": "project metadata",
            "valueType": "codeValue",
            "valueKind": "project status",
            "operator": "="
        }]
        ls_things = self.client\
            .advanced_search_ls_things('project', 'project', 'active',
                                       value_listings=value_listings,
                                       codes_only=False,
                                       max_results=1000)
        self.assertGreaterEqual(len(ls_things), 3)
        self.assertIn('codeName', ls_things[0])

        return_codes = self.client\
            .advanced_search_ls_things('project', 'project', 'active',
                                       value_listings=value_listings,
                                       codes_only=True,
                                       max_results=1000)
        self.assertIn(codes[0], return_codes)

        # Use 'codetable' data 'format'; 'codes_only' is False
        results = self.client\
            .advanced_search_ls_things('project', 'project', 'active',
                                       value_listings=value_listings,
                                       codes_only=False,
                                       max_results=1000,
                                       combine_terms_with_and=True,
                                       format='codetable')
        return_codes = [res['code'] for res in results]
        self.assertIn(codes[0], return_codes)

        # Test 'combine_terms_with_and'
        value_listings[0]['value'] = 'active'
        value_listings.append({
            "stateType": "metadata",
            "stateKind": "project metadata",
            "valueType": "codeValue",
            "valueKind": "project is restricted",
            "operator": "=",
            'value': 'true'  # Default is false
        })

        results = self.client\
            .advanced_search_ls_things('project', 'project', None,
                                       value_listings=value_listings,
                                       codes_only=True,
                                       max_results=1000,
                                       combine_terms_with_and=False)
        assert len(results) >= 3

        results = self.client\
            .advanced_search_ls_things('project', 'project', None,
                                       value_listings=value_listings,
                                       codes_only=True,
                                       max_results=1000,
                                       combine_terms_with_and=True)
        assert len(results) == 0

        # Test with Labels
        label_listings = [
            {
                "labelType": "name",
                "labelKind": "project name",
                "operator": "=",
                "labelText": codes[0]
            }]
        results = self.client\
            .advanced_search_ls_things('project', 'project', None,
                                       label_listings=label_listings,
                                       codes_only=True,
                                       max_results=1000,
                                       combine_terms_with_and=True)
        assert len(results) == 1


    @requires_basic_cmpd_reg_load
    def test_033_get_all_lots(self):
        """Test get all lots request."""

        all_lots = self.client.get_all_lots()
        self.assertGreater(len(all_lots), 0)
        self.assertIn('id', all_lots[0])
        self.assertIn('lotCorpName', all_lots[0])
        self.assertIn('lotNumber', all_lots[0])
        self.assertIn('parentCorpName', all_lots[0])
        self.assertIn('registrationDate', all_lots[0])
        self.assertIn('project', all_lots[0])

    def test_034_get_ls_things_by_type_and_kind(self):
        codes = []
        for n in range(3):
            code = str(uuid.uuid4())
            ls_thing = create_project_thing(code)
            self.client.save_ls_thing(ls_thing)
            codes.append(ls_thing["codeName"])

        ls_things = self.client.get_ls_things_by_type_and_kind("project",
                                                               "project",
                                                               "stub")
        self.assertIn('codeName', ls_things[0])
        returnedCodes = []
        for thing in ls_things:
            if thing['codeName'] in codes:
                returnedCodes.append(thing['codeName'])
        self.assertEqual(len(returnedCodes), len(codes))
        self.assertIn('codeName', ls_things[0])

        # Verify that codectable format works
        ls_things = self.client.get_ls_things_by_type_and_kind("project",
                                                               "project",
                                                               format="codetable")
        self.assertIn('code', ls_things[0])

        # Verify that giving bad format gives ValueError
        with self.assertRaises(ValueError):
            self.client.get_ls_things_by_type_and_kind("project",
                                                       "project",
                                                       format="badformat")

    def test_035_test_create_label_sequence(self):
        labelPrefix = "TESTSEQ"+str(uuid.uuid4())
        sequence = self.client.create_label_sequence(
            labelPrefix, 0, 0, "-", "id_corpName", "parent_compound")
        self.assertIn('dbSequence', sequence)
        self.assertIn(labelPrefix, sequence["labelPrefix"])
        self.assertIn('id_corpName', sequence["labelTypeAndKind"])
        self.assertIn('parent_compound', sequence["thingTypeAndKind"])

    def test_036_get_all_label_sequences(self):
        sequences = self.client.get_all_label_sequences()
        self.assertGreater(len(sequences), 0)
        self.assertIn('dbSequence', sequences[0])
        self.assertIn('labelPrefix', sequences[0])
        self.assertIn('thingTypeAndKind', sequences[0])

    def test_037_get_label_sequence_by_types_and_kinds(self):
        labelTypeAndKind = "id_corpName"
        thingTypeAndKind = "parent_compound"
        sequences = self.client.get_label_sequence_by_types_and_kinds(
            labelTypeAndKind, thingTypeAndKind)
        self.assertGreater(len(sequences), 0)
        for sequence in sequences:
            self.assertEqual(labelTypeAndKind, sequence["labelTypeAndKind"])
            self.assertEqual(thingTypeAndKind, sequence["thingTypeAndKind"])

    def test_038_get_labels(self):
        numberOfLabels = 5
        labels = self.client.get_labels(
            "id_codeName", "document_experiment", numberOfLabels)
        self.assertEqual(len(labels), numberOfLabels)
        for label in labels:
            self.assertIn('autoLabel', label)

    def test_039_get_all_ddict_values(self):
        all_ddict_values = self.client.get_all_ddict_values()
        self.assertGreater(len(all_ddict_values), 0)
        for ddict_value in all_ddict_values:
            self.assertIn('codeType', ddict_value)
            self.assertIn('codeKind', ddict_value)
            self.assertIn('code', ddict_value)

    def test_040_get_ddict_values_by_type_and_kind(self):
        codeType = "experiment metadata"
        codeKind = "file type"
        all_ddict_values = self.client.get_ddict_values_by_type_and_kind(
            codeType, codeKind)
        self.assertGreater(len(all_ddict_values), 0)
        for ddict_value in all_ddict_values:
            self.assertIn('codeType', ddict_value)
            self.assertIn('codeKind', ddict_value)
            self.assertEqual(codeType, ddict_value["codeType"])
            self.assertEqual(codeKind, ddict_value["codeKind"])

    def test_041_get_blob_data_by_value_id(self):
        # Save an ls thing with a blob value
        code = str(uuid.uuid4())
        ls_thing, file_name, bytes_array = create_thing_with_blob_value(code)
        saved_ls_thing = self.client.save_ls_thing(ls_thing)

        # Get the blob value from the saved ls thing (does not contain blobValue data)
        saved_blob_value = None
        for state in saved_ls_thing["lsStates"]:
            for value in state["lsValues"]:
                if value["lsType"] == "blobValue":
                    saved_blob_value = value
                    break

        # Blob value should return and the comments should be set to the file name
        self.assertIsNotNone(saved_blob_value)
        self.assertEqual(saved_blob_value["comments"], file_name)

        # Get the actual blob value data by value id
        blob_data = self.client.get_blob_data_by_value_id(
            saved_blob_value["id"])

        # Assert that the returned blob data is of type bytes and is equal to the blob data sent in
        self.assertEqual(type(blob_data), bytes)
        self.assertEqual(blob_data, bytes_array)

    @requires_absent_basic_cmpd_reg_load
    def test_042_cmpd_structure_search(self):
        """Test cmpd structure search request."""
        # Get a mapping of the registered parents and their structures
        result = self.basic_cmpd_reg_load()
        for file in result['report_files']:
            if file['name'].endswith('registered.sdf'):
                registered_sdf_content = file['parsed_content']
                structures = {}
                for compound in registered_sdf_content:
                    meta_lot = self.client.get_meta_lot(compound['properties']['Registered Lot Corp Name'])
                    if meta_lot is None:
                        self.fail("Expected meta lot to be found for registered compound.")
                    structures[meta_lot['lot']['parent']['id']] = compound['ctab']
                break

        # Search for the structures and verify that the returned parent id matches that of the registered parent id
        for id in structures:
            mol_structure = structures[id]
            search_results = self.client.\
                cmpd_structure_search(molStructure=mol_structure, searchType = "duplicate_tautomer")
            self.assertGreater(len(search_results), 0)
            self.assertEqual(search_results[0], id)


        # Search for an empty mol to verify no false positive
        search_results = self.client.\
            cmpd_structure_search(molStructure=EMPTY_MOL, searchType = "duplicate_tautomer")
        self.assertEqual(len(search_results), 0)

    @requires_node_api
    def test_044_author_and_role_apis(self):
        # Test that as an admin you can fetch authors
        all_authors = self.client.get_authors()
        self.assertGreater(len(all_authors), 0)
        # Test that as an admin you can create an author
        author = {
            "firstName": "John",
            "lastName": "Doe",
            "userName": "jdoe",
            "emailAddress": "john@example.com",
            "password": str(uuid.uuid4()),
        }
        self.test_usernames.append(author['userName'])
        new_author = self.client.create_author(author)
        self.assertEqual(new_author["firstName"], author["firstName"])
        self.assertEqual(new_author["lastName"], author["lastName"])
        self.assertEqual(new_author["userName"], author["userName"])
        self.assertEqual(new_author["emailAddress"], author["emailAddress"])
        self.assertEqual(new_author.get('password'), None)
        self.assertIsNotNone(new_author.get('codeName'))
        # Test as an admin you can grant the user roles
        acas_user_author_role = {
            'userName': new_author['userName'],
            'roleType': 'System',
            'roleKind': 'ACAS',
            'roleName': 'ROLE_ACAS-USERS',
        }
        cmpdreg_user_author_role = {
            'userName': new_author['userName'],
            'roleType': 'System',
            'roleKind': 'CmpdReg',
            'roleName': 'ROLE_CMPDREG-USERS',
        }
        roles_to_add = [acas_user_author_role, cmpdreg_user_author_role]
        self.client.update_author_roles(roles_to_add)
        # Fetch the updated author so we can check its attributes
        updated_author = self.client.get_author_by_username(new_author['userName'])
        # Confirm the roles were granted
        self.assertEqual(len(updated_author['authorRoles']), 2)
        for author_role in updated_author['authorRoles']:
            role = author_role['roleEntry']
            self.assertEqual(role['lsType'], 'System')
            self.assertIn(role['lsKind'], ['ACAS', 'CmpdReg'])
            self.assertIn(role['roleName'], ['ROLE_ACAS-USERS', 'ROLE_CMPDREG-USERS'])
        # Revoke the CmpdReg role
        roles_to_remove = [cmpdreg_user_author_role]
        self.client.update_author_roles(author_roles_to_delete=roles_to_remove)
        # Confirm a role was revoked
        updated_author = self.client.get_author_by_username(new_author['userName'])
        self.assertEqual(len(updated_author['authorRoles']), 1)
        role = updated_author['authorRoles'][0]['roleEntry']
        self.assertEqual(role['roleName'], 'ROLE_ACAS-USERS')
        # Try adding a role by updating the author
        # Unfortunately we need to hardcode the id of the role, or fetch it from the server
        nested_cmpdreg_role = {
            'roleEntry': {
                'id': 3,
                'lsType': 'System',
                'lsKind': 'CmpdReg',
                'roleName': 'ROLE_CMPDREG-USERS',
            }
        }
        updated_author['authorRoles'].append(nested_cmpdreg_role)
        self.client.update_author(updated_author)
        # Confirm the role was added
        updated_author = self.client.get_author_by_username(new_author['userName'])
        self.assertEqual(len(updated_author['authorRoles']), 2)
        # Confirm the legacy 'updateProjectRoles' endpoint is still functional
        self.client.update_project_roles([cmpdreg_user_author_role])
        updated_author = self.client.get_author_by_username(new_author['userName'])
        self.assertEqual(len(updated_author['authorRoles']), 2)
        self.client.update_project_roles(author_roles_to_delete=[cmpdreg_user_author_role])
        updated_author = self.client.get_author_by_username(new_author['userName'])
        self.assertEqual(len(updated_author['authorRoles']), 1)
        # Try login with the new user, which will fail due to account not being activated
        # Database authentication requires email address to be confirmed
        user_creds = {
            'username': author['userName'],
            'password': author['password'],
            'url': self.client.url
        }
        with self.assertRaises(RuntimeError):
            acasclient.client(user_creds)
        # Now use the "backdoor" route to create a non-admin account which will be activated
        test_username = 'test_user'
        user_client = self.create_and_connect_backdoor_user(test_username)
        # Confirm the user can access projects
        projects = user_client.projects()
        self.assertGreater(len(projects), 0)
        # Check that a non-admin cannot create more authors
        with self.assertRaises(requests.HTTPError) as context:
            author = {
                "firstName": "Jane",
                "lastName": "Doe",
                "userName": "jadoe",
                "emailAddress": "jane@example.com",
                "password": str(uuid.uuid4()),
            }
            user_client.create_author(author)
        self.assertIn('500 Server Error', str(context.exception))
        # Check a non-admin can access the list of authors
        authors = user_client.get_authors()
        self.assertGreater(len(authors), 0)
        # Confirm a non-admin cannot escalate user roles
        with self.assertRaises(requests.HTTPError) as context:
            cmpdreg_user_author_role['userName'] = test_username
            user_client.update_author_roles([cmpdreg_user_author_role])
        self.assertIn('500 Server Error', str(context.exception))
        # Confirm a non-admin cannot revoke user roles
        with self.assertRaises(requests.HTTPError) as context:
            acas_user_author_role['userName'] = test_username
            user_client.update_author_roles(author_roles_to_delete=[acas_user_author_role])
        self.assertIn('500 Server Error', str(context.exception))

    @requires_absent_basic_cmpd_reg_load
    def test_045_register_sdf_case_insensitive(self):
        """Test register sdf with case insensitive lookups"""
        # test values
        CHEMIST = 'bob'
        CHEMIST_NAME = 'Bob Roberts'
        STEREO_CATEGORY = 'Unknown'
        SALT_ABBREV = 'HCl'
        SALT_MOL = "\n  Ketcher 05182214202D 1   1.00000     0.00000     0\n\n  1  0  0     1  0            999 V2000\n    6.9500   -4.3250    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0\nM  END\n"
        PHYSICAL_STATE = 'solid'
        VENDOR = 'ThermoFisher'
        # Do a "get or create" to ensure the expected values are there
        self._get_or_create_codetable(self.client.get_cmpdreg_scientists, self.client.create_cmpdreg_scientist, CHEMIST, CHEMIST_NAME)
        # Stereo Category
        self._get_or_create_codetable(self.client.get_stereo_categories, self.client.create_stereo_category, STEREO_CATEGORY, STEREO_CATEGORY)
        # Physical States
        self._get_or_create_codetable(self.client.get_physical_states, self.client.create_physical_state, PHYSICAL_STATE, PHYSICAL_STATE)
        # Vendors
        self._get_or_create_codetable(self.client.get_cmpdreg_vendors, self.client.create_cmpdreg_vendor, VENDOR, VENDOR)
        # Get Salt Abbrevs. Treat salts separately since they are not a standard codetable
        salts = self.client.get_salts()
        # Create Salt Abbrev
        if SALT_ABBREV.lower() not in [s['abbrev'].lower() for s in salts]:
            salt = self.client.create_salt(abbrev=SALT_ABBREV, name=SALT_ABBREV, mol_structure=SALT_MOL)
            self.assertIsNotNone(salt.get('id'))
        
        # Setup SDF registration with a file containing wrong-case lookups for above values
        upload_file_file = Path(__file__).resolve().parent.\
            joinpath('test_acasclient', 'test_045_register_sdf_case_insensitive.sdf')
        mappings = [
            {
                "dbProperty": "Lot Vendor",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Vendor"
            },
            {
                "dbProperty": "Lot Chemist",
                "defaultVal": "Bob",
                "required": True,
                "sdfProperty": None
            },
            {
                "dbProperty": "Project",
                "defaultVal": self.global_project_code,
                "required": True,
                "sdfProperty": None
            },
            {
                "dbProperty": "Parent Stereo Category",
                "defaultVal": "unknown",
                "required": True,
                "sdfProperty": None
            },
            {
                "dbProperty": "Lot Physical State",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Physical State"
            },
            {
                "dbProperty": "Lot Salt Abbrev",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Salt Name"
            },
            {
                "dbProperty": "Lot Salt Equivalents",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Salt Equivalents"
            }
        ]
        
        # Validate and confirm no errors
        response = self.client.register_sdf(upload_file_file, "bob",
                                            mappings, dry_run=True)
        self.assertIn('results', response)
        messages = response['results']
        errors = [m for m in messages if m['level'] == 'error']
        warnings = [m for m in messages if m['level'] == 'warning']
        if len(errors) > 0:
            print(errors)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 6)
        # Register and confirm no errors
        response = self.client.register_sdf(upload_file_file, "bob",
                                            mappings)
        self.assertIn('results', response)
        messages = response['results']
        errors = [m for m in messages if m['level'] == 'error']
        warnings = [m for m in messages if m['level'] == 'warning']
        if len(errors) > 0:
            print(errors)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 6)
        summary = response['summary']
        self.assertIn('New compounds: 2', summary)

        # Get the lots and confirm they have user 'bob' not 'Bob'
        registered_sdf = [f for f in response['report_files'] if '_registered.sdf' in f['name']][0]
        registered_records = registered_sdf['parsed_content']
        lot_corp_names = [rec['properties']['Registered Lot Corp Name'] for rec in registered_records]
        for corp_name in lot_corp_names:
            meta_lot = self.client.get_meta_lot(corp_name)
            lot = meta_lot['lot']
            self.assertEqual(lot['chemist'], 'bob')
        
    
    @requires_node_api
    def test_046_cmpdreg_admin_crud(self):
        """Test create, read, update, delete methods for CmdpReg controlled vocabulary items
            Also test that these are properly restricted to CmpdReg admins (except for read)"""
        # Test values
        CHEMIST = 'testChemist'
        CHEMIST_NAME = 'Test Chemist'
        STEREO_CATEGORY = 'TestCategory'
        PHYSICAL_STATE = 'plasma'
        VENDOR = 'Test Vendor'
        # Setup non-privileged test user
        user_client =  self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=False)

        # Create as unprivileged should fail
        UNAUTH_ERROR = '401 Client Error: Unauthorized'
        # TODO fix scientist
        # with self.assertRaises(requests.HTTPError) as context:
        #     user_client.create_cmpdreg_scientist(CHEMIST, CHEMIST_NAME)
        # self.assertIn(UNAUTH_ERROR, str(context.exception))
        with self.assertRaises(requests.HTTPError) as context:
            user_client.create_stereo_category(STEREO_CATEGORY, STEREO_CATEGORY)
        self.assertIn(UNAUTH_ERROR, str(context.exception))
        with self.assertRaises(requests.HTTPError) as context:
            user_client.create_physical_state(PHYSICAL_STATE, PHYSICAL_STATE)
        self.assertIn(UNAUTH_ERROR, str(context.exception))
        with self.assertRaises(requests.HTTPError) as context:
           user_client.create_cmpdreg_vendor(VENDOR, VENDOR)
        self.assertIn(UNAUTH_ERROR, str(context.exception))

        # Create as privileged should succeed
        chemist = self.client.create_cmpdreg_scientist(CHEMIST, CHEMIST_NAME)
        self.assertIsNotNone(chemist.get('id'))
        stereo_category = self.client.create_stereo_category(STEREO_CATEGORY, STEREO_CATEGORY)
        self.assertIsNotNone(stereo_category.get('id'))
        physical_state = self.client.create_physical_state(PHYSICAL_STATE, PHYSICAL_STATE)
        self.assertIsNotNone(physical_state.get('id'))
        vendor = self.client.create_cmpdreg_vendor(VENDOR, VENDOR)
        self.assertIsNotNone(vendor.get('id'))

        # Read as unprivileged should succeed
        chemists = user_client.get_cmpdreg_scientists()
        self.assertNotEqual(len(chemists), 0)
        stereo_categories = user_client.get_stereo_categories()
        self.assertNotEqual(len(stereo_categories), 0)
        physical_states = user_client.get_physical_states()
        self.assertNotEqual(len(physical_states), 0)
        vendors = user_client.get_cmpdreg_vendors()
        self.assertNotEqual(len(vendors), 0)

        # Read as privileged should also work
        chemists = self.client.get_cmpdreg_scientists()
        self.assertIn(CHEMIST, [c['code'] for c in chemists])
        stereo_categories = self.client.get_stereo_categories()
        self.assertIn(STEREO_CATEGORY, [c['code'] for c in stereo_categories])
        physical_states = self.client.get_physical_states()
        self.assertIn(PHYSICAL_STATE, [s['code'] for s in physical_states])
        vendors = self.client.get_cmpdreg_vendors()
        self.assertIn(VENDOR, [v['code'] for v in vendors])

        # Setup updated values
        updated_chemist = chemist.copy()
        updated_chemist['name'] = 'Updated Chemist'
        updated_stereo_category = stereo_category.copy()
        updated_stereo_category['name'] = 'Updated Category'
        updated_physical_state = physical_state.copy()
        updated_physical_state['name'] = 'Updated State'
        updated_vendor = vendor.copy()
        updated_vendor['name'] = 'Updated Vendor'
        
        # Update as unprivileged should fail
        # with self.assertRaises(requests.HTTPError) as context:
        #     user_client.update_cmpdreg_scientist(updated_chemist)
        # self.assertIn(UNAUTH_ERROR, str(context.exception))
        with self.assertRaises(requests.HTTPError) as context:
            user_client.update_stereo_category(updated_stereo_category)
        self.assertIn(UNAUTH_ERROR, str(context.exception))
        with self.assertRaises(requests.HTTPError) as context:
            user_client.update_physical_state(updated_physical_state)
        self.assertIn(UNAUTH_ERROR, str(context.exception))
        with self.assertRaises(requests.HTTPError) as context:
            user_client.update_cmpdreg_vendor(updated_vendor)
        self.assertIn(UNAUTH_ERROR, str(context.exception))

        # update as privileged should succeed
        self.client.update_cmpdreg_scientist(updated_chemist)
        self.client.update_stereo_category(updated_stereo_category)
        self.client.update_physical_state(updated_physical_state)
        self.client.update_cmpdreg_vendor(updated_vendor)
        # Read to confirm values were updated
        chemists = self.client.get_cmpdreg_scientists()
        chemist = [c for c in chemists if c['code'] == CHEMIST][0]
        stereo_categories = self.client.get_stereo_categories()
        stereo_category = [c for c in stereo_categories if c['code'] == STEREO_CATEGORY][0]
        physical_states = self.client.get_physical_states()
        physical_state = [s for s in physical_states if s['code'] == PHYSICAL_STATE][0]
        vendors = self.client.get_cmpdreg_vendors()
        vendor = [v for v in vendors if v['code'] == VENDOR][0]
        self.assertEqual(chemist['name'], updated_chemist['name'])
        self.assertEqual(stereo_category['name'], updated_stereo_category['name'])
        self.assertEqual(physical_state['name'], updated_physical_state['name'])
        self.assertEqual(vendor['name'], updated_vendor['name'])

        # Test creating duplicates with alternate case, confirm they're rejected
        CHEMIST = 'Testchemist'
        STEREO_CATEGORY = 'testcategory'
        PHYSICAL_STATE = 'plaSma'
        VENDOR = 'tesT Vendor'
        self._create_dupe_codetable(self.client.create_cmpdreg_scientist, CHEMIST, CHEMIST_NAME)
        self._create_dupe_codetable(self.client.create_stereo_category, STEREO_CATEGORY, STEREO_CATEGORY)
        self._create_dupe_codetable(self.client.create_physical_state, PHYSICAL_STATE, PHYSICAL_STATE)
        self._create_dupe_codetable(self.client.create_cmpdreg_vendor, VENDOR, VENDOR)

        # Delete as unprivileged should fail
        # with self.assertRaises(requests.HTTPError) as context:
        #    user_client.delete_cmpdreg_scientist(chemist['id'])
        # self.assertIn(UNAUTH_ERROR, str(context.exception))
        with self.assertRaises(requests.HTTPError) as context:
            user_client.delete_stereo_category(stereo_category['id'])
        self.assertIn(UNAUTH_ERROR, str(context.exception))
        with self.assertRaises(requests.HTTPError) as context:
            user_client.delete_physical_state(physical_state['id'])
        self.assertIn(UNAUTH_ERROR, str(context.exception))
        with self.assertRaises(requests.HTTPError) as context:
            user_client.delete_cmpdreg_vendor(vendor['id'])
        self.assertIn(UNAUTH_ERROR, str(context.exception))

        # Delete as privileged should succeed
        self.client.delete_cmpdreg_scientist(chemist['id'])
        self.client.delete_stereo_category(stereo_category['id'])
        self.client.delete_physical_state(physical_state['id'])
        self.client.delete_cmpdreg_vendor(vendor['id'])
  
    def test_047_load_sdf_with_salts(self):
        """
        Tests to Make Sure Salt Can Only Be Derived from Structure or SDF Properties; NOT BOTH! 
        """
        test_047_load_sdf_with_salts_file = Path(__file__).resolve().parent.\
            joinpath('test_acasclient', 'test_047_register_sdf_with_salts.sdf')
        mappings = [
            {
                "dbProperty": "Parent Corp Name",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Corporate ID"
            },
            {
                "dbProperty": "Lot Chemist",
                "defaultVal": "bob",
                "required": True,
                "sdfProperty": "Lot Scientist"
            },
            {
                "dbProperty": "Project",
                "defaultVal": "PROJ-00000001",
                "required": True,
                "sdfProperty": "Project Code Name"
            },
            {
                "dbProperty": "Parent Stereo Category",
                "defaultVal": "unknown",
                "required": True,
                "sdfProperty": None
            },
            {
                "dbProperty": "Lot Salt Abbrev",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Salt Name"
            },
            {
                "dbProperty": "Lot Salt Equivalents",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Salt Equivalents"
            }
        ]
        # Ensuring HCl is registered as a salt since this test assumes that the salt parent structure
        # is already registered in CReg
        SALT_ABBREV = 'HCl'
        SALT_MOL = "\n  Ketcher 05182214202D 1   1.00000     0.00000     0\n\n  1  0  0     1  0            999 V2000\n    6.9500   -4.3250    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0\nM  END\n"
        # Get Salt Abbrevs. Treat salts separately since they are not a standard codetable
        salts = self.client.get_salts()
        # Create Salt Abbrev
        if SALT_ABBREV.lower() not in [s['abbrev'].lower() for s in salts]:
            salt = self.client.create_salt(abbrev=SALT_ABBREV, name=SALT_ABBREV, mol_structure=SALT_MOL)
            self.assertIsNotNone(salt.get('id'))

        response = self.client.register_sdf(test_047_load_sdf_with_salts_file, "bob",
                                            mappings)
        self.assertIn('report_files', response)
        self.assertIn('summary', response)
        self.assertIn('Number of entries processed: 4', response['summary'])
        self.assertIn('Number of entries with error: 1', response['summary'])
        self.assertIn('Number of warnings: 0', response['summary'])
        self.assertIn('New compounds: 1', response['summary'])
        self.assertIn('New lots of existing compounds: 2', response['summary'])
        self.assertIn('Salts found in both structure and SDF Property', response['summary'])
        return response

    def test_048_warn_existing_compound_new_id(self):
        """
        Test for Warning When Uploading A "New" Compound That Has Existing Parent and Gets New ID
        """
        test_048_warn_existing_compound_new_id_file_one = Path(__file__).resolve().parent.\
            joinpath('test_acasclient', 'test_048_warn_existing_compound_new_id.sdf')
        test_048_warn_existing_compound_new_id_file_two = Path(__file__).resolve().parent.\
            joinpath('test_acasclient', 'test_048_warn_existing_compound_new_id_two.sdf')
        mappings = [
            {
                "dbProperty": "Parent Corp Name",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Corporate ID"
            },
            {
                "dbProperty": "Lot Chemist",
                "defaultVal": "bob",
                "required": True,
                "sdfProperty": "Lot Scientist"
            },
            {
                "dbProperty": "Project",
                "defaultVal": "PROJ-00000001",
                "required": True,
                "sdfProperty": "Project Code Name"
            },
            {
                "dbProperty": "Parent Stereo Category",
                "defaultVal": "mixture",
                "required": True,
                "sdfProperty": None
            },
        ]
        response = self.client.register_sdf(test_048_warn_existing_compound_new_id_file_one, "bob",
                                            mappings)
        self.assertIn('report_files', response)
        self.assertIn('summary', response)
        self.assertIn('Number of entries processed', response['summary'])
        # Want to Assert Compound Registered Successfully 
        self.assertIn('Number of entries with error: 0', response['summary'])
        self.assertIn('Number of warnings: 0', response['summary'])
        self.assertIn('New compounds: 1', response['summary'])
        # Need to Do Second Round of File Since First Needs to Registered Already
        mappings = [
            {
                "dbProperty": "Parent Corp Name",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Corporate ID"
            },
            {
                "dbProperty": "Lot Chemist",
                "defaultVal": "bob",
                "required": True,
                "sdfProperty": "Lot Scientist"
            },
            {
                "dbProperty": "Project",
                "defaultVal": "PROJ-00000001",
                "required": True,
                "sdfProperty": "Project Code Name"
            },
            {
                "dbProperty": "Parent Stereo Category",
                "defaultVal": "unknown",
                "required": True,
                "sdfProperty": None
            },
        ]
        response = self.client.register_sdf(test_048_warn_existing_compound_new_id_file_two, "bob",
                                            mappings)
        self.assertIn('report_files', response)
        self.assertIn('summary', response)
        self.assertIn('Number of entries processed', response['summary'])
        self.assertIn('Number of entries with error: 0', response['summary'])
        # There are two warnings expected here: only one is related to the feature we are testing here
        self.assertIn('Number of warnings: 2', response['summary'])
        self.assertIn('New compounds: 1', response['summary'])
        self.assertIn('New parent will be assigned due to different stereo category', response['summary'])
        return response

    @requires_absent_basic_cmpd_reg_load
    def test_049_register_large_sdf_with_error(self):
        # Large request to test performance and error handling
        file = Path(__file__).resolve().parent\
            .joinpath('test_acasclient', 'nci1000.sdf')
        try:
            # SDF load of 1000 structures should take less than 60 seconds
            # to complete. On my machine it takes 30 seconds.
            # This is a performance check to make sure the
            # bulk load hasn't slowed significantly.
            with Timeout(seconds=90):
                response = self.basic_cmpd_reg_load(file = file)
        except TimeoutError:
            self.fail("Timeout error")

        self.assertIn('report_files', response)
        self.assertIn('Number of entries processed: 1000', response['summary'])
        self.assertIn('Number of entries with error: 1', response['summary'])

    def test_50_delete_ls_thing(self):
        code = str(uuid.uuid4())
        ls_thing = create_project_thing(code)
        saved_ls_thing = self.client.save_ls_thing(ls_thing)
        self.assertIn('codeName', saved_ls_thing)
        self.assertEqual(code, saved_ls_thing["codeName"])
        ls_thing = self.client.get_ls_thing("project",
                                            "project",
                                            code, None)
        self.assertIn(False, [ls_thing['deleted']])
        ls_thing = self.client.delete_ls_thing("project",
                                            "project",
                                            code, None) 
        ls_thing = self.client.get_ls_thing("project",
                                            "project",
                                            code, None)
        self.assertIn(True, [ls_thing['deleted']])


def get_basic_experiment_load_file_with_project(project_code, tempdir, corp_name = None, file_name = None):
    if file_name is None:
        file_name = 'uniform-commas-with-quoted-text.csv'
    data_file_to_upload = Path(__file__).resolve()\
                        .parent.joinpath('test_acasclient', file_name)
    # Read the data file and replace the project code with the one we want
    with open(data_file_to_upload, 'r') as f:
        data_file_contents = f.read()

    # Replace the project code
    data_file_contents = data_file_contents.replace('Global', project_code)

    # If corp name is specified, replace the corp name
    if corp_name is not None:
        data_file_contents = data_file_contents.replace('CMPD-0000001-001', corp_name)

    # Write the data file to the temp dir
    file_name = f'basic-experiment-with-project-{project_code}.csv'
    data_file_to_upload = Path(tempdir).joinpath(file_name)
    with open(data_file_to_upload, 'w') as f:
        f.write(data_file_contents)

    return data_file_to_upload

def csv_to_txt(data_file_to_upload, dir):
    # Get the file name but change it to .txt
    file_name = data_file_to_upload.name
    file_name = file_name.replace(".csv", ".txt")
    file_path = Path(dir, file_name)
    # Change the delim to the new delim
    with open(data_file_to_upload, 'r') as f:
        with open(file_path, 'w') as f2:
            for line in f:
                f2.write(line.replace(',', "\t"))
    return file_path

class TestCmpdReg(BaseAcasClientTest):

    def create_restricted_lot(self, project_code):
        # Bulk load a compound to the restricted project
        response = self.basic_cmpd_reg_load(project_code)
        # Assert that the are no errors in the response results level
        all_lots = self.client.get_all_lots()

        # Sort lots by id and get the latest corp id
        # This is because we dont' get the corp id in the response from the bulkload
        all_lots = sorted(all_lots, key=lambda lot: lot['id'])
        global_project_parent_corp_name = all_lots[0]['parentCorpName']

        # Find the lot that was bulk loaded with the same corp name as the global project
        restricted_project_lot = [lot for lot in all_lots if lot['parentCorpName'] == global_project_parent_corp_name][-1]
        restricted_lot_corp_name = restricted_project_lot["lotCorpName"]

        return restricted_lot_corp_name

    @requires_node_api
    @requires_basic_cmpd_reg_load
    def test_001_get_meta_lot(self):
        """Test get meta lot."""
        # The default user is 'bob' and bob has cmpdreg admin role
        # The basic cmpdreg load has a lot registered that is unrestricted (Global project)
        meta_lot = self.client.\
            get_meta_lot('CMPD-0000001-001')
        self.assertIsNotNone(meta_lot)
        self.assertEqual(meta_lot['lot']['corpName'], 'CMPD-0000001-001')

        # Create a restricted project 
        project = self.create_basic_project_with_roles()

        # Bulk load a compound to the restricted project
        self.basic_cmpd_reg_load(project.code_name)
        all_lots = self.client.get_all_lots()

        # Sort lots by id and get the latest corp id
        # This is because we dont' get the corp id in the response from the bulkload
        all_lots = sorted(all_lots, key=lambda lot: lot['id'])
        restricted_project_lot_corp_name = all_lots[-1]['lotCorpName']
        global_project_lot_corp_name = all_lots[0]['lotCorpName']

        # Verify our cmpdreg admin user can fetch the restricted lot
        meta_lot = self.client.\
            get_meta_lot(restricted_project_lot_corp_name)
        self.assertIsNotNone(meta_lot)

        # Now create a user that is not a cmpdreg admin and does not have access to the restricted project
        user_client = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=False)

        # User SHOULD be able to fetch the global lot
        try:
            meta_lot = user_client.\
                get_meta_lot(global_project_lot_corp_name)
            self.assertIn("lot", meta_lot)
        except requests.HTTPError:
            self.fail("User should be able to fetch the global lot")
        
        # User should NOT be able fetch the restricted lot
        with self.assertRaises(requests.HTTPError) as context:
            meta_lot = user_client.\
                get_meta_lot(restricted_project_lot_corp_name)
        self.assertIn('403 Client Error: Forbidden for url', str(context.exception))
        
        # Now create a user which has access to the project
        user_client = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=False, project_names = [project.names[PROJECT_NAME]])

        # User SHOULD be able to fetch the restricted lot
        try:
            meta_lot = user_client.\
                get_meta_lot(restricted_project_lot_corp_name)
            self.assertIn("lot", meta_lot)
        except requests.HTTPError:
            self.fail("User should be able to fetch the restricted lot")

    @requires_node_api
    @requires_basic_experiment_load
    def test_002_get_lot_dependencies(self, experiment):

        # CMPDREG-ADMIN, ACAS-ADMIN tests
        # Get meta lot dependencies
        meta_lot_dependencies = self.client.get_lot_dependencies("CMPD-0000001-001")

        # Check basic structure
        self.assertIn('batchCodes', meta_lot_dependencies)
        self.assertIn('linkedDataExists', meta_lot_dependencies)
        self.assertIn('linkedExperiments', meta_lot_dependencies)
        self.assertIn('linkedLots', meta_lot_dependencies)

        # Verify we can turn off the linked lots checking
        meta_lot_dependencies = self.client.get_lot_dependencies("CMPD-0000001-001", include_linked_lots=False)
        self.assertNotIn('linkedLots', meta_lot_dependencies)
        
        # Verify that the experiment code name is in the linkedExperiments list
        self.assertIn(experiment['codeName'], [e['code'] for e in meta_lot_dependencies['linkedExperiments']])

        # Delete the experiment and then check the meta lot dependencies again, this time the experiment should be removed from the linkedExperiments list
        self.client.delete_experiment(experiment['id'])
        meta_lot_dependencies = self.client.get_lot_dependencies("CMPD-0000001-001")
        self.assertNotIn(experiment['codeName'], [e['code'] for e in meta_lot_dependencies['linkedExperiments']])

        # Setup for further tests
        # Create a restricted project 
        project = self.create_basic_project_with_roles()

        # Bulk load a compound to the restricted project
        self.basic_cmpd_reg_load(project.code_name)
        all_lots = self.client.get_all_lots()

        # Load an experiment to the newly created restricted project using the global project lots
        file_to_upload = get_basic_experiment_load_file_with_project(project.names[PROJECT_NAME], self.tempdir)
        response = self.client.\
            experiment_loader(file_to_upload, "bob", False)
        restricted_experiment_code_name = response['results']['experimentCode']

        # Sort lots by id and get the latest corp id
        # This is because we dont' get the corp id in the response from the bulkload
        all_lots = sorted(all_lots, key=lambda lot: lot['id'])
        global_project_lot_corp_name = all_lots[0]['lotCorpName']
        global_project_parent_corp_name = all_lots[0]['parentCorpName']

        # Find the lot that was bulk loaded with the same corp name as the global project
        restricted_project_lot = [lot for lot in all_lots if lot['parentCorpName'] == global_project_parent_corp_name][-1]

        # Check that CMPDREG-ADMIN, ACAS-ADMIN can get all depdencies
        # Verify our cmpdreg admin can see the restricted lot in the dependencies as the new lot 
        global_lot_dependencies = self.client.get_lot_dependencies(global_project_lot_corp_name)
        
        # Verify that the restricted_project_lot_corp_name is in the list of linkedLots for our cmpdreg admin
        self.assertIn(restricted_project_lot['lotCorpName'], [l['code'] for l in global_lot_dependencies['linkedLots']])

        # Verify our cmpdreg admin, acas-admin can see the restricted experiment in the dependencies as the new experiment
        self.assertIn(restricted_experiment_code_name, [e['code'] for e in global_lot_dependencies['linkedExperiments']])

        # Get the acls for the restricted experiment from the global_lot_dependencies
        restricted_experiment_acls = [acl for acl in global_lot_dependencies['linkedExperiments'] if acl['code'] == restricted_experiment_code_name][0]['acls']
        
        # Our cmpdreg admin also has acas admin so should be able to read, write and delete the restricted experiment
        self.assertTrue(restricted_experiment_acls['read'])
        self.assertTrue(restricted_experiment_acls['write'])
        self.assertTrue(restricted_experiment_acls['delete'])

        # CMPDREG_ADMIN, no acas roles
        # Now create another cmpdreg admin but don't give them acas admin
        user_client = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=True)

        # User SHOULD be able to fetch the global lot depdencies
        try:
            global_lot_dependencies = user_client.get_lot_dependencies(global_project_lot_corp_name)
        except requests.HTTPError:
            self.fail("User should be able to check the meta lot dependencies for the global lot")

        # User SHOULD be able to fetch the restricted experiment info
        self.assertIn(restricted_experiment_code_name, [e['code'] for e in global_lot_dependencies['linkedExperiments']])

        # Get the acls for the restricted experiment from the global_lot_dependencies
        restricted_experiment_acls = [acl for acl in global_lot_dependencies['linkedExperiments'] if acl['code'] == restricted_experiment_code_name][0]['acls']
        
        # User SHOULD be able to read but not write or delete the restricted experiment
        self.assertTrue(restricted_experiment_acls['read'])
        self.assertFalse(restricted_experiment_acls['write'])
        self.assertFalse(restricted_experiment_acls['delete'])

        # CMPDREG-USER no acas roles or restricted project roles
        user_client = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=False)

        # The user should be able to fetch global lot dependencies
        try:
            global_lot_dependencies = user_client.get_lot_dependencies(global_project_lot_corp_name)
        except requests.HTTPError:
            self.fail("User should be able to check the meta lot dependencies for the global lot")

        # The user SHOULD NOT be able to see the restricted lot info
        self.assertNotIn(restricted_project_lot['lotCorpName'], [l['code'] for l in global_lot_dependencies['linkedLots']])

        # Verify that the restricted_experiment_code_name is not listed in the linkedExperiments for the user
        # But the the lot has linkedDataExists true and there is more than 0 experiments in the linkedExperiments
        self.assertNotIn(restricted_experiment_code_name, [e['code'] for e in global_lot_dependencies['linkedExperiments']])
        self.assertTrue(global_lot_dependencies['linkedDataExists'])
        self.assertGreater(len(global_lot_dependencies['linkedExperiments']), 0)
        
        # CMPDREG-USER no acas roles but has access to restricted project
        user_client = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=False, project_names = [project.names[PROJECT_NAME]])

        # User SHOULD be able to fetch the restricted lot depdencies
        try:
            restricted_lot_dependencies = user_client.\
                get_lot_dependencies(restricted_project_lot['lotCorpName'])
        except requests.HTTPError:
            self.fail("User should be able to fetch the restricted lot")

        # Verify that the global_lot is in the linkedLots for the user
        self.assertIn(global_project_lot_corp_name, [l['code'] for l in restricted_lot_dependencies['linkedLots']])

        # Get the global lot depdencies
        global_lot_dependencies = user_client.\
            get_lot_dependencies(global_project_lot_corp_name)

        # Verify that the restricted_experiment_code_name is NOT in the linkedExperiments for the user because they aren't an acas user
        # Bug that the lot does show it has linkedDataExists true and there is more than 0 experiments in the linkedExperiments
        self.assertNotIn(restricted_experiment_code_name, [e['code'] for e in global_lot_dependencies['linkedExperiments']])
        self.assertTrue(global_lot_dependencies['linkedDataExists'])
        self.assertGreater(len(global_lot_dependencies['linkedExperiments']), 0)
        
        # CMPDREG-USER and ACAS-USER with access to restricted project
        user_client = self.create_and_connect_backdoor_user(acas_user=True, acas_admin=False, creg_user=True, creg_admin=False, project_names = [project.names[PROJECT_NAME]])

        # User SHOULD be able to fetch the restricted lot depdencies
        try:
            restricted_lot_dependencies = user_client.\
                get_lot_dependencies(restricted_project_lot['lotCorpName'])
        except requests.HTTPError:
            self.fail("User should be able to fetch the restricted lot")
        
        global_lot_dependencies = user_client.get_lot_dependencies(global_project_lot_corp_name)

        # Verify that the restricted_experiment_code_name is in the linkedExperiments for the user
        self.assertIn(restricted_experiment_code_name, [e['code'] for e in global_lot_dependencies['linkedExperiments']])

        # Get the acls for the restricted experiment from the global_lot_dependencies
        restricted_experiment_acls = [acl for acl in global_lot_dependencies['linkedExperiments'] if acl['code'] == restricted_experiment_code_name][0]['acls']
        
        # Verify the expected acls are read: true, write: true, delete: true
        self.assertTrue(restricted_experiment_acls['read'])
        self.assertTrue(restricted_experiment_acls['write'])
        self.assertTrue(restricted_experiment_acls['delete'])

    @requires_node_api
    @requires_basic_cmpd_reg_load
    def test_003_save_meta_lot(self):
        """Test post meta lot."""

        # Create a restricted project 
        project = self.create_basic_project_with_roles()
    
        # Bulk load some compounds to we don't interfere with CMPD-0000001-001
        self.basic_cmpd_reg_load(project.code_name)
        all_lots = self.client.get_all_lots()

        # Sort lots by id and get the latest corp id
        # This is because we dont' get the corp id in the response from the bulkload
        all_lots = sorted(all_lots, key=lambda lot: lot['id'])
        restricted_project_lot_corp_name = all_lots[-1]['lotCorpName']
        
        # The default user is 'bob' and bob has cmpdreg admin role
        # The basic cmpdreg load has a lot registered that is unrestricted (Global project)
        meta_lot = self.client.\
            get_meta_lot(restricted_project_lot_corp_name)
        self.assertIsNotNone(meta_lot)
        self.assertEqual(meta_lot['lot']['corpName'], restricted_project_lot_corp_name)

        # Verify our cmpdreg admin user can save the restricted lot
        meta_lot["lot"]["color"] = "red"
        response = self.client.\
            save_meta_lot(meta_lot)
        self.assertEqual(len(response["errors"]), 0)
        self.assertIn("metalot", response)
        self.assertIn("lot", response["metalot"])
        self.assertEqual(response["metalot"]["lot"]["color"], "red")

        # Verify our admin user can update the project
        meta_lot["lot"]["project"] = project.code_name
        response = self.client.\
            save_meta_lot(meta_lot)
        self.assertEqual(len(response["errors"]), 0)
        self.assertIn("metalot", response)
        self.assertIn("lot", response["metalot"])
        self.assertEqual(response["metalot"]["lot"]["project"], project.code_name)

        # Now create a user that is not a cmpdreg admin and does not have access to the restricted project
        user_client = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=False)
              
        # User should NOT be able save/update the restricted lot
        with self.assertRaises(requests.HTTPError) as context:
            response = user_client.\
                save_meta_lot(meta_lot)
        self.assertIn('403 Client Error: Forbidden for url', str(context.exception))
        
        # Now create a user which has access to the project
        user_client = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=False, project_names = [project.names[PROJECT_NAME]])

        # User should still not be able to save the restricted lot because they aren't the owner of the lot
        with self.assertRaises(requests.HTTPError) as context:
            response = user_client.\
                save_meta_lot(meta_lot)
        self.assertIn('403 Client Error: Forbidden for url', str(context.exception))

        # Update the lot and make the user the chemist of the lot so they can fetch the restricted lot
        meta_lot["lot"]["chemist"] = user_client.username
        response = self.client.\
            save_meta_lot(meta_lot)

        meta_lot["lot"]["color"] = "blue"
        try:
            response = user_client.\
                save_meta_lot(meta_lot)
        except requests.HTTPError:
            self.fail("User should be able to save the restricted lot")
        self.assertIn("metalot", response)
        self.assertIn("lot", response["metalot"])
        self.assertEqual(response["metalot"]["lot"]["color"], "blue")

    @requires_node_api
    @requires_absent_basic_cmpd_reg_load
    @requires_basic_experiment_load
    def test_004_delete_lot(self, experiment):

        # Create a restricted project 
        project = self.create_basic_project_with_roles()

        # Create a bunch of users with various roles and project access
        cmpdreg_user = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=False)
        cmpdreg_user_with_restricted_project_acls = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=False, project_names = [project.names[PROJECT_NAME]])
        acas_user = self.create_and_connect_backdoor_user(acas_user=True, acas_admin=False, creg_user=False, creg_admin=False)
        acas_user_restricted_project_acls = self.create_and_connect_backdoor_user(acas_user=True, acas_admin=False, creg_user=False, creg_admin=False, project_names = [project.names[PROJECT_NAME]])

        def can_delete_lot(self, user_client, lot_corp_name, set_owner_first=True):
            if set_owner_first:
                meta_lot = self.client.get_meta_lot(lot_corp_name)
                meta_lot["lot"]["chemist"] = user_client.username
                self.client.save_meta_lot(meta_lot)
            try:
                response = user_client.delete_lot(lot_corp_name)
            except requests.HTTPError:
                return False
            self.assertIn("success", response)
            self.assertTrue(response['success'])
            return True

        # Global compound, with experiment in Global project
        ## Deny Rule: Not an acas user so can't delete because dependent experiment exists
        self.assertFalse(can_delete_lot(self, cmpdreg_user, "CMPD-0000001-001", set_owner_first=True))

        ## Allow Rule: An acas user with access to delete global experiment and global compound
        self.assertTrue(can_delete_lot(self, acas_user, "CMPD-0000001-001", set_owner_first=True))
        meta_lot = self.client.get_meta_lot("CMPD-0000001-001")
        self.assertIsNone(meta_lot)

        # Create a restricted lot by project
        restricted_lot_corp_name = self.create_restricted_lot(project.code_name)

        # Deny Rule: No access to lot project
        self.assertFalse(can_delete_lot(self, cmpdreg_user, restricted_lot_corp_name, set_owner_first=True))

        # Deny Rule: Not the owner of the lot (must be chemist or recorded by user based on default acas configs for lot access)
        self.assertFalse(can_delete_lot(self, cmpdreg_user_with_restricted_project_acls, restricted_lot_corp_name, set_owner_first=False))

        # Deny Rule: No access to lot project
        self.assertFalse(can_delete_lot(self, acas_user, restricted_lot_corp_name, set_owner_first=False))

        # Deny Rule: Not the owner of the lot (must be chemist or recorded by user based on default acas configs for lot access)
        self.assertFalse(can_delete_lot(self, acas_user_restricted_project_acls, restricted_lot_corp_name, set_owner_first=False))

        # Allow Rule: Owns lot by chemist rule, has access to restricted lot project
        self.assertTrue(can_delete_lot(self, acas_user_restricted_project_acls, restricted_lot_corp_name, set_owner_first=True))

        # Allow Rule: Owns lot by chemist rule, has access to restricted lot project
        restricted_lot_corp_name = self.create_restricted_lot(project.code_name)
        self.assertTrue(can_delete_lot(self, cmpdreg_user_with_restricted_project_acls, restricted_lot_corp_name, set_owner_first=True))

        # Load an experiment to the newly created restricted project using the global project lots
        restricted_lot_corp_name = self.create_restricted_lot(project.code_name)
        file_to_upload = get_basic_experiment_load_file_with_project(project.names[PROJECT_NAME], self.tempdir, restricted_lot_corp_name, file_name = '4 parameter D-R.csv')
        response = self.client.\
            experiment_loader(file_to_upload, "bob", False)
        restricted_experiment_code_name = response['results']['experimentCode']

        # Update the lot and make the cmpdreg_user_with_restricted_project_acls the chemist of the lot
        meta_lot = self.client.get_meta_lot(restricted_lot_corp_name)
        meta_lot["lot"]["chemist"] = cmpdreg_user_with_restricted_project_acls.username

        # Deny Rule: Not an acas user so can't delete because dependent experiment exists
        self.assertFalse(can_delete_lot(self, cmpdreg_user_with_restricted_project_acls, restricted_lot_corp_name, set_owner_first=True))

        # Delete the experiment (mimic asking acas_user_restricted_project_acls to delete the experiment)
        response = acas_user_restricted_project_acls.delete_experiment(restricted_experiment_code_name)

        # Allow Rule: Owns lot by chemist rule, no longer has dependent experiment
        self.assertTrue(can_delete_lot(self, cmpdreg_user_with_restricted_project_acls, restricted_lot_corp_name, set_owner_first=True))

    @requires_node_api
    @requires_absent_basic_cmpd_reg_load
    def test_005_swap_parent_structures(self):
        """
        Check `swap_parent_structures` can swap structures in case of parents with no duplicates or
        parents who are duplicates of each other.
        """

        file = Path(__file__).resolve().parent.joinpath(
            'test_acasclient', 'test_005_swap_parent_structures.sdf')
        self.basic_cmpd_reg_load(file=file)

        # CMPD-0000001 (structure: A, stereo category: Single stereoisomer)
        # CMPD-0000002 (structure: A'(stereoisomer of 1), stereo category: Single stereoisomer)
        # CMPD-0000003 (structure: A'(stereoisomer of 1), stereo category: Single stereoisomer - arbitrary assign)
        # CMPD-0000004 (structure: B, stereo category: Single stereoisomer)
        # CMPD-0000005 (structure: C, stereo category: Unknown, stereo comment: foo)
        # CMPD-0000006 (structure: C'(stereoisomer of 5), stereo category: Unknown, stereo comment: foo)
        # CMPD-0000007 (structure: C'(stereoisomer of 5), stereo category: Unknown, stereo comment: bar)

        try:
            # Swapping 1 and 3 will introduce duplicacy between 1 and 2.
            with self.assertRaises(requests.exceptions.HTTPError):
                self.client.swap_parent_structures(
                    corp_name1='CMPD-0000001', corp_name2='CMPD-0000003')

            # Swapping 1 and 2 will not introduce any duplicates.
            assert self.client.swap_parent_structures(
                corp_name1='CMPD-0000001', corp_name2='CMPD-0000002')
            # Restore the original structures
            assert self.client.swap_parent_structures(
                corp_name1='CMPD-0000001', corp_name2='CMPD-0000002')

            # Swapping 1 and 4 will not introduce any duplicates.
            assert self.client.swap_parent_structures(
                corp_name1='CMPD-0000001', corp_name2='CMPD-0000004')
            # Restore the original structures
            assert self.client.swap_parent_structures(
                corp_name1='CMPD-0000001', corp_name2='CMPD-0000004')

            # Swapping 5 and 6 will not introduce any duplicates.
            assert self.client.swap_parent_structures(
                corp_name1='CMPD-0000005', corp_name2='CMPD-0000006')
        finally:
            # Prevent interaction with other tests.
            self.delete_all_cmpd_reg_bulk_load_files()


        

    @requires_node_api
    @requires_absent_basic_cmpd_reg_load
    @requires_basic_experiment_load
    def test_006_reparent_lot(self, experiment):
        # Function with test to verify reparent lot functionality
        def can_reparent_lot(self, user_client, lot_corp_name, adopting_parent_corp_name, dry_run):
            try:
                original_meta_lot = self.client.get_meta_lot(lot_corp_name)
                dry_run_response = user_client.reparent_lot(lot_corp_name, adopting_parent_corp_name, True)
                self.assertIn("newLot", dry_run_response)
                self.assertIn("modifiedBy", dry_run_response)
                self.assertIn("originalLotCorpName", dry_run_response)
                self.assertIn("originalParentCorpName", dry_run_response)
                self.assertIn("originalParentDeleted", dry_run_response)
                self.assertIn("originalLotNumber", dry_run_response)
                self.assertEqual(dry_run_response['newLot']["parent"]["corpName"], adopting_parent_corp_name)
                
                # Make sure we can still find the original lot corp name if we haven't done a wet run yet
                meta_lot = self.client.get_meta_lot(lot_corp_name)
                self.assertEqual(meta_lot["lot"]["parent"]["corpName"], original_meta_lot["lot"]["parent"]["corpName"])
                self.assertEqual(meta_lot["lot"]["saltForm"]["corpName"], original_meta_lot["lot"]["parent"]["corpName"])

                if not dry_run:
                    wet_run_response = user_client.reparent_lot(lot_corp_name, adopting_parent_corp_name, False)
                    self.assertIn("newLot", wet_run_response)
                    self.assertIn("modifiedBy", wet_run_response)
                    self.assertIn("originalLotCorpName", wet_run_response)
                    self.assertIn("originalParentCorpName", wet_run_response)
                    self.assertIn("originalParentDeleted", wet_run_response)
                    self.assertIn("originalLotNumber", wet_run_response)

                    self.assertEqual(wet_run_response['newLot']["parent"]["corpName"], adopting_parent_corp_name)

                    # Make sure the predicted lot corp name is the same as the actual lot corp name we changed to
                    self.assertEqual(wet_run_response["newLot"]["corpName"], dry_run_response["newLot"]["corpName"])

                    # Make sure we canf ind the new lot and that the parent and salt form are same as new corp name
                    meta_lot = self.client.get_meta_lot(wet_run_response["newLot"]["corpName"])
                    self.assertEqual(meta_lot["lot"]["parent"]["corpName"], adopting_parent_corp_name)
                    self.assertEqual(meta_lot["lot"]["saltForm"]["corpName"], adopting_parent_corp_name)        

            except requests.HTTPError:
                return False
            
            return True

        # Create a restricted project 
        project = self.create_basic_project_with_roles()
        
        # Create a bunch of users with various roles and project access
        cmpdreg_user = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=False)
        cmpdreg_user_with_restricted_project_acls = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=False, project_names = [project.names[PROJECT_NAME]])
        acas_user = self.create_and_connect_backdoor_user(acas_user=True, acas_admin=False, creg_user=False, creg_admin=False)
        acas_user_restricted_project_acls = self.create_and_connect_backdoor_user(acas_user=True, acas_admin=False, creg_user=False, creg_admin=False, project_names = [project.names[PROJECT_NAME]])
        acas_admin = self.create_and_connect_backdoor_user(acas_user=True, acas_admin=True, creg_user=False, creg_admin=False)
        cmpdreg_admin = self.create_and_connect_backdoor_user(acas_user=False, acas_admin=False, creg_user=True, creg_admin=True)

        # Verify dry run works by doing a dry run reparent
        # Starting state is 2 lots (1 on CMPD-0000001 and 1 on CMPD-0000002)
        self.assertTrue(can_reparent_lot(self, self.client, "CMPD-0000001-001",  "CMPD-0000002", dry_run = True))
        # Current state is 2 lots (1 on CMPD-0000002 and 1 on CMPD-0000002)

        # Reparent a lot
        self.assertTrue(can_reparent_lot(self, self.client, "CMPD-0000001-001",  "CMPD-0000002", dry_run = False))
        
        # Verify that the assay data has moved to the new lot which should be CMPD-0000002-002 dependencies
        depdencies = self.client.get_lot_dependencies("CMPD-0000002-002")
        self.assertIn("linkedExperiments", depdencies)
        hasExperiment = False
        for depExperiment in depdencies["linkedExperiments"]:
            if depExperiment["code"] == experiment["codeName"]:
                hasExperiment = True
        self.assertTrue(hasExperiment)
        
        # Current state is 2 lots (2 on CMPD-0000002 and 0 on CMPD-0000002 (which is now deleted))

        # Create a restricted lot by project to verify we can reparent it for our user auth tests
        # This actually creates 2 lots in the system but returns one back by corp name
        restricted_lot_corp_name = self.create_restricted_lot(project.code_name)
        # Current state is 4 lots (3 on CMPD-0000002 and 1 on CMPD-0000001 (which is now re-created))
        self.assertEqual(restricted_lot_corp_name, "CMPD-0000002-003")

        # Deny Rule: Must be cmpdreg admin
        self.assertFalse(can_reparent_lot(self, cmpdreg_user, restricted_lot_corp_name, "CMPD-0000001", dry_run = False))
        self.assertFalse(can_reparent_lot(self, cmpdreg_user_with_restricted_project_acls, restricted_lot_corp_name, "CMPD-0000001", dry_run = False))
        self.assertFalse(can_reparent_lot(self, acas_user, restricted_lot_corp_name, "CMPD-0000001", dry_run = False))
        self.assertFalse(can_reparent_lot(self, acas_user_restricted_project_acls, restricted_lot_corp_name, "CMPD-0000001", dry_run = False))
        self.assertFalse(can_reparent_lot(self, acas_admin, restricted_lot_corp_name, "CMPD-0000001", dry_run = False))
        # Current state has not changed)

        # Allow Rule: CmpdReg Admin
        self.assertTrue(can_reparent_lot(self, cmpdreg_admin, restricted_lot_corp_name,  "CMPD-0000001", dry_run = True))
        self.assertTrue(can_reparent_lot(self, cmpdreg_admin, restricted_lot_corp_name,  "CMPD-0000001", dry_run = False))
        # Current state is 4 lots (2 on CMPD-0000002 and 2 on CMPD-0000001)

        # Verify we have our expected current state by counting lots and parents
        all_lots = self.client.get_all_lots()
        self.assertEqual(len(all_lots), 4)
        
        # Get a count of lots per parent
        parents = {}
        for lot in all_lots:
            if lot["parentCorpName"] not in parents:
                parents[lot["parentCorpName"]] = 1
            else:
                parents[lot["parentCorpName"]] += 1

        # Verify we have 2 lots per parent after the re-arranging we did
        self.assertEqual(parents["CMPD-0000002"], 2)
        self.assertEqual(parents["CMPD-0000001"], 2)
    
class TestExperimentLoader(BaseAcasClientTest):
    """Tests for `Experiment Loading`."""
    
    # Test for malformed single quote format file
    def assert_malformed_single_quote_file(self, response):
        self.assertTrue(response['hasError'])
        self.assertIn('errorMessages', response)
        hasEOFError = False 
        for message in response['errorMessages'] :
            if(message['message'].endswith('EOF within quoted string')):
                hasEOFError = True
        self.assertTrue(hasEOFError)

    # Test to check if expected messages are in messages from experiment loader
    def check_expected_messages(self, expected_messages, messages):
        for expected_message in expected_messages:
            # This matches the response error message and level to the expected message and level
            expected_result = [m for m in messages if m['errorLevel'] == expected_message['errorLevel'] and m['message'] == expected_message['message']]
            if 'count' in expected_message:
                if expected_message['count'] > -1:
                    # If count is present and not -1, then we expect the number of results to be equal to the count
                    self.assertEqual(len(expected_result), expected_message['count'])
                else:
                    # If coount is -1, then we don't care about the number of results, just as long as it has the message
                    self.assertGreaterThan(len(expected_result), 0)
            else:
                # Should return 1 and only 1 match
                self.assertEqual(len(expected_result), 1)

    @requires_basic_cmpd_reg_load
    def test_001_basic_xlsx(self):
        """Test experiment loader xlsx format."""

        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', '1_1_Generic.xlsx')
        self.experiment_load_test(data_file_to_upload, True)
        self.experiment_load_test(data_file_to_upload, False)

    @requires_basic_cmpd_reg_load
    def test_002_basic_xls(self):
        """Test experiment loader xls format."""
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', '1_1_Generic.xls')
        self.experiment_load_test(data_file_to_upload, True)
        self.experiment_load_test(data_file_to_upload, False)

    @requires_basic_cmpd_reg_load
    def test_003_basic_xls_1995_fails(self):
        """Test experiment loader 1995 xls format fails."""
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', '1_1_Generic-XLS_50_1995_Fail.xls')
        response = self.experiment_load_test(data_file_to_upload, True)
        expected_messages = [
            {
                "errorLevel": "error",
                "message": "Cannot read input excel file: OldExcelFormatException (Java): The supplied spreadsheet seems to be Excel 5.0/7.0 (BIFF5) format. POI only supports BIFF8 format (from Excel versions 97/2000/XP/2003)"
            }
        ]
        self.check_expected_messages(expected_messages, response['errorMessages'])

    @requires_basic_cmpd_reg_load
    def test_004_basic_csv(self):
        """Test experiment loader csv format."""
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', 'uniform-commas-with-quoted-text.csv')
        self.experiment_load_test(data_file_to_upload, True)
        self.experiment_load_test(data_file_to_upload, False)

    @requires_basic_cmpd_reg_load
    def test_005_basic_tsv(self):
        """Test experiment loader tsv format."""
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', 'uniform-commas-with-quoted-text.csv')
        txt_file = csv_to_txt(data_file_to_upload, self.tempdir)
        self.experiment_load_test(txt_file, True)
        self.experiment_load_test(txt_file, False)

    @requires_basic_experiment_load
    def test_006_expt_reload(self, experiment):
        """Test for experiment reloading."""
        
        code_of_previous_experiment = experiment['codeName']

        # Reload the experiment
        # It's expected that this file has the same name as that loaded by `requires_basic_cmpd_reg_load` and will delete and reload the experiment getting a new code name
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', 'uniform-commas-with-quoted-text.csv')
        result = self.experiment_load_test(data_file_to_upload, False)
        expected_messages = [
            {
                "errorLevel": "warning",
                "message": f"Experiment '{BASIC_EXPERIMENT_LOAD_EXPERIMENT_NAME}' already exists, so the loader will delete its current data and replace it with your new upload. If you do not intend to delete and reload data, enter a new Experiment Name."
            }
        ]
        self.check_expected_messages(expected_messages, result['errorMessages'])

        # Check that the code name is different
        self.assertNotEqual(code_of_previous_experiment, result['results']['experimentCode'])

        # Get the original experiment by code name and verify it was deleted and that it's modified date is newer than the reloaded experiment
        # TODO: Then we changed the default config to server.project.roles.enabled=true, it broke this test
        # Because the get experiment by code route uses this and will not return experiments which have their deleted and ignored flags set to true.
        # We may change this behavior in the future, or come upe with way of modifying the configs during tests but for now we'll just comment this out.
        # original_experiment = self.client.get_experiment_by_code(code_of_previous_experiment)
        # self.assertTrue(original_experiment['deleted'])
        # self.assertTrue(original_experiment['ignored'])
        # self.assertGreater(original_experiment['modifiedDate'], experiment['modifiedDate'])

        # Get new experiment and make sure that the "previous experiment code" value is set in ls states of the new experiment
        new_experiment = self.client.get_experiment_by_code(result['results']['experimentCode'])
        has_previous_code = False
        for ls_state in new_experiment['lsStates']:
            if ls_state['ignored'] == False and ls_state['deleted'] == False and ls_state['lsType'] == "metadata" and ls_state['lsKind'] == "experiment metadata":
                for ls_value in ls_state['lsValues']:
                    if ls_value['ignored'] == False and ls_value['deleted'] == False and ls_value['lsType'] == "codeValue" and ls_value['lsKind'] == "previous experiment code" and ls_value['codeValue'] == code_of_previous_experiment:
                        has_previous_code = True
                    
        if not has_previous_code:
            self.fail("Could not find previous experiment code in ls states of the reloaded experiment")

    @requires_basic_cmpd_reg_load
    def test_007_non_unitform_comma_csv(self):
        # Test for non-uniform comma format file
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', 'non-uniform-commas-with-quoted-text.csv')
        self.experiment_load_test(data_file_to_upload, True)
        self.experiment_load_test(data_file_to_upload, False)
        txt_file = csv_to_txt(data_file_to_upload, self.tempdir)
        self.experiment_load_test(txt_file, True)
        self.experiment_load_test(txt_file, False)

    @requires_basic_cmpd_reg_load
    def test_008_malformed_single_quote(self):

        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', 'malformatted-single-quote.csv')
        response = self.experiment_load_test(data_file_to_upload, True)
        self.assert_malformed_single_quote_file(response)
        txt_file = csv_to_txt(data_file_to_upload, self.tempdir)
        response = self.experiment_load_test(txt_file, True)
        self.assert_malformed_single_quote_file(response)

    @requires_basic_cmpd_reg_load
    def test_009_speed(self):
        # Speed test dry run
        try:
            # Dry run on 50 K row file with 3 columns of data should take
            # less than 25 seconds to complete. On my machine it takes
            # about 9 seconds. This is a sanity check to make sure the
            # dry run hasn't slowed significantly.
            with Timeout(seconds=25):
                data_file_to_upload = Path(__file__).resolve()\
                    .parent.joinpath('test_acasclient', '50k-lines.csv')
                self.experiment_load_test(data_file_to_upload, True)
        except TimeoutError:
            self.fail("Timeout error")

    @requires_basic_cmpd_reg_load
    def test_010_experiment_loader_curve_validation(self):
        # Test dose response curve validation
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', '4 parameter D-R-validation.csv')

        response = self.experiment_load_test(data_file_to_upload, True)

        # When loading Dose Resposne format but not having ACAS fit the curves, we shold get a dose response summary table
        self.assertTrue(response['results']['htmlSummary'].find("bv_doseResponseSummaryTable") != -1)

        # Leaving this comment here on how this dict was generted in case there are expected changes we want to make to the expected results match the current results
        # print(json.dumps(response['errorMessages'], sort_keys=True, indent=4))
        expected_messages = [
            {
                "errorLevel": "error",
                "message": "No 'Rendering Hint' was found for curve id '9629'. If a curve id is specified, it must be associated with a Rendering Hint."
            },
            {
                "errorLevel": "warning",
                "message": "The following parameters were not found for curve id '9629'.  Please provide values for these parameters so that curves are drawn properly: EC50"
            },
            {
                "errorLevel": "warning",
                "message": "The following parameters were not found for curve id '8836'.  Please provide values for these parameters so that curves are drawn properly: Min"
            },
            {
                "errorLevel": "warning",
                "message": "The following parameters were not found for curve id '8806'.  Please provide values for these parameters so that curves are drawn properly: Max"
            },
            {
                "errorLevel": "warning",
                "message": "The following parameters were not found for curve id '8788'.  Please provide values for these parameters so that curves are drawn properly: Slope"
            },
            {
                "errorLevel": "warning",
                "message": "The following parameters were not found for curve id '126933'.  Please provide values for these parameters so that curves are drawn properly: Slope, Max"
            },
            {
                "errorLevel": "warning",
                "message": "The following parameters were not found for curve id '126915'.  Please provide values for these parameters so that curves are drawn properly: Slope, Min, Max, EC50"
            },
            {
                "errorLevel": "error",
                "message": "Could not find `Calculated Results` match for `Raw Results` links: 'f'"
            },
            {
                "errorLevel": "warning",
                "message": "A date is not in the proper format. Found: \"5/8/15\" This was interpreted as \"2015-08-05\". Please enter dates as YYYY-MM-DD."
            },
            {
                "errorLevel": "warning",
                "message": "The R&#178; for curve id 'a' is 0.215 which is < than the threshold value of 0.9."
            },
            {
                "errorLevel": "warning",
                "message": "The R&#178; for curve id 'b' is 0.858 which is < than the threshold value of 0.9."
            },
            {
                "errorLevel": "warning",
                "message": "The R&#178; for curve id 'c' is 0.0601 which is < than the threshold value of 0.9."
            }
        ]
        self.check_expected_messages(expected_messages, response['errorMessages'])

    @requires_basic_cmpd_reg_load
    def test_011_dose_response_experiment_loader(self):
        """Test dose response experiment loader."""
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', '4 parameter D-R.csv')
        request = {
            "data_file": data_file_to_upload,
            "user": "bob",
            "dry_run": True,
            "model_fit_type": "4 parameter D-R",
            "fit_settings": {
                "smartMode":True,
                "inactiveThresholdMode":True,
                "inactiveThreshold":20,
                "theoreticalMaxMode":False,
                "theoreticalMax":None,
                "inverseAgonistMode":False,
                "max":{
                    "limitType":"none"
                },
                "min":{
                    "limitType":"none"
                },
                "slope":{
                    "limitType":"none"
                },
                "baseline":{
                    "value":0
                }
            }
        }
        response = self.client.\
            dose_response_experiment_loader(**request)
        self.assertIn("experiment_loader_response", response)
        self.assertIn('results', response["experiment_loader_response"])
        self.assertIn('errorMessages', response["experiment_loader_response"])
        self.assertIn('hasError', response["experiment_loader_response"])
        self.assertIn('hasWarning', response["experiment_loader_response"])
        self.assertIn('transactionId', response["experiment_loader_response"])
        self.assertIsNone(response["experiment_loader_response"]['transactionId'])
        self.assertIsNone(response['dose_response_fit_response'])

        # When loading dose response data and doing a curve fit we shold NOT get a dose response summary table because acas isn't evaluating the uploaded
        # curve fit parameters (it replaces it with it's own curve fits)
        self.assertTrue(response["experiment_loader_response"]['results']['htmlSummary'].find("bv_doseResponseSummaryTable") == -1)

        # Read the file as a string so that we can update the data
        with open(data_file_to_upload, 'r') as f:
            data_file_as_string = f.read()

        # Substitute Format with "Generic" to test for warning for uploading Generic to 
        # a Dose Response experiment
        data_file_as_string = data_file_as_string.replace("Format,Dose Response", "Format,Generic")
        request["data_file"] = {
            "name": f.name,
            "data": data_file_as_string
        }
        response = self.client.\
            dose_response_experiment_loader(**request)

        # Dose response load should warn that a Generic file was uploaded which had a curve id
        self.assertIn("experiment_loader_response", response)
        self.assertIn('results', response["experiment_loader_response"])
        self.assertIn('hasWarning', response["experiment_loader_response"])
        self.assertTrue(response["experiment_loader_response"]['hasWarning'])
        self.assertIn('errorMessages', response["experiment_loader_response"])
        # Assert that error messages has a warning message
        genericFormatUploadedAsDoseResponse = "The upload 'Format' was set to 'Generic' and a 'curve id' column was found. Curve data may not upload correctly."
        matchingMessage = None
        for error_message in response["experiment_loader_response"]['errorMessages']:
            if error_message['errorLevel'] == 'warning':
                # Check if warning has the message in it
                if genericFormatUploadedAsDoseResponse in error_message['message']:
                    matchingMessage = True
        if matchingMessage is None:
            self.fail("ACAS did not produce warning that 'Generic' was uploaded as 'Dose")
        
        # Use the original data file for further tests
        request["data_file"] = data_file_to_upload
        request["dry_run"] = False
        response = self.client.\
            dose_response_experiment_loader(**request)

        self.assertIn('transactionId', response["experiment_loader_response"])
        self.assertIsNotNone(response["experiment_loader_response"]['transactionId'])
        self.assertIsNotNone(response["experiment_loader_response"]['results'])
        self.assertIsNotNone(response["experiment_loader_response"]['results']['experimentCode'])

        self.assertIn('dose_response_fit_response', response)
        self.assertIn('results', response["dose_response_fit_response"])
        self.assertIn('htmlSummary', response["dose_response_fit_response"]['results'])
        self.assertIn('status', response["dose_response_fit_response"]['results'])
        self.assertEqual(response["dose_response_fit_response"]['results']['status'], 'complete')

        # Get Experiment results
        experiment = self.client.\
            get_experiment_by_code(response["experiment_loader_response"]['results']['experimentCode'], full = True)
        self.assertIsNotNone(experiment)
        self.assertIn("analysisGroups", experiment)

        accepted_results_file_path = Path(__file__).resolve().parent\
            .joinpath('test_acasclient', "test_dose_response_experiment_loader_accepted_results.json")

        # Leaving this here to show how to update the accepted results file
        # with open(accepted_results_file_path, 'w') as f:
        #     json.dump(experiment, f, indent=2)

        experiment = anonymize_experiment_dict(experiment)
        
        accepted_results_experiment  = json.loads(accepted_results_file_path.read_text())
        accepted_results_analysis_groups = anonymize_experiment_dict(accepted_results_experiment)["analysisGroups"]
        new_results_analysis_groups = experiment["analysisGroups"]

        # Verify that the analysis groups are the same as the accepted results analysis groups
        # Groups should have been sorted by the "Key" analysis group value uploaded in the dose response file
        
        for i in range(len(accepted_results_analysis_groups)):
            self.assertDictEqual(accepted_results_analysis_groups[i], new_results_analysis_groups[i])

    @requires_basic_cmpd_reg_load
    def test_012_escaped_quotes_xls(self):
        """Test experiment loader with escaped quotes in xls file"""
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', 'escaped_quotes.xls')
        self.experiment_load_test(data_file_to_upload, True)
        response = self.experiment_load_test(data_file_to_upload, False)
        # Check the loaded experiment
        experiment = self.client.\
            get_experiment_by_code(response['results']['experimentCode'], full = True)
        self.assertIsNotNone(experiment)
        self.assertIn("analysisGroups", experiment)
        # Find the clobValue
        clob_value = None
        for analysis_group in experiment["analysisGroups"]:
            for state in analysis_group["lsStates"]:
                for value in state["lsValues"]:
                    if value["lsKind"] == "Test JSON":
                        clob_value = value["clobValue"]
        # Ensure the clob value can be parsed as JSON
        self.assertIsNotNone(clob_value)
        parsed_json = json.loads(clob_value)
        self.assertIsNotNone(parsed_json)
    
    @requires_basic_cmpd_reg_load
    def test_012_escaped_quotes_csv(self):
        """Test experiment loader with escaped quotes in csv file
        This is a negative test - the experiment load is expected to fail at present. """
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', 'escaped_quotes.csv')
        # Validate the experiment
        self.experiment_load_test(data_file_to_upload, True)
        # Try to load and commit - this is expected to fail
        with self.assertRaises(AssertionError) as context:
            response = self.experiment_load_test(data_file_to_upload, False)
        # # Check the loaded experiment
        # experiment = self.client.\
        #     get_experiment_by_code(response['results']['experimentCode'], full = True)
        # self.assertIsNotNone(experiment)
        # self.assertIn("analysisGroups", experiment)
        # # Find the clobValue
        # clob_value = None
        # for analysis_group in experiment["analysisGroups"]:
        #     for state in analysis_group["lsStates"]:
        #         for value in state["lsValues"]:
        #             if value["lsKind"] == "Test JSON":
        #                 clob_value = value["clobValue"]
        # # Ensure the clob value can be parsed as JSON
        # self.assertIsNotNone(clob_value)
        # parsed_json = json.loads(clob_value)
        # self.assertIsNotNone(parsed_json)
