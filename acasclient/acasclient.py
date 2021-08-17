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

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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


class client():

    def __init__(self, creds):
        self.username = creds['username']
        self.password = creds['password']
        self.url = creds['url']
        self.session = self.getSession()

    def getSession(self):
        data = {
            'username': self.username,
            'password': self.password
        }
        session = requests.Session()
        resp = session.post("{}/login".format(self.url),
                            headers={'Content-Type': 'application/json'},
                            data=json.dumps(data))
        resp.raise_for_status()
        if 'location' in resp.headers and resp.headers.location == "/login":
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
        resp.raise_for_status()
        return resp.json()

    def get_meta_lot(self, lot_corp_name):
        """Get metalot by lot corp name

        Get a meta lot object from the lot corp name

        Args:
            lot_corp_name (str): A lot corp name

        Returns: Returns a dict meta lot object
        """
        resp = self.session.get("{}/cmpdreg/metalots/corpName/{}/"
                                .format(self.url, lot_corp_name))
        if resp.status_code == 500:
            return None
        else:
            resp.raise_for_status()
        return resp.json()

    def cmpd_search(self, corpNameList="", corpNameFrom="", corpNameTo="",
                    aliasContSelect="contains", alias="", dateFrom="",
                    dateTo="", searchType="substructure", percentSimilarity=90,
                    chemist="anyone", maxResults=100, molStructure=""
                    ):
        search_request = dict(locals())
        del search_request['self']
        VALID_SEARCH_TYPES = {"substructure", "duplicate",
                              "duplicate_tautomer", "duplicate_no_tautomer",
                              "stereo_ignore", "full_tautomer", "substructure",
                              "similarity", "full"}
        if searchType not in VALID_SEARCH_TYPES:
            raise ValueError("cmpd_search: searchType must be one of %r."
                             % VALID_SEARCH_TYPES)
        return self.cmpd_search_request(search_request)

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

    def get_file(self, file_path):
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

        """
        resp = self.session.get("{}{}".format(self.url, file_path))
        resp.raise_for_status()
        return {
            'content-type': resp.headers.get('content-type', None),
            'content-length': resp.headers.get('content-length', None),
            'last-modified': resp.headers.get('Last-modified', None),
            'name': PurePath(Path(file_path)).name,
            'content': resp.content}

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

    def get_experiment_by_code(self, experiment_code):
        """Get an experiment from an experiment code

        Get an experiment given an experiment code

        Args:
            experiment_code (str): An experiment code code

        Returns: Returns an experiment object
        """
        resp = self.session.get("{}/api/experiments/codename/{}".
                                format(self.url, experiment_code))
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

    def register_sdf(self, file, userName, mappings, prefix=None):
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
        response = self.register_sdf_request(request)
        report_files = []
        for file in response[0]['reportFiles']:
            filePath = "/dataFiles/cmpdreg_bulkload/{}".format(
                PurePath(Path(file)).name)
            report_files.append(self.get_file(filePath))
        return {"summary": response[0]['summary'],
                "report_files": report_files}

    def experiment_loader_request(self, data):
        resp = self.session.post("{}/api/genericDataParser".format(self.url),
                                 headers={'Content-Type': 'application/json'},
                                 data=json.dumps(data))
        resp.raise_for_status()
        return resp.json()

    def experiment_loader(self, data_file, user, dry_run, report_file="",
                          images_file=""):
        data_file = self.upload_files([data_file])['files'][0]["name"]
        if report_file and report_file != "":
            report_file = self.upload_files([report_file])['files'][0]["name"]
        if images_file and images_file != "":
            images_file = self.upload_files([images_file])['files'][0]["name"]
        request = {"user": user,
                   "fileToParse": data_file,
                   "reportFile": report_file,
                   "imagesFile": images_file,
                   "dryRunMode": dry_run}
        resp = self.experiment_loader_request(request)
        return resp

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
