import logging
from typing import Optional, Union

from .acasclient import (get_entity_label_by_label_type_kind,
                         get_entity_value_by_state_type_kind_value_type_kind)
from .selfile import get_file_type, load_from_str
from .acasclient import client
from .selfile import DoseResponse, Generic
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
DELETED_STATUS = "deleted"
################################################################################
# Classes
################################################################################


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
        data = get_entity_value_by_state_type_kind_value_type_kind(
            entity=self, 
            state_type="metadata", 
            state_kind="experiment metadata", 
            value_type="fileValue", 
            value_kind=SOURCE_FILE_KEY)
        return data.get('fileValue') if data else None

    def get_source_file(self, client: client = None) -> dict:
        file = None
        source_file = self.source_file
        if source_file is not None:
            file = client.get_file("/dataFiles/{}"
                        .format(source_file))
        return file

    def get_simple_experiment(self, client=None) -> Union[Generic, DoseResponse]:
        """
        get a simple experiment from the server
        """
        file = self.get_source_file(client=client)
        file_type = get_file_type(file["name"])
        simple_experiment = load_from_str(file["content"], file_type=file_type)
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
