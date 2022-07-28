"""Main module."""

import requests
import logging
import os
import configparser
import json
from pathlib import Path
from pathlib import PurePath
import re
import base64
import hashlib
from io import StringIO, IOBase

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

VALID_STRUCTURE_SEARCH_TYPES = {"substructure", "duplicate",
                        "duplicate_tautomer", "duplicate_no_tautomer",
                        "stereo_ignore", "full_tautomer", "substructure",
                        "similarity", "full"}

def isBase64(s):
    return (len(s) % 4 == 0) and re.match('^[A-Za-z0-9+/]+[=]{0,2}$', s)


def creds_from_file(fpath, profile="default"):
    """Fetches crecentials from a file

    Retrieves credentials from a file.

    Args:
        fpath: Path to the credentials file
        profile: Optional string which specifies which section to read from
        the credentials file.  Defaults to "default"
    Returns:
        A section of the configuration file.

    """
    config = configparser.ConfigParser()
    config.read(fpath)
    return config[profile]


def get_default_credentials(profile="default"):
    """Fetches default credentials to use for client authentication.

    Retrievies credentials from ~/.acas/credentials file or
    preferentially from the environment variables
    ACAS_API_{USERNAME, PASSWORD and URL}

    Args:
        profile: Optinal string which specifies which section to read from
        the credentials file.
    Returns:
        A dict of credentials fetched. For example:

        .. code-block:: python

            {'username': "USERNAME",
            'password': "PASSWORD",
            'url': "URL"}

        Example setting via environment variables:

        .. code-block:: console

                $ export ACAS_API_USERNAME=bob
                $ export ACAS_API_PASSWORD=secret
                $ export ACAS_API_URL=http://localhost:3000

        If any one of the three environment variables are not found then the
        credentials file at ``~/.acas/credentials`` is used.

        Example credentials file:

        .. code-block:: ini

            [default]
            username=bob
            password=secret
            url=http://localhost:3000

        If the environment variable ``ACAS_API_PROFILE`` is set then it will be
        used as the default credential section from the credentials file
        otherwise, the ``[default]`` section is used. For example:

        .. code-block:: console

                $ export ACAS_API_PROFILE=myserver

        The ``myserver`` section credentials will be read:

        .. code-block:: ini

            [mysever]
            username=bob
            password=secret
            url=http://localhost:3000

    """
    try:
        data = {}
        data['username'] = os.environ['ACAS_API_USERNAME']
        data['password'] = os.environ['ACAS_API_PASSWORD']
        data['url'] = os.environ['ACAS_API_URL']
        logger.debug("Using credentials from ACAS_API_CREDENTIALS environment"
                     " variable.")
    except KeyError:
        homedir = os.environ['HOME']
        creds_file = Path(homedir, '.acas', 'credentials')
        logger.debug("Looking for credentials in {}".format(creds_file))
        if 'ACAS_API_PROFILE' in os.environ:
            profile = os.environ['ACAS_API_PROFILE']
        else:
            profile = profile
        data = creds_from_file(creds_file, profile)
    return {'username': data['username'], 'password': data['password'],
            'url': data['url']}


def get_entity_value_by_state_type_kind_value_type_kind(entity, state_type,
                                                        state_kind, value_type,
                                                        value_kind):
    """Get a value from an acas entity dict object.

    Gets a specific value from an acas entity dict object.

    Args:
        entity: Any ACAS entity (protocol, experiment, analysis_group,
        treatment_group, container...etc.)
        state_type: String. The state type of the value.
        state_kind: String. The state kind of the value.
        value_type: String. The value type of the value.
        value_kind: String. The value type of the value.

    Returns:
        A dict object representing the value if it exits. Ot.herwise it
        returns None

    """
    value = None
    if len(entity["lsStates"]) > 0:
        for s in entity["lsStates"]:
            if (not s["deleted"] and not s["ignored"] and
                    s["lsType"] == state_type and s["lsKind"] == state_kind):
                for v in s["lsValues"]:
                    if (not v["deleted"] and not v["ignored"] and
                            v["lsType"] == value_type and
                            v["lsKind"] == value_kind):
                        value = v
                        break
    return value

def sdf_iterator(iteratable):
    data = []
    for line in iteratable:
        data.append(line)
        if line.startswith("$$$$"):
            yield "".join(data)
            data = []

def get_mol_as_dict(mol):
    """
    Returns a dict representation of a molecule in cluding the mol block, the ctab and the properties as a key value pair
    """
    lines = mol.split("\n")
    properties = {}
    property = None
    ctab = None
    ctab_complete = False
    for line in lines:
        if line.startswith(">"):
            ctab_complete = True
            if property is not None:
                properties[property] = properties[property] = "\n".join(properties[property])
            property = line.split("<")[1].split(">")[0].strip()
            properties[property] = []
        else:
            if not ctab_complete:
                if ctab is None:
                    ctab = line + "\n"
                else:
                    ctab += line + "\n"
            if property is not None:
                if line.strip() != "":
                    properties[property].append(line.strip())
                else:
                    properties[property] = "\n".join(properties[property])
                    property = None
    return {"mol": mol, "ctab": ctab, "properties": properties}

def parse_file(file_content, file_extension):
    """Parse content from a string into an extension specific format

    Args:
        file_content (str): Content of the file
        file_extension (str): Extension of the file

    Returns:
        Parsed content of the file in a format specific to the extension
    """
    if file_extension == '.sdf':
        return parse_sdf(file_content)
    elif file_extension == '.json':
        return json.loads(file_content)
    else:
        return None

def parse_sdf(file_content):
    """Parse an SDF file content

    Parse an SDF file

    Args:
        file_content (bytes): Content of the file

    Returns:
        Parsed content of the file
    """
    sdf_data = []
    file_content = StringIO(file_content.decode('utf-8'))
    for e, mol in enumerate(sdf_iterator(file_content)):
        mol_dict = get_mol_as_dict(mol)
        sdf_data.append(mol_dict)
    return sdf_data 


class client():

    def __init__(self, creds):
        self.username = creds['username']
        self.password = creds['password']
        self.url = creds['url']
        self.session = self.getSession()

    def close(self):
        self.session.close()

    def getSession(self):
        data = {
            'username': self.username,
            'password': self.password
        }
        session = requests.Session()
        resp = session.post("{}/login".format(self.url),
                            headers={'Content-Type': 'application/json'},
                            data=json.dumps(data),
                            allow_redirects=False)
        resp.raise_for_status()
        if resp.status_code == 302 and 'location' in resp.headers and resp.headers.get('location') == "/login":
            raise RuntimeError("Failed to login. Please check credentials.")
        return session

    def projects(self):
        """Get projects authorized to user.

        List of projects user is authorized to see.

        Args:
            None

        Returns:
            An array of dict objects representing the projects the user has
            access to.

            For example:

        .. code-block:: python

            [
                {'active': True,
                'alias': 'Global',
                'code': 'PROJ-00000001',
                'id': 2,
                'isRestricted': False,
                'name': 'Global'}
            ]

        """
        url = "{}/api/projects".format(self.url)
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def upload_files(self, files):
        """Upload a list of files to ACAS.

        Pass an array of files to ACAS and upload them to the server

        Args:
            files: An array of either string paths, Path objects (see
            :py:class:`pathlib.Path`), base64 encoded strings, or dicts
            with "name" and "data" (base64 encoded data) attributes.

        Returns:
            An object of responses from ACAS in the form:

        .. code-block:: python

            {'files': [
                {'name': '1_1_Generic.xlsx',
                'originalName': '1_1_Generic.xlsx',
                'size': 12887,
                'type': None,
                'deleteType': 'DELETE',
                'url': 'http://localhost:3000/dataFiles/1_1_Generic.xlsx',
                'deleteUrl': 'http://localhost:3000/uploads/1_1_Generic.xlsx'}
            ]}
        """
        filesToUpload = {}
        for file in files:
            if isinstance(file, Path):
                filesToUpload[str(file)] = file.open('rb')
            elif isBase64(file):
                filesToUpload[str("file")] = base64.decodebytes(file.encode())
            elif isinstance(file, dict):
                if isBase64(file['data']):
                    filesToUpload[file["name"]] = base64.decodebytes(
                        file["data"].encode())
                else:
                    filesToUpload[file["name"]] = file["data"]
            else:
                filesToUpload[str(file)] = file.open('rb')
        resp = self.session.post("{}/uploads".format(self.url),
                                 files=filesToUpload)
        # Close the open files
        for file in filesToUpload:
            # Check if the file is a file object
            if isinstance(filesToUpload[file], IOBase):
                filesToUpload[file].close()

        resp.raise_for_status()
        return resp.json()

    def get_meta_lot(self, lot_corp_name):
        """Get metalot by lot corp name
         Granted read permission on a lot if one of these is true:
            1. The user is the owner of the lot (chemist or recorded by)
            2. The user has access to the project the lot is associated with
            3. The user is a cmpdreg admin

        Args:
            lot_corp_name (str): A lot corp name

        Returns: Returns a dict meta lot object
        """
        resp = self.session.get("{}/cmpdreg/metalots/corpName/{}/"
                                .format(self.url, lot_corp_name))
        if resp.status_code == 500:
            return None
        resp.raise_for_status()
        return resp.json()

    def save_meta_lot(self, meta_lot):
        """Save a meta lot to the server
         If updating a saved lot permissions are granted if one of these is true:
            1. Edit my lots is configured to true on the system and..
                a. The user is the owner of the lot (chemist or recorded by)
                b. The user has access to the project the lot is associated with
            2. The user is a cmpdreg admin

        Args:
            meta_lot (dict): A meta lot

        Returns: Returns a dict meta lot object
        """
        resp = self.session.post("{}/cmpdreg/metalots".
                                 format(self.url),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(meta_lot))
        resp.raise_for_status()
        return resp.json()

    def cmpd_search(self, corpNameList="", corpNameFrom="", corpNameTo="",
                    aliasContSelect="contains", alias="", dateFrom="",
                    dateTo="", searchType="substructure", percentSimilarity=90,
                    chemist="anyone", maxResults=100, molStructure=""
                    ):
        search_request = dict(locals())
        del search_request['self']

        if searchType not in VALID_STRUCTURE_SEARCH_TYPES:
            raise ValueError("cmpd_search: searchType must be one of %r."
                             % VALID_STRUCTURE_SEARCH_TYPES)
        return self.cmpd_search_request(search_request)

    def cmpd_structure_search(self, searchType="substructure", percentSimilarity=90,
                    maxResults=100, molStructure=""
                    ):
        search_request = dict(locals())
        del search_request['self']

        if searchType not in VALID_STRUCTURE_SEARCH_TYPES:
            raise ValueError("cmpd_search: searchType must be one of %r."
                             % VALID_STRUCTURE_SEARCH_TYPES)
        return self.cmpd_structure_search_request(search_request)

    def get_all_lots(self):
        """Get all lots

        Get all lots the currently logged in user is allowed to access

        Returns: Returns an array of dict objects
            id (id): the lot corp name
            lotCorpName (str): the lot corp name
            lotNumber (int): the lot number
            parentCorpName (str): the lots parent corp name
            registrationDate (int): the registration date
            project (str): the lots project
        """
        resp = self.session.get("{}/cmpdReg/parentLot/getAllAuthorizedLots"
                                .format(self.url))
        resp.raise_for_status()
        return resp.json()

    def cmpd_search_request(self, search_request):
        search_request["loggedInUser"] = self.username
        if("corpNameList" not in search_request):
            search_request["corpNameList"] = ""
        if("corpNameFrom" not in search_request):
            search_request["corpNameFrom"] = ""
        if("corpNameTo" not in search_request):
            search_request["corpNameTo"] = ""
        if("aliasContSelect" not in search_request):
            search_request["aliasContSelect"] = "contains"
        if("alias" not in search_request):
            search_request["alias"] = ""
        if("dateFrom" not in search_request):
            search_request["dateFrom"] = ""
        if("dateTo" not in search_request):
            search_request["dateTo"] = ""
        if("searchType" not in search_request):
            search_request["searchType"] = "substructure"
        if("dateFrom" not in search_request):
            search_request["dateFrom"] = ""
        if("percentSimilarity" not in search_request):
            search_request["percentSimilarity"] = 90
        if("percentSimilarity" not in search_request):
            search_request["percentSimilarity"] = 90
        if("chemist" not in search_request):
            search_request["chemist"] = "anyone"
        if("maxResults" not in search_request):
            search_request["maxResults"] = 100

        resp = self.session.post("{}/cmpdreg/search/cmpds".
                                 format(self.url),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(search_request))
        resp.raise_for_status()
        return resp.json()

    def cmpd_structure_search_request(self, search_request):
        if("searchType" not in search_request):
            search_request["searchType"] = "substructure"
        if("percentSimilarity" not in search_request):
            search_request["percentSimilarity"] = 90

        resp = self.session.post("{}/cmpdreg/structuresearch/".
                                 format(self.url),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(search_request))
        resp.raise_for_status()
        return resp.json()

    def export_cmpd_search_results(self, search_results):
        """Export an sdf of compound search results.

        Given a search results dict object this will export a list of matching
        compounds to an SDF file.

        Args:
            search_results: Dict object

        Search criteria for lots

        .. code-block:: python

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

        Full List of potential search results

        .. code-block:: python

            search_results = {
                "foundCompounds": [
                    {
                        "corpName": "CMPD-0000001",
                        "corpNameType": "Parent",
                        "lotIDs": [
                            {
                                "corpName": "CMPD-0000001-001",
                                "lotNumber": 1,
                                "registrationDate": "01/29/2020",
                                "synthesisDate": "01/29/2020"
                            }
                        ],
                        "molStructure": "MOLFILE STRUCTURE"
                        "parentAliases": [],
                        "stereoCategoryName": "Achiral",
                        "stereoComment": ""
                    }
                ],
                "lotsWithheld": False
            }

        Returns:
            An object of responses from ACAS in the form:

        .. code-block:: python

            {'reportFilePath':
                '/dataFiles/exportedSearchResults/2020_02_12_1581466283857_searchResults.sdf',
            'summary': 'Successfully exported 1 lots.'
            }

        See the output of :func:`get_sdf_file_for_lots` for SDF details.
        """
        resp = self.session.post("{}/cmpdReg/export/searchResults".
                                 format(self.url),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(search_results))
        resp.raise_for_status()
        return resp.json()

    def get_sdf_file_for_lots(self, lots):
        """Get an SDF file object from an array of lot corp names

        Given an array of lots this function fetches and SDF file for those
        lots with their lot and parent attibutes

        Args:
            lots: Array of lot corp names
        Returns:
            ACAS file dict object with sdf content

        Output object structure:

        .. code-block:: python

            {'content-type': 'application/octet-stream',
            'content-length': '1642',
            'last-modified': 'Wed, 12 Feb 2020 00:49:09 GMT',
            'name': '2020_02_12_1581468549556_searchResults.sdf',
            'content': b'SDFILE CONTENT'}

        SDF Attributes:


        * Amount Units Code (str): amount units
        * Buid (int): legacy field not used
        * Bulk Load File (str): Bulk load file that the lot came from
        * Chemist (str): the lot chemist
        * Lot Corp Name (str):
        * Is Virtual (bool): Is this a virtual compound
        * Lot Mol Weight (float): Lot weight (includes salt weight)
        * Lot Number (int):
        * Project (str):
        * Registration Date (str): Lot registration date in the
          format "2020-02-11"
        * Lot Registered By (str):
        * Salt Form Corp Name (str): Salt form name
        * Parent Corp Name (str):
        * Parent Number (int): Internal parent identifier
        * Parent Stereo Category (str):
        * Parent Mol Weight (float):
        * Parent Exact Mass (float):
        * Parent Mol Formula (str):
        * Parent Registration Date (str): Parent registration date in the
          format "2020-02-11"
        * Parent Registered By (str):

        """
        lotIds = []
        for lot in lots:
            lotIds.append({"corpName": lot})
        search_results = {
            "foundCompounds": [
                {
                    "lotIDs": lotIds,
                }
            ]
        }
        search_results_export = self.export_cmpd_search_results(search_results)
        search_results_file = self.get_file(search_results_export[
                                            'reportFilePath'])
        return search_results_file

    def write_sdf_file_for_lots(self, lots, dir_or_file_path):
        """Get and write an SDF from lot corp name array

        Given an array of lots this function fetches and SDF file for those
        lots with their lot and parent attibutes and write an SDF file

        Args:
            lots: Array of lot corp names
        Returns:
            ACAS file dict object with sdf content

        See the output of :func:`get_sdf_file_for_lots` for SDF details.
        """
        sdf_file = self.get_sdf_file_for_lots(lots)
        file_path = self.write_file(sdf_file, dir_or_file_path)
        return file_path

    def get_file(self, file_path, parse_content=True):
        """Get a file from ACAS

        Get a file from ACAS

        Note:
            If behind a proxy some fields (denoted with a ``*``) may not be
            filled

        Args:
            file_path (str): A path to a file known to exist in ACAS

        Returns: ACAS file dict object with file content
            content-type* (str): Content type of the file
            content-length* (int): Content length in bytes of the file
            last-modified* (str): Date file was last mofied
            name (str): Name of the file
            content (str): Content of the file
            parsed_content (depends): Parsed content of the file
        """
        resp = self.session.get("{}{}".format(self.url, file_path))
        resp.raise_for_status()
        name = PurePath(Path(file_path)).name
        return_dict = {
            'content-type': resp.headers.get('content-type', None),
            'content-length': resp.headers.get('content-length', None),
            'last-modified': resp.headers.get('Last-modified', None),
            'name': name,
            'content': resp.content}

        # Get file extension
        file_extension = PurePath(Path(file_path)).suffix
        
        if parse_content:
            try:
                # This function returns None if the file extension is not
                # recognized
                return_dict['parsed_content'] = parse_file(
                    resp.content, file_extension)
            except Exception as e:
                # In case there is an error parsing the file, just return the
                # None
                logger.warning("Could not parse file: {}".format(e))
                return_dict['parsed_content'] = None

        return return_dict

    def protocol_search(self, search_term):
        """Search for protocols by search term

        Get an array of protocols given a protocol search term string

        Args:
            searchTerm (str): A protocol search term

        Returns: Returns an array of protocols
        """
        resp = self.session.get("{}/api/protocols/genericSearch/{}"
                                .format(self.url, search_term))
        resp.raise_for_status()
        return resp.json()

    def get_protocols_by_label(self, label):
        """Get all experiments for a protocol from a protocol label

        Get an array of experiments given a protocol label

        Args:
            label (str): A protocol label

        Returns: Returns an array of experiments
        """
        resp = self.session.get("{}/api/getProtocolByLabel/{}"
                                .format(self.url, label))
        resp.raise_for_status()
        return resp.json()

    def get_experiments_by_protocol_code(self, protocol_code):
        """Get all experiments for a protocol from a protocol code

        Get an array of experiments given a protocol code

        Args:
            protocol_code (str): A protocol code

        Returns: Returns an array of experiments
        """
        resp = self.session.get("{}/api/experiments/protocolCodename/{}".
                                format(self.url, protocol_code))
        if resp.status_code == 500:
            return None
        else:
            resp.raise_for_status()
        return resp.json()

    def get_experiment_by_name(self, experiment_name):
        """Get an experiment from experiment name

        Get an experiment given an experiment name

        Args:
            experiment_name (str): An experiment name

        Returns: Returns an experiment object or None if the experiment not found
        """

        resp = self.session.get("{}/api/experiments/experimentName/{}".
                                format(self.url, experiment_name))
        if resp.status_code == 500:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_experiment_by_code(self, experiment_code, full = False):
        """Get an experiment from an experiment code

        Get an experiment given an experiment code

        Args:
            experiment_code (str): An experiment code code
            full (bool): If true, return the full experiment object

        Returns: Returns an experiment object
        """

        params = {}
        if full:
            params = {**params, 'fullObject': True}
        resp = self.session.get("{}/api/experiments/codename/{}".
                                format(self.url, experiment_code),
                                params = params)
        if resp.status_code == 500:
            return None
        else:
            resp.raise_for_status()
        return resp.json()

    def get_source_file_for_experient_code(self, experiment_code):
        """Get the source file for an experiment

        Gets the experiment loader file for ACAS

        Note:
            If behind a proxy some fields (denoted with a ``*``) may not be
            filled

        Args:
            file_path (str): A path to a file known to exist in ACAS

        Returns: ACAS file dict object with file content
            content-type* (str): Content type of the file
            content-length* (int): Content length in bytes of the file
            last-modified* (str): Date file was last mofied
            name (str): Name of the file
            content (str): Content of the file

        """
        experiment = self.get_experiment_by_code(experiment_code)
        if not experiment:
            return None
        source_file = get_entity_value_by_state_type_kind_value_type_kind(
            experiment,
            "metadata",
            "experiment metadata",
            "fileValue",
            "source file")
        file = None
        if source_file and "fileValue" in source_file:
            file = self.get_file("/dataFiles/{}"
                                 .format(source_file['fileValue']))
        return file

    def write_file(self, file, dir_or_file_path):
        dir_or_file_path = Path(dir_or_file_path)
        if dir_or_file_path.is_dir():
            file_path = dir_or_file_path.joinpath(file['name'])
        else:
            file_path = dir_or_file_path
        mode = "w"
        if type(file['content']) is bytes:
            mode = "wb"
        with open(file_path, mode) as f:
            f.write(file['content'])
        return file_path

    def write_source_file_for_experient_code(self, experiment_code, dir):
        source_file = self.get_source_file_for_experient_code(experiment_code)
        file_path = None
        if source_file:
            file_path = self.write_file(source_file, dir)
        return file_path

    def register_sdf_request(self, data):
        resp = self.session.post("{}/api/cmpdRegBulkLoader/registerCmpds"
                                 .format(self.url),
                                 headers={'Content-Type': 'application/json'},
                                 data=json.dumps(data))
        resp.raise_for_status()
        return resp.json()
    
    def _validate_sdf_request(self, data):
        resp = self.session.post("{}/api/cmpdRegBulkLoader/validateCmpds"
                                 .format(self.url),
                                 headers={'Content-Type': 'application/json'},
                                 data=json.dumps(data))
        resp.raise_for_status()
        return resp.json()

    def register_sdf(self, file, userName, mappings, prefix=None, dry_run=False):
        files = self.upload_files([file])
        request = {
            "fileName": files['files'][0]["name"],
            "userName": userName,
            "mappings": mappings,
        }
        if prefix:
            request["labelPrefix"] = {
                "name": prefix,
                "labelPrefix": prefix,
                "labelTypeAndKind": "id_corpName",
                "thingTypeAndKind": "parent_compound"
            }
        if dry_run:
            response = self._validate_sdf_request(request)
        else:
            response = self.register_sdf_request(request)
        report_files = []
        for file in response[0]['reportFiles']:
            filePath = "/dataFiles/cmpdreg_bulkload/{}".format(
                PurePath(Path(file)).name)
            report_files.append(self.get_file(filePath))
        return {"id": response[0]['id'],
                "summary": response[0]['summary'],
                "results": response[0]['results'],
                "report_files": report_files}

    def experiment_loader_request(self, data):
        resp = self.session.post("{}/api/genericDataParser".format(self.url),
                                 headers={'Content-Type': 'application/json'},
                                 data=json.dumps(data))
        resp.raise_for_status()
        return resp.json()

    def _dose_response_fit_request(self, dose_response_request_dict):
        """ Send a dose response fit request to ACAS
        
        This is a private method that is used to send a dose response fit json request to ACAS. It is not intended to be used directly.

        Args:
            dose_response_request_dict (dict): A dictionary containing the request parameters for the dose response fit request.
        """
    
        resp = self.session.post("{}/api/doseResponseCurveFit".format(self.url),
                                 headers={'Content-Type': 'application/json'},
                                 data=json.dumps(dose_response_request_dict))
        resp.raise_for_status()
        return resp.json()

    def experiment_loader(self, data_file, user, dry_run, report_file="",
                          images_file="", validate_dose_response_curves=True):
        """Load an experiment
        
        Load an experiment into ACAS.

        Args:
            data_file (str): A path to an experiment loader formatted file
            user (str): A username
            dry_run (bool): If true, then validate but do not load the data into the database
            report_file (str): A path to a report file (optional)
            images_file (str): A path to an images file (optional)
        """
        data_file = self.upload_files([data_file])['files'][0]["name"]
        if report_file and report_file != "":
            report_file = self.upload_files([report_file])['files'][0]["name"]
        if images_file and images_file != "":
            images_file = self.upload_files([images_file])['files'][0]["name"]
        request = {"user": user,
                   "fileToParse": data_file,
                   "reportFile": report_file,
                   "imagesFile": images_file,
                   "moduleName": None if validate_dose_response_curves else "DoseResponseDataParserController",
                   "dryRunMode": dry_run}
        resp = self.experiment_loader_request(request)
        return resp

    def dose_response_experiment_loader(self, model_fit_type, fit_settings, **kwargs):
        """Dose response experiment loader
        
        Args:
            model_fit_type (str): The type of model fit to perform
            fit_settings (dict): The settings for the model fit
            **kwargs: All required arguments to pass to the experiment loader (e.g. data_file, user, dry_run = True/False)

        Returns:
            dict: The response from the experiment loader and doseresponse fit request
             
            Example:

                {
                    "experiment_loader_response": experiment_loader_response_resp_dict,
                    "dose_response_fit_response": dose_response_fit_response_resp_dict
                }
    
        Example:
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
            response = client.\
                dose_response_experiment_loader(**request)
        """

        resp = self.experiment_loader(validate_dose_response_curves=False, **kwargs)
        response = {
            "experiment_loader_response": resp,
            "dose_response_fit_response": None
        }
        if resp['hasError'] == False and resp['commit'] == True:
            request = {
                "experimentCode": resp['results']['experimentCode'],
                "modelFitType": model_fit_type,
                "testMode": False,
                "user": kwargs['user'],
                "inputParameters": json.dumps(fit_settings)
            }
            dose_response_resp = self._dose_response_fit_request(request)
            response["dose_response_fit_response"] = dose_response_resp
        return response

    def delete_experiment(self, idOrCode):
        """Delete an experiment

        Deletes an experiment.  If a code name is given, the experiment is
        first retrieved by code name and then deleted by id.

        Args:
            idOrCode (int or str): An experiment id or an experiment code name

        Returns: Dict object with the experiment status value of the deleted
                 experiment

        """
        if isinstance(idOrCode, str):
            experiment = self.get_experiment_by_code(idOrCode)
            if experiment is None:
                return None
            else:
                idOrCode = experiment['id']

        resp = self.session.delete("{}/api/experiments/{}".
                                   format(self.url, idOrCode)
                                   )
        resp.raise_for_status()
        return resp.json()

    def experiment_search(self, query):
        resp = self.session.get("{}/api/experiments/genericSearch/{}/"
                                .format(self.url, query))
        return resp.json()

    def get_cmpdreg_bulk_load_files(self):
        """Get cmpdreg bulk load files

        Gets a list of all cmpdreg bulk files on the system

        Returns: An array of dict objects
            fileDate (int): The epoch date the file was registered
            fileName (str): The name of the file
            fileSize (int): Size in bytes of the file
            id (int): The file id
            numberOfMols (int): Number of mols registered by this file
            recordedBy (str): Username of the user who registered the file
            version (int): The file version number

        """
        resp = self.session.get("{}/api/cmpdRegBulkLoader/getFilesToPurge"
                                .format(self.url))
        return resp.json()

    def check_cmpdreg_bulk_load_file_dependency(self, id):
        """Check cmpdreg bulk load file dependencies

        Check for dependencies of cmpdreg bulk load file

        Args:
            id (int): A bulk load file id

        Returns: Dict object with file content
            canPurge (bool): Can this file be purged
            summary (str): An html formatted summary of the dependencies

        """
        request = {
            "fileInfo": {
                "id": id
            }
        }
        resp = self.session.post("{}/api/cmpdRegBulkLoader/checkFileDependencies".
                                 format(self.url),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(request))
        if resp.text == '"Error"':
            return None
        return resp.json()

    def purge_cmpdreg_bulk_load_file(self, id):
        """Purge a cmpdreg bulk load file

        Purges a cmpdreg bulk load file

        Args:
            id (int): A bulk load file id

        Returns: Dict object with file content
            fileName (str): The name of the file that was purged
            success (bool): Did the file purge successfully
            summary (str): An html formatted summary of the purge results

        """
        request = {
            "fileInfo": {
                "id": id
            }
        }
        resp = self.session.post("{}/api/cmpdRegBulkLoader/purgeFile".
                                 format(self.url),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(request))
        if resp.text == '"Error"':
            return None
        return resp.json()

    def get_ls_thing(self, ls_type, ls_kind, code_name, nestedfull=True):
        """
        Get a models.LsThing object by ls_type, ls_kind, and code_name

        Args:
            ls_type (str): Type of ls thing
            ls_kind (str): Kind of ls thing
            code_name (str): Code name of ls thing

        """
        resp = self.session.get("{}/api/things/{}/{}/{}".
                                format(self.url,
                                       ls_type,
                                       ls_kind,
                                       code_name),
                                params={'nestedfull': nestedfull})
        if resp.status_code == 500:
            return None
        else:
            resp.raise_for_status()
        return resp.json()
    
    def delete_ls_thing(self, ls_type, ls_kind, code_name, format):
        """
            Deletes a models.LsThing object by ls_type, ls_kind, and code_name
            Args:
                ls_type (str): Type of ls thing
                ls_kind (str): Kind of ls thing
                code_name (str): Code name of ls thing
                format (str)
        """
        if not format:
            format = 'nestedfull'
        resp = self.session.delete(
            "{}/api/things/{}/{}/{}".format(self.url, ls_type, ls_kind,
                                            code_name),
            params={format: True})
        if resp.status_code == 500:
            return None
        else: 
            resp.raise_for_status()
        return resp

    def save_ls_thing(self, ls_thing):
        """
        Persist a models.LsThing object to ACAS

        Args:
            ls_thing (dict): A dict object representing an ls thing

        Returns: Dict object representing a saved ls_thing
        """

        resp = self.session.post("{}/api/things/{}/{}".
                                 format(self.url,
                                        ls_thing["lsType"],
                                        ls_thing["lsKind"]),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(ls_thing))
        resp.raise_for_status()
        return resp.json()

    def get_ls_things_by_codes(self, ls_type, ls_kind, code_name_list,
                               nestedfull=True):
        """
        Get a list of ls thing dict objects from a list of their code_names

        Args:
            ls_type (str): ls_type for all things to retrieve
            ls_kind (str): ls_kind for all things to retrieve
            code_name_list (str list): list of str code_names
        """
        params = {}
        if nestedfull:
            params = {**params, 'with': 'nestedfull'}
        resp = self.session.post("{}/api/things/{}/{}/codeNames/jsonArray".
                                 format(self.url,
                                        ls_type,
                                        ls_kind),
                                 params=params,
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(code_name_list))
        if resp.status_code == 500:
            return None
        else:
            resp.raise_for_status()
        return resp.json()

    def get_ls_things_by_type_and_kind(self, ls_type, ls_kind,
                                       format='stub'):
        """
        Get a list of ls thing dict objects from ls_type and ls_kind

        Args:
            ls_type (str): ls_type for all things to retrieve
            ls_kind (str): ls_kind for all things to retrieve
        """
        allowedFormats = {'codetable', 'stub'}
        if format not in allowedFormats:
            raise ValueError("format must be one of %s." % allowedFormats)
        params = {format: '1'}
        resp = self.session.get("{}/api/things/{}/{}".
                                format(self.url,
                                       ls_type,
                                       ls_kind),
                                params=params,
                                headers={'Content-Type': "application/json"})
        if resp.status_code == 500:
            return None
        else:
            resp.raise_for_status()
        return resp.json()

    def save_ls_thing_list(self, ls_thing_list):
        """
        Save a list of ls thing dict objects

        Args:
            ls_thing_list (str): list of ls_thing dict objects
        """
        resp = self.session.post("{}/api/bulkPostThingsSaveFile".
                                 format(self.url),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(ls_thing_list))
        resp.raise_for_status()
        return resp.json()

    def update_ls_thing_list(self, ls_thing_list):
        """
        Update a list of ls thing dict objects

        Args:
            ls_thing_list (str): list of ls_thing dict objects
        """
        # TODO: generate a transaction
        resp = self.session.put("{}/api/bulkPutThingsSaveFile".
                                format(self.url),
                                headers={'Content-Type': "application/json"},
                                data=json.dumps(ls_thing_list))
        resp.raise_for_status()
        return resp.json()

    def get_thing_codes_by_labels(self, thing_type, thing_kind, labels_or_codes, label_type=None, label_kind=None):
        """
        Get a list of thing codes by providing a list of labels

        Args:
            labels_or_codes (str list): list of str labels or codes
            thing_type (str): ls_type for all things to retrieve
            thing_kind (str): ls_kind for all things to retrieve
            label_type (str): label_type to limit label searches
            label_kind (str): label_kind to limit label searches
        Returns:
            ref_name_lookup_results: list of objects with
                requestName (str): input label string
                preferredName (str): LsThing preferred label string
                referenceName (str): LsThing code name string
        """
        request = {
            'thingType': thing_type,
            'thingKind': thing_kind,
            'labelType': label_type,
            'labelKind': label_kind,
            'requests': [
                {"requestName": request} for request in labels_or_codes
            ]
        }

        resp = self.session.post("{}/api/getThingCodeByLabel".
                                 format(self.url),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(request))
        if resp.status_code == 500:
            return None
        else:
            resp.raise_for_status()
        resp_object = resp.json()
        if resp_object == 'error trying to lookup lsThing name':
            raise RuntimeError("Failed to get things, please see acas logs.")
        results = resp_object['results']
        return results

    def get_saved_entity_codes(self, ls_type, ls_kind, id_list, label_type=None, label_kind=None):
        """
        Query ACAS to determine which identifiers (labels) are already saved

        Args:
            ls_type (str): LsThing lsType to query for
            ls_kind (str): LsThing lsKind to query for
            id_list (str): list of identifier strings
            label_type (str): label_type to limit label searches
            label_kind (str): label_kind to limit label searches
        Returns:
            saved_codes (dict): dict of identifier : LsThing codeName for previously saved entities
            missing_ids (list): list of identifiers that were not found to be previously saved
        """
        # Query ACAS for list of identifiers
        ref_name_lookup_results = self.get_thing_codes_by_labels(
            ls_type, ls_kind, id_list, label_type, label_kind)
        # Parse results into found and not found
        saved_codes = {}
        missing_ids = []
        for res in ref_name_lookup_results:
            ident = res['requestName']
            if res['referenceName'] and len(res['referenceName']) > 0:
                saved_codes[ident] = res['referenceName']
            else:
                missing_ids.append(ident)
        return saved_codes, missing_ids

    def advanced_search_ls_things(self, ls_type, ls_kind, search_string,
                                  value_listings=[], label_listings=[],
                                  first_itx_listings=[], second_itx_listings=[],
                                  codes_only=False,
                                  max_results=1000, combine_terms_with_and=False,
                                  format='stub'):
        """
        Query ACAS for deeply specified conditions

        Args:
            ls_type (str): LsThing lsType to match
            ls_kind (str): LsThing lsKind to match
            search_string (str): str to match on or compare to
            value_listings (list): list of dicts of a structure like:
                {
                    "stateType": "metadata",
                    "stateKind": "pdb",
                    "valueType": "stringValue",
                    "valueKind": "librarian search status",
                    "operator": "="
                }
            combine_terms_with_and (bool): Whether to combine terms with 'and'
            format (str): ACAS format to fetch data in
        Returns:
            if codes_only:
                list of code_name strings
            otherwise:
                list of LsThing objects
        """
        request = {
            'queryString': search_string,
            'queryDTO': {
                'maxResults': max_results,
                'lsType': ls_type,
                'lsKind': ls_kind,
                'values': value_listings,
                'labels': label_listings,
                'firstInteractions': first_itx_listings,
                'secondInteractions': second_itx_listings,
                'combineTermsWithAnd': combine_terms_with_and,
            }
        }
        params = {}
        if codes_only:
            format = 'codetable'
        params['format'] = format
        resp = self.session.post('{}/api/advancedSearch/things/{}/{}'.
                                 format(self.url,
                                        ls_type,
                                        ls_kind),
                                 data=json.dumps(request),
                                 headers={'Content-Type': "application/json"},
                                 params=params)
        result = resp.json()
        if type(result) is not dict:
            msg = 'Caught error response from {}: {}'.format(
                '/api/advancedSearch/things', result)
            logger.error(msg)
            raise ValueError(msg)
        results = result['results']
        if codes_only:
            return [res['code'] for res in results]
        else:
            return results

    def create_label_sequence(self, labelPrefix, startingNumber, digits,
                              labelSeparator, labelTypeAndKind=None, thingTypeAndKind=None,
                              labelSequenceRoles=[]):
        """
        Create a label sequence

        Args:
            labelPrefix (str): Prefix of the label
            startingNumber (str): Set to 0 for the first number to be 1
            digits (str): The number of leading zeros to add to the label sequence when formatting (e.g. CMPD-0000007 would be digts: 7 )
            labelTypeAndKind (str): the label type and kind associated with this sequence (used for finding all labels of a specific label type and kind in some interfaces)
            thingTypeAndKind (str): the thing type and kind associated with this sequence (used for finding all labels of a specific thing type and kind in some interfaces)
            labelSequenceRoles (list): the registered role to associate with this label (used for limiting access to specific label sequences in some interfaces)

        Returns:
            a dict object representing the new label sequence
        """
        request = {
            'labelPrefix': labelPrefix,
            'startingNumber': startingNumber,
            'digits': digits,
            'labelSeparator': labelSeparator,
            'labelTypeAndKind': labelTypeAndKind,
            'thingTypeAndKind': thingTypeAndKind,
            'labelSequenceRoles': labelSequenceRoles
        }
        resp = self.session.post("{}/api/labelsequences/".
                                 format(self.url),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(request))
        resp.raise_for_status()
        return resp.json()

    def get_all_label_sequences(self):
        """
        Get all label sequences (limited to those authorized by logged in user roles)

        Returns:
            a list of dict objects representing the labelSequence
        """

        json = self.get_label_sequence_by_types_and_kinds()
        return json

    def get_label_sequence_by_types_and_kinds(self, labelTypeAndKind=None, thingTypeAndKind=None):
        """
        Get label sequence by types and kinds (limited to those authorized by logged in user roles)

        Args:
            labelPrefix (str): Prefix of the label
            startingNumber (str): Set to 0 for the first number to be 1
            digits (str): The number of leading zeros to add to the label sequence when formatting (e.g. CMPD-0000007 would be digts: 7 )
            labelTypeAndKind (str): the label type and kind associated with this sequence (used for finding all labels of a specific label type and kind in some interfaces)
            thingTypeAndKind (str): the thing type and kind associated with this sequence (used for finding all labels of a specific thing type and kind in some interfaces)
            labelSequenceRoles (list): the registered role to associate with this label (used for limiting access to specific label sequences in some interfaces)

        Returns:
            a list of dict objects representing the labelSequence
        """
        params = {}
        if labelTypeAndKind:
            params = {**params, 'labelTypeAndKind': labelTypeAndKind}
        if thingTypeAndKind:
            params = {**params, 'thingTypeAndKind': thingTypeAndKind}
        resp = self.session.get("{}/api/labelSequences/getAuthorizedLabelSequences".
                                format(self.url),
                                params=params)
        resp.raise_for_status()
        return resp.json()

    def get_labels(self, labelTypeAndKind, thingTypeAndKind, numberOfLabels):
        """
        Get next n labels from label sequence prefix

        Args:
            labelTypeAndKind (str): Prefix of the registered label (see create_label_sequence)
            numberOfLabels (int): Number of labels to fetch

        Returns:
            a list of dict objects representing the labelSequence
        """
        request = {
            'labelTypeAndKind': labelTypeAndKind,
            'thingTypeAndKind': thingTypeAndKind,
            'numberOfLabels': numberOfLabels
        }
        resp = self.session.post("{}/api/getNextLabelSequence".
                                 format(self.url),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(request))
        resp.raise_for_status()
        return resp.json()

    def get_all_ddict_values(self):
        """
        Get all ddict values

        Returns:
            a list of dict objects representing the ddict value (aka code value)
        """
        all_values = self.get_ddict_values_by_type_and_kind()
        return all_values

    def get_ddict_values_by_type_and_kind(self, codeType=None, codeKind=None):
        """
        Get ddict values

        Returns:
            a list of dict objects representing the ddict value (aka code value)
        """
        path = "/api/codetables"
        if codeType and codeKind:
            path = "{}/{}/{}".format(path, codeType, codeKind)
        resp = self.session.get("{}{}".
                                format(self.url, path))
        resp.raise_for_status()
        return resp.json()

    def get_blob_data_by_value_id(self, valueId):
        """
        Get blob data by value id
        Args:
            valueId (int): A known value id to fetch from the database that is stored as a blobValue lsType

        Returns:
            (bytes): representing the blob value
        """

        resp = self.session.get("{}/api/thingvalues/downloadThingBlobValueByID/{}"
                                .format(self.url, valueId))
        resp.raise_for_status()
        return resp.content
    
    def get_authors(self):
        """
        Get all authors

        Returns:
            a list of dict objects representing the authors
        """
        resp = self.session.get("{}/api/authors".format(self.url))
        resp.raise_for_status()
        return resp.json()
    
    def get_author_by_username(self, username):
        """
        Get author by username
            
        Args:
            username (str): The username of the author to fetch

        Returns:
            a dict object representing the author
        """
        resp = self.session.get("{}/api/authorByUsername/{}".format(self.url, username))
        resp.raise_for_status()
        return resp.json()
    
    def create_author(self, author):
        """
        Create an author

        Args:
            author (dict): A dict object representing the author to create

        Returns:
            a dict object representing the new author
        """
        def hash_password(password):
            """ Calculate the base64-encoded sha1 hash of the password for ACAS built-in authentication """
            hasher = hashlib.sha1()
            hasher.update(password.encode('utf-8'))
            return base64.b64encode(hasher.digest()).decode('utf-8')
        if 'password' in author:
            author['password'] = hash_password(author['password'])
        resp = self.session.post("{}/api/author".format(self.url),
                                    json=author)
        resp.raise_for_status()
        return resp.json()
    
    def update_author(self, author):
        """Update an author

        Args:
            author (dict): A dict object representing the author to update

        Returns:
            a dict object representing the updated author
        """
        if 'id' not in author:
            raise ValueError("id attribute of author dict is required")
        resp = self.session.put("{}/api/author/{}".format(self.url, author.get('id')),
                                    json=author)
        resp.raise_for_status()
        return resp.json()
    
    def create_authors(self, authors):
        """
        Create authors

        Args:
            authors (list): A list of dicts representing the authors to create
            
        Returns:
            a list of dict objects representing the saved authors
        """
        return [self.create_author(author) for author in authors]
    
    def update_author_roles(self, new_author_roles=None, author_roles_to_delete=None):
        """
        Update author roles
        
        Args:
            new_author_roles (list): A list of dicts representing the new author roles to create
            author_roles_to_delete (list): A list of dicts representing the author roles to delete
            
        Returns:
            a list of dict objects representing the saved author roles
        """
        body = {
            'newAuthorRoles': new_author_roles or [],
            'authorRolesToDelete': author_roles_to_delete or [],
        }
        resp = self.session.post("{}/api/updateAuthorRoles".format(self.url),
                                    json=body)
        resp.raise_for_status()
        return resp.json()
    
    def update_project_roles(self, new_author_roles=None, author_roles_to_delete=None):
        """
        Same as update author roles but with a different endpoint name.
        """
        body = {
            'newAuthorRoles': new_author_roles or [],
            'authorRolesToDelete': author_roles_to_delete or [],
        }
        resp = self.session.post("{}/api/projects/updateProjectRoles".format(self.url),
                                    json=body)
        resp.raise_for_status()
        return resp.json()
    
    def _validate_then_save_codetable(self, url_base, codeTable: dict) -> dict:
        """
        Validate a codetable and save it to the database

        Args:
            url_base (str): The base URL for the codetable
            codeTable (dict): A dict object representing the codetable to save

        Returns:
            a dict object representing the saved codetable
        """
        # Validate
        resp = self.session.post(url_base + "/validateBeforeSave", json=codeTable)
        resp.raise_for_status()
        validation_resp = resp.json()
        if type(validation_resp) is list and len(validation_resp) > 0:
            raise ValueError(validation_resp[0]['message'])
        # Create
        resp = self.session.post(url_base, json=codeTable)
        resp.raise_for_status()
        return resp.json()
    
    def get_cmpdreg_scientists(self):
        """
        Fetch the list of possible lot chemists for CmpdReg
        """
        resp = self.session.get("{}/cmpdreg/scientists".format(self.url))
        resp.raise_for_status()
        return resp.json()
    
    def create_cmpdreg_scientist(self, code, name):
        """
        Create a new scientist for CmpdReg
        """
        url_base = "{}/api/codeTablesAdmin/compound/scientist".format(self.url)
        body = {'code': code, 'name': name}
        return self._validate_then_save_codetable(url_base, body)
    
    def update_cmpdreg_scientist(self, scientist: dict):
        """
        Update a scientist for CmpdReg
        """
        if 'id' not in scientist:
            raise ValueError("id attribute of scientist dict is required")
        resp = self.session.put("{}/api/codeTablesAdmin/compound/scientist/{}".format(self.url, scientist['id']), json=scientist)
        resp.raise_for_status()
        return resp.json()
    
    def delete_cmpdreg_scientist(self, id: int) -> bool:
        resp = self.session.delete("{}/api/codeTablesAdmin/{}".format(self.url, id))
        resp.raise_for_status()
        return True
    
    def get_stereo_categories(self):
        """
        Get all stereo categories
        """
        resp = self.session.get("{}/api/cmpdRegAdmin/stereoCategories".format(self.url))
        resp.raise_for_status()
        return resp.json()
    
    def create_stereo_category(self, code, name):
        """
        Create a new stereo category
        """
        url_base = "{}/api/cmpdRegAdmin/stereoCategories".format(self.url)
        body = {'code': code, 'name': name}
        return self._validate_then_save_codetable(url_base, body)
    
    def update_stereo_category(self, stereo_category: dict):
        """
        Update a stereo category
        """
        if 'id' not in stereo_category:
            raise ValueError("id attribute of stereo_category dict is required")
        resp = self.session.put("{}/api/cmpdRegAdmin/stereoCategories/{}".format(self.url, stereo_category['id']), json=stereo_category)
        resp.raise_for_status()
        # No return because backend doesn't return anything
    
    def delete_stereo_category(self, id: int) -> bool:
        resp = self.session.delete("{}/api/cmpdRegAdmin/stereoCategories/{}".format(self.url, id))
        resp.raise_for_status()
        return True
    
    def get_salts(self):
        """
        Get all salts
        """
        resp = self.session.get("{}/cmpdreg/salts".format(self.url))
        resp.raise_for_status()
        return resp.json()
    
    def create_salt(self, abbrev, name, mol_structure):
        """
        Create a new salt
        """
        resp = self.session.post("{}/cmpdreg/salts".format(self.url), json={'abbrev': abbrev, 'name': name, 'molStructure': mol_structure})
        resp.raise_for_status()
        return resp.json()
    
    def get_physical_states(self):
        """
        Get all physical states
        """
        resp = self.session.get("{}/api/cmpdRegAdmin/physicalStates".format(self.url))
        resp.raise_for_status()
        return resp.json()
    
    def create_physical_state(self, code, name):
        """
        Create a new physical state
        """
        url_base = "{}/api/cmpdRegAdmin/physicalStates".format(self.url)
        body = {'code': code, 'name': name}
        return self._validate_then_save_codetable(url_base, body)
    
    def update_physical_state(self, physical_state: dict):
        """
        Update a physical state
        """
        if 'id' not in physical_state:
            raise ValueError("id attribute of physical_state dict is required")
        resp = self.session.put("{}/api/cmpdRegAdmin/physicalStates/{}".format(self.url, physical_state['id']), json=physical_state)
        resp.raise_for_status()
        # No return because backend doesn't return anything
    
    def delete_physical_state(self, id: int) -> bool:
        resp = self.session.delete("{}/api/cmpdRegAdmin/physicalStates/{}".format(self.url, id))
        resp.raise_for_status()
        return True
    
    def get_cmpdreg_vendors(self):
        """
        Get all vendors for CmpdReg
        """
        resp = self.session.get("{}/api/cmpdRegAdmin/vendors".format(self.url))
        resp.raise_for_status()
        return resp.json()
    
    def create_cmpdreg_vendor(self, code, name):
        """
        Create a new vendor for CmpdReg
        """
        url_base = "{}/api/cmpdRegAdmin/vendors".format(self.url)
        body = {'code': code, 'name': name}
        return self._validate_then_save_codetable(url_base, body)
    
    def update_cmpdreg_vendor(self, vendor: dict):
        """
        Update a vendor for CmpdReg
        """
        if 'id' not in vendor:
            raise ValueError("id attribute of vendor dict is required")
        resp = self.session.put("{}/api/cmpdRegAdmin/vendors/{}".format(self.url, vendor['id']), json=vendor)
        resp.raise_for_status()
        # No return because backend doesn't return anything
    
    def delete_cmpdreg_vendor(self, id: int) -> bool:
        resp = self.session.delete("{}/api/cmpdRegAdmin/vendors/{}".format(self.url, id))
        resp.raise_for_status()
        return True

    def setup_items(self, item_type, items):
        """Create or update items of a given typeKind 
           ACAS Admin role for this operation

        Args:
            item_type (str): Type of item to create or update
            items (list): List of items to create or update
        """
        allowed_types = ['experimenttypes', 'experimentkinds', 'statetypes', 'statekinds', 'valuetypes', 'valuekinds',
                         'labeltypes', 'labelkinds', 'ddicttypes', 'ddictkinds', 'codetables','labelsequences', 'roletypes',
                         'rolekinds', 'lsroles']
        if item_type not in allowed_types:
            raise ValueError("item_type must be one of {}".format(allowed_types))
        resp = self.session.post("{}/api/setup/{}".format(self.url, item_type), json=items)
        resp.raise_for_status()
        return resp.json()

    def get_lot_dependencies(self, lot_corp_name, include_linked_lots=True):
        """Get lot dependencies for a lot by corp name

        Args:
            lot_corp_name (str): Corp name of lot to get dependencies for
            include_linked_lots (bool): Whether to include linked lots in the response, default True.  Linked lots are purely informational as they are not a dependency preventing the lot from being deleted.

        Returns:
            A dict of the lot dependencies
            For example:
            {
                "batchCodes": [
                    "CMPD-0000001-001"
                ],
                "linkedDataExists": true,
                "linkedExperiments": [
                    {
                        "acls": {
                            "delete": true,
                            "read": true,
                            "write": true
                        },
                        "code": "EXPT-00000009",
                        "comments": "CMPD-0000001-001",
                        "description": "6 results",
                        "ignored": false,
                        "name": "BLAH"
                    }
                ],
                "linkedLots": [
                    {
                        "acls": {
                            "delete": false,
                            "read": true,
                            "write": true
                        },
                        "code": "CMPD-0000001-002",
                        "ignored": false,
                        "name": "CMPD-0000001-002"
                    }
                ],
                "lot": {
                    ...the lot info...
                }
            }
        Raises:
            HTTPError: If permission denied
        """

        params = {'includeLinkedLots': str(include_linked_lots).lower()}
        resp = self.session.get("{}/cmpdreg/metalots/checkDependencies/corpName/{}"
                                .format(self.url, lot_corp_name),
                                params=params)
        if resp.status_code == 500:
            return None
        resp.raise_for_status()
        return resp.json()

    def delete_lot(self, lot_corp_name):
        """Delete a lot

        Args:
            lot_corp_name (str): Corp name of lot to delete

        Returns:
            A dict with "success": true if successful. For example
            {
                "success": true
            }
            Or None if there was an error
        Raises:
            HTTPError: If permission denied
        """
        resp = self.session.delete("{}/cmpdReg/metalots/corpName/{}"
                                .format(self.url, lot_corp_name))
        if resp.status_code == 500:
            return None
        resp.raise_for_status()
        return resp.json()

    def swap_parent_structures(self, corp_name1: str, corp_name2: str) -> bool:
        """Swap parent structures.

        Args:
            corp_name1 (str): Corporate ID of the first parent compound.
            corp_name2 (str): Corporate ID of the second parent compound.

        Returns:
            Whether structures were swapped.
        """

        data = {'corpName1': corp_name1, 'corpName2': corp_name2}
        resp = self.session.post(f'{self.url}/cmpdreg/swapParentStructures/', json=data)
        resp.raise_for_status()
        return not resp.json()["hasError"]
        
    def reparent_lot(self, lot_corp_name, new_parent_corp_name, dry_run=True):
        """Reparent a lot

        Args:
            lot_corp_name (str): Corp name of lot to reparent
            new_parent_corp_name (str): Corp name of new parent
            dry_run (bool): Whether to perform a dry run, default True

        Returns:
            A dict with information about expected changes
            {
                "dependencies": {
                    "linkedDataExists": true,
                    ...other dependency data...
                },
                "modifiedBy": "bob",
                "newLot": {
                    "corpName": "CMPD-0000003-002",
                    ...other lot info...
                    "saltForm": {
                        ...salt form info...
                        "parent": {
                            "corpName": "CMPD-0000003",
                            ...other parent info...
                    },
                },
                "originalLotCorpName": "CMPD-0000001-001",
                "originalParentCorpName": "CMPD-0000001"
                "originalParentDeleted": true
            }

            Or None if there was an error
        Raises:
            HTTPError: If permission denied
        """
        data = {
            'lotCorpName': lot_corp_name,
            'parentCorpName': new_parent_corp_name
        }

        # Set dry run url param
        params = {'dryRun': str(dry_run).lower()}

        resp = self.session.post("{}/api/cmpdRegAdmin/lotServices/reparent/lot"
                                .format(self.url),
                                 params=params,
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(data))
        if resp.status_code == 500:
            return None
        resp.raise_for_status()
        return resp.json()