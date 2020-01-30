"""Main module."""

import requests
import logging
import os
import configparser
import json
from pathlib import Path
from pathlib import PurePath

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def creds_from_file(fpath, profile):
    config = configparser.ConfigParser()
    config.read(fpath)
    return config[profile]


def get_default_credentials():
    '''
    Get ACAS credentials from ~/.acas/credentials
    or the env var ACAS_API_CREDENTIALS.
    '''
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
            profile = 'acas'
        data = creds_from_file(creds_file, profile)
    return {'username': data['username'], 'password': data['password'],
            'url': data['url']}


def get_entity_value_by_state_type_kind_value_type_kind(entity, state_type,
                                                        state_kind, value_type,
                                                        value_kind):
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
        url = "{}/api/projects".format(self.url)
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def upload_files(self, files):
        filesToUpload = {}
        for file in files:
            filesToUpload[str(file)] = file.open('rb')
        resp = self.session.post("{}/uploads".format(self.url),
                                 files=filesToUpload)
        resp.raise_for_status()
        return resp.json()

    def export_cmpd_search_results(self, search_results):
        resp = self.session.post("{}/cmpdReg/export/searchResults".
                                 format(self.url),
                                 headers={'Content-Type': "application/json"},
                                 data=json.dumps(search_results))
        resp.raise_for_status()
        return resp.json()

    def get_sdf_file_for_lots(self, lots):
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
        sdf_file = self.get_sdf_file_for_lots(lots)
        file_path = self.write_file(sdf_file, dir_or_file_path)
        return file_path

    def get_file(self, file_path):
        resp = self.session.get("{}{}".format(self.url, file_path))
        resp.raise_for_status()
        return {
                'content-type': resp.headers['content-type'],
                'content-length': resp.headers['content-length'],
                'last-modified': resp.headers['Last-modified'],
                'name': PurePath(Path(file_path)).name,
                'content': resp.content}

    def get_protocols_by_label(self, label):
        resp = self.session.get("{}/api/getProtocolByLabel/{}"
                                .format(self.url, label))
        resp.raise_for_status()
        return resp.json()

    def get_experiments_by_protocol_code(self, protocol_code):
        resp = self.session.get("{}/api/experiments/protocolCodename/{}".
                                format(self.url, protocol_code))
        resp.raise_for_status()
        return resp.json()

    def get_experiment_by_code(self, experiment_code):
        resp = self.session.get("{}/api/experiments/codename/{}".
                                format(self.url, experiment_code))
        resp.raise_for_status()
        return resp.json()

    def get_source_file_for_experient_code(self, experiment_code):
        experiment = self.get_experiment_by_code(experiment_code)
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

    def register_sdf(self, file, userName, mappings):
        files = self.upload_files([file])
        request = {
            "fileName": files['files'][0]["name"],
            "userName": userName,
            "mappings": mappings
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
