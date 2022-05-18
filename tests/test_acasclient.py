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


EMPTY_MOL = """
  Mrv1818 02242010372D          

  0  0  0  0  0  0            999 V2000
M  END
"""

ACAS_NODEAPI_BASE_URL = "http://localhost:3001"

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

    # Round numeric values to 6 digits for comparison on different systems where calculations like EC50 might be different
    if value['lsType'] == "numericValue":
        if value["numericValue"] is not None:
            value["numericValue"] = round(value["numericValue"], 6)
    
    # Round uncertainty values as their calculations may vary from system to system
    if 'uncertainty' in value and value['uncertainty'] is not None:
        value["uncertainty"] = round(value["uncertainty"], 6)

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

class BaseAcasClientTest(unittest.TestCase):
    """ Base class for ACAS Client tests """
    def setUp(self):
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
        self.tempdir = tempfile.mkdtemp()
        # Set TestCase - maxDiff to None to allow for a full diff output when comparing large dictionaries
        self.maxDiff = None

    def tearDown(self):
        """Tear down test fixtures, if any."""
        try:
            shutil.rmtree(self.tempdir)
            for username in self.test_usernames:
                delete_backdoor_user(username)
        finally:
            self.client.close()

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
                    "sdfProperty": "Corporate ID"
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

    def test_006_register_sdf(self):
        """Test register sdf."""
        test_012_upload_file_file = Path(__file__).resolve().parent.\
            joinpath('test_acasclient', 'test_012_register_sdf.sdf')
        mappings = [
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
                "sdfProperty": "Corporate ID"
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

        response = self.client.register_sdf(test_012_upload_file_file, "bob",
                                            mappings)
        self.assertIn('report_files', response)
        self.assertIn('summary', response)
        self.assertIn('Number of entries processed', response['summary'])
        return response

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
        search_results_export = self.client.\
            get_file(search_results_export['reportFilePath'])

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

    def test_014_experiment_loader(self):
        """Test experiment loader."""

        def experiment_load_test(data_file_to_upload, dry_run_mode, self):
            response = self.client.\
                experiment_loader(data_file_to_upload, "bob", dry_run_mode)
            self.assertIn('results', response)
            self.assertIn('errorMessages', response)
            self.assertIn('hasError', response)
            self.assertIn('hasWarning', response)
            self.assertIn('transactionId', response)
            if dry_run_mode:
                self.assertIsNone(response['transactionId'])
            else:
                self.assertIsNotNone(response['transactionId'])
            return response

        def csv_to_txt(data_file_to_upload, self):
            # Get the file name but change it to .txt
            file_name = data_file_to_upload.name
            file_name = file_name.replace(".csv", ".txt")
            temp_file_path = Path(self.tempdir, file_name)
            # Change the delim to the new delim
            with open(data_file_to_upload, 'r') as f:
                with open(temp_file_path, 'w') as f2:
                    for line in f:
                        f2.write(line.replace(',', "\t"))
            return temp_file_path

        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', '1_1_Generic.xlsx')
        experiment_load_test(data_file_to_upload, True, self)
        experiment_load_test(data_file_to_upload, False, self)

        
        # Test for csv format file
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', 'uniform-commas-with-quoted-text.csv')
        experiment_load_test(data_file_to_upload, True, self)
        experiment_load_test(data_file_to_upload, False, self)
        txt_file = csv_to_txt(data_file_to_upload, self)
        experiment_load_test(txt_file, True, self)
        experiment_load_test(txt_file, False, self)

        # Test for non-uniform comma format file
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', 'non-uniform-commas-with-quoted-text.csv')
        experiment_load_test(data_file_to_upload, True, self)
        experiment_load_test(data_file_to_upload, False, self)
        txt_file = csv_to_txt(data_file_to_upload, self)
        experiment_load_test(txt_file, True, self)
        experiment_load_test(txt_file, False, self)

        # Test for malformed single quote format file
        def assert_malformed_single_quote_file(response, self):
            self.assertTrue(response['hasError'])
            self.assertIn('errorMessages', response)
            hasEOFError = False 
            for message in response['errorMessages'] :
                if(message['message'].endswith('EOF within quoted string')):
                    hasEOFError = True
            self.assertTrue(hasEOFError)

            
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', 'malformatted-single-quote.csv')
        response = experiment_load_test(data_file_to_upload, True, self)
        assert_malformed_single_quote_file(response, self)
        txt_file = csv_to_txt(data_file_to_upload, self)
        response = experiment_load_test(txt_file, True, self)
        assert_malformed_single_quote_file(response, self)

        # Speed test dry run
        try:
            # Dry run on 50 K row file with 3 columns of data should take
            # less than 25 seconds to complete. On my machine it takes
            # about 9 seconds. This is a sanity check to make sure the
            # dry run hasn't slowed significantly.
            with Timeout(seconds=25):
                data_file_to_upload = Path(__file__).resolve()\
                    .parent.joinpath('test_acasclient', '50k-lines.csv')
                experiment_load_test(data_file_to_upload, True, self)
        except TimeoutError:
            self.fail("Timeout error")
        else:
            pass


    def test_015_get_protocols_by_label(self):
        """Test get protocols by label"""
        protocols = self.client.get_protocols_by_label("Test Protocol")
        self.assertGreater(len(protocols), 0)
        self.assertIn('codeName', protocols[0])
        self.assertIn('lsLabels', protocols[0])
        self.assertEqual(protocols[0]["lsLabels"][0]["labelText"],
                         "Test Protocol")
        fakeProtocols = self.client.get_protocols_by_label("Fake Protocol")
        self.assertEqual(len(fakeProtocols), 0)

    def test_016_get_experiments_by_protocol_code(self):
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

    def test_017_get_experiment_by_code(self):
        """Test get experiment by code."""
        experiment = self.client.get_experiment_by_code("EXPT-00000001")
        self.assertIn('codeName', experiment)
        self.assertIn('lsLabels', experiment)
        experiment = self.client.get_experiment_by_code("FAKECODE")
        self.assertIsNone(experiment)

    def test_018_get_source_file_for_experient_code(self):
        """Test get source file for experiment code."""
        source_file = self.client.\
            get_source_file_for_experient_code("EXPT-00000001")
        self.assertIn('content', source_file)
        self.assertIn('content-type', source_file)
        self.assertIn('name', source_file)
        self.assertIn('content-length', source_file)
        self.assertIn('last-modified', source_file)
        source_file = self.client.\
            get_source_file_for_experient_code("FAKECODE")
        self.assertIsNone(source_file)

    def test_019_write_source_file_for_experient_code(self):
        """Test get source file for experiment code."""
        source_file_path = self.client.\
            write_source_file_for_experient_code("EXPT-00000001", self.tempdir)
        self.assertTrue(source_file_path.exists())

    def test_020_get_meta_lot(self):
        """Test get meta lot."""
        meta_lot = self.client.\
            get_meta_lot('CMPD-0000001-001')
        self.assertIsNotNone(meta_lot)
        self.assertEqual(meta_lot['lot']['corpName'], 'CMPD-0000001-001')

    def test_021_experiment_search(self):
        """Test experiment generic search."""
        results = self.client.\
            experiment_search('EXPT')
        self.assertIsNotNone(results)
        self.assertGreater(len(results), 0)
        self.assertIn('codeName', results[0])

    def test_022_get_cmpdreg_bulk_load_files(self):
        """Test get cmpdreg bulk load files."""
        results = self.client.\
            get_cmpdreg_bulk_load_files()
        self.assertIsNotNone(results)
        self.assertGreater(len(results), 0)
        self.assertIn('fileDate', results[0])

    def test_023_check_cmpdreg_bulk_load_file_dependency(self):
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
        self.assertIn('summary', results)

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
        # not currently easy to look up a bulk load files so we will just purge the latest one
        # get all bulk load files and then find the latest one
        files = self.client.\
            get_cmpdreg_bulk_load_files()
        for index, file in enumerate(files):
            if index == 0:
                file_to_purge = file
            else:
                if file['fileDate'] > file_to_purge['fileDate']:
                    file_to_purge = file

        # purge the bulk load file
        results = self.client.\
            purge_cmpdreg_bulk_load_file(file_to_purge["id"])
        self.assertIn('summary', results)
        self.assertIn('Successfully purged file', results['summary'])
        self.assertIn('success', results)
        self.assertTrue(results['success'])

    def test_025_delete_experiment(self):
        """Test delete experiment."""
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', '1_1_Generic.xlsx')
        response = self.client.\
            experiment_loader(data_file_to_upload, "bob", False)
        self.assertIn('transactionId', response)
        self.assertIsNotNone(response['transactionId'])
        experiment_code = response['results']['experimentCode']
        response = self.client.\
            delete_experiment(experiment_code)
        self.assertIsNotNone(response)
        self.assertIn('codeValue', response)
        self.assertEqual('deleted', response['codeValue'])
        experiment = self.client.get_experiment_by_code(experiment_code)
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

    def test_042_cmpd_structure_search(self):
        """Test cmpd structure search request."""
        response = self.test_006_register_sdf()

        # Get a mapping of the registered parents and their structures
        for file in response['report_files']:
            if file['name'].endswith('registered.sdf'):
                registered_sdf_content = file['parsed_content']
                structures = {}
                for compound in registered_sdf_content:
                    meta_lot = self.client.get_meta_lot(compound['properties']['Registered Lot Corp Name'])
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

    def test_043_dose_response_experiment_loader(self):
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
                "min":
                    {
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
                if "The upload 'Format' was set to 'Generic' and a 'curve id' column was found. Curve data may not upload correctly." in error_message['message']:
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
        test_password = str(uuid.uuid4())
        self.test_usernames.append(test_username)
        new_user = create_backdoor_user(test_username, test_password)
        user_creds = {
            'username': test_username,
            'password': test_password,
            'url': self.client.url
        }
        user_client = acasclient.client(user_creds)
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
    
    def test045_register_sdf_case_insensitive(self):
        """Test register sdf with case insensitive lookups"""
        # test values
        CHEMIST = 'bob'
        CHEMIST_NAME = 'Bob Roberts'
        STEREO_CATEGORY = 'Unknown'
        SALT_ABBREV = 'HCl'
        SALT_MOL = "\n  Ketcher 05182214202D 1   1.00000     0.00000     0\n\n  1  0  0     1  0            999 V2000\n    6.9500   -4.3250    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0\nM  END\n"
        PHYSICAL_STATE = 'plasma'
        VENDOR = 'ThermoFisher'
        # TODO Lot Chemist, Stereo Category, Salt Abbrev, Physical State, Vendor
        # Get Lot Chemists
        lot_chemists = self.client.get_cmpdreg_scientists()
        # Create Lot Chemist
        if CHEMIST not in [c['code'] for c in lot_chemists]:
            lot_chemist = self.client.create_cmpdreg_scientist(code=CHEMIST, name=CHEMIST_NAME)
            self.assertIsNotNone(lot_chemist.get('id'))
        # Get Stereo Category
        stereo_categories = self.client.get_stereo_categories()
        # Create Stereo Category
        if STEREO_CATEGORY not in [c['code'] for c in stereo_categories]:
            stereo_category = self.client.create_stereo_category(code=STEREO_CATEGORY, name=STEREO_CATEGORY)
            self.assertIsNotNone(stereo_category.get('id'))
        # Get Salt Abbrevs
        salts = self.client.get_salts()
        # Create Salt Abbrev
        if SALT_ABBREV not in [s['abbrev'] for s in salts]:
            salt = self.client.create_salt(abbrev=SALT_ABBREV, name=SALT_ABBREV, mol_structure=SALT_MOL)
            self.assertIsNotNone(salt.get('id'))
        # Get Physical States
        physical_states = self.client.get_physical_states()
        # Create Physical State
        if PHYSICAL_STATE not in [p['code'] for p in physical_states]:
            physical_state = self.client.create_physical_state(code=PHYSICAL_STATE, name=PHYSICAL_STATE)
            self.assertIsNotNone(physical_state.get('id'))
        # Get Vendors
        vendors = self.client.get_cmpdreg_vendors()
        # Create Vendor
        if VENDOR not in [v['code'] for v in vendors]:
            vendor = self.client.create_cmpdreg_vendor(code=VENDOR, name=VENDOR)
            self.assertIsNotNone(vendor.get('id'))
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
        errors = response['results']
        self.assertEqual(len(errors), 0)
        # Register and confirm no errors
        response = self.client.register_sdf(upload_file_file, "bob",
                                            mappings)
        self.assertIn('results', response)
        errors = response['results']
        self.assertEqual(len(errors), 0)
        summary = response['summary']
        self.assertIn('New lots of existing compounds: 2', summary)