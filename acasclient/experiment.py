import logging
from typing import Optional, Union

from .acasclient import (get_entity_label_by_label_type_kind,
                         get_entity_value_by_state_type_kind_value_type_kind,
                         get_entity_values_by_state_type_kind_value_type)
from .selfile import get_file_type, load_from_str
from .acasclient import client
from .selfile import DoseResponse, Generic
from functools import wraps
import zipfile
import tempfile

################################################################################
# Logging
################################################################################
logger = logging.getLogger(__name__).addHandler(logging.NullHandler())

################################################################################
# Globals/Constants
################################################################################
ORIGINAL_PROJECT_KEY = "Original Project"
ORIGINAL_EXPT_CODE_KEY = "Original Experiment Code"
ORIGINAL_SERVER_KEY = "Original Server"
SOURCE_FILE_KEY = "source file"
REPORT_FILE_KEY = "annotation file"
DELETED_STATUS = "deleted"
ANALYSIS_GROUPS_KEY = "analysisGroups"
################################################################################
# Classes
################################################################################


def fetch_analysis_groups_if_missing(func):
    """Decorator to fetch analysis groups if they are missing from the experiment dict
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if ANALYSIS_GROUPS_KEY not in self:
            experiment_dict = self.client.get_experiment_by_code(self.code, full=True)
            self.__init__(experiment_dict, client=self.client)
        return func(self)
    return wrapper

class Experiment(dict):
    """Simple class which adds some convenience methods to an experiment dict to fetch common values and data from the experiment.
    """
    def __init__(self, expt_dict: dict, client: Optional[client] = None) -> None:
        dict.__init__(self, expt_dict)
        # set after source file is written
        self.exported_path = None
        # set after source file is transformed
        self.transformed_path = None

        if client is not None:
            self.client = client
        return
    
    @property
    def code(self) -> str:
        return self['codeName']

    @property
    def id(self) -> str:
        return self['id']

    @property
    def status(self) -> str:
        data = get_entity_value_by_state_type_kind_value_type_kind(
                entity=self,
                state_type="metadata",
                state_kind="experiment metadata",
                value_type="codeValue",
                value_kind="experiment status")
        return data["codeValue"]

    @property
    def deleted(self) -> bool:
        return self.status == DELETED_STATUS

    @property
    def protocol_name(self) -> str:
        protocol_name = get_entity_label_by_label_type_kind(
                entity=self["protocol"],
                label_type="name",
                label_kind="protocol name")
        return protocol_name["labelText"]

    @property
    def project(self) -> None:
        prj = get_entity_value_by_state_type_kind_value_type_kind(
                entity=self,
                state_type="metadata",
                state_kind="experiment metadata",
                value_type="codeValue",
                value_kind="project")
        return prj["codeValue"]

    @property
    def name(self) -> str:
        experiment_name = get_entity_label_by_label_type_kind(
                entity=self,
                label_type="name",
                label_kind="experiment name")
        return experiment_name["labelText"]

    @property
    def source_file(self) -> str:
        return self.get_experiment_metadata_file(SOURCE_FILE_KEY)

    def get_source_file(self, client: client = None) -> dict:
        file = None
        source_file = self.source_file
        if source_file is not None:
            if client is None:
                client = self.client
            file = client.get_file("/dataFiles/{}"
                        .format(source_file))
        return file
    
    @fetch_analysis_groups_if_missing
    def get_images_file(self, client: client = None) -> str:
        """Get a zip file of all the image (inline file values) in the experiment
        The zip image file isn't saved as a file in the experiment, but rather each image file is saved as an analysis group value. This method fetches all the image files and creates a zip file with them.

        Returns:
            str: The path to the zip file or None if there are no images in the experiment
        """

        # Loop through all the analysis groups and get the inline file values and add them to a set
        analysisGroups = self["analysisGroups"]
        inlineFilePaths = set()
        for ag in analysisGroups:
            inlineFileValues = get_entity_values_by_state_type_kind_value_type(ag, "data", "results", "inlineFileValue")
            for inlineFileValue in inlineFileValues:
                inlineFilePaths.add(inlineFileValue['fileValue'])

        # If there are no inline file values, return None
        if len(inlineFilePaths) == 0:
            return None
        
        # Create a unique zip file name
        images_file_to_upload = tempfile.NamedTemporaryFile(suffix=".zip").name

        # Fetch the files and write them to the zip file
        with zipfile.ZipFile(images_file_to_upload, 'w') as zip_ref:
            for inlineFilePath in inlineFilePaths:
                # Fetch the file from the API
                file = self.client.get_file("/dataFiles/{}"
                                    .format(inlineFilePath))
                # Write the file to base directory of the zip
                zip_ref.writestr(file["name"], file["content"])
        return images_file_to_upload

    @property
    def report_file(self) -> str:
        return self.get_experiment_metadata_file(REPORT_FILE_KEY)
    
    def get_report_file(self, client: client = None) -> dict:
        file = None
        report_file = self.report_file
        if report_file is not None:
            if client is None:
                client = self.client
            file = client.get_file("/dataFiles/{}"
                        .format(report_file))
        return file
    
    def get_experiment_metadata_file(self, value_kind) -> dict:
        data = get_entity_value_by_state_type_kind_value_type_kind(
            entity=self, 
            state_type="metadata", 
            state_kind="experiment metadata", 
            value_type="fileValue", 
            value_kind=value_kind)
        return data.get('fileValue') if data else None

    def get_simple_experiment(self, client=None) -> Union[Generic, DoseResponse]:
        """
        get a simple experiment from the server
        """
        file = self.get_source_file(client=client)
        if file is None:
            raise Exception("Could not find source file for experiment {}".format(self.code))
        file_type = get_file_type(file["name"])
        try:
            simple_experiment = load_from_str(file["content"], file_type=file_type)
        except Exception as e:
            raise Exception("Could not load source file for experiment {}: {}".format(self.code, e))
        simple_experiment.file_name = file["name"]
        simple_experiment.id = self.id
        return simple_experiment
    
    @property
    def original_experiment_code(self) -> str:
        data = get_entity_value_by_state_type_kind_value_type_kind(
            entity=self, 
            state_type="metadata", 
            state_kind="custom experiment metadata", 
            value_type="stringValue", 
            value_kind=ORIGINAL_EXPT_CODE_KEY)
        return data.get('stringValue') if data else None
    
    @property
    def original_project(self) -> str:
        data = get_entity_value_by_state_type_kind_value_type_kind(
            entity=self,
            state_type="metadata",
            state_kind="custom experiment metadata",
            value_type="stringValue",
            value_kind=ORIGINAL_PROJECT_KEY)
        return data.get('stringValue') if data else None
    
    @property
    def original_server(self) -> str:
        data = get_entity_value_by_state_type_kind_value_type_kind(
            entity=self,
            state_type="metadata",
            state_kind="custom experiment metadata",
            value_type="stringValue",
            value_kind=ORIGINAL_SERVER_KEY)
        return data.get('stringValue') if data else None
    
    @property
    def scientist(self) -> str:
        data = get_entity_value_by_state_type_kind_value_type_kind(
            entity=self,
            state_type="metadata",
            state_kind="experiment metadata",
            value_type="codeValue",
            value_kind="scientist")
        return data.get('codeValue') if data else None

    as_dict = dict.__str__
