from acasclient.ddict import ACASDDict
from enum import Enum
import types
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class AdditionalScientistType(Enum):
    """Enum for additional scientist types."""
    COMPOUND = ACASDDict('compound', 'scientist')
    ASSAY = ACASDDict('assay', 'scientist')

class AdditionalScientist():
    """Additional Scientist class."""
    def __init__(self, type: AdditionalScientistType, id=None, code=None, name=None, ignored=None):
        self.id = id
        self.ignored = ignored
        self.code = code
        self.name = name
        self.type = type
        
    def save(self, client):
        if self.type == AdditionalScientistType.COMPOUND:
            resp =client.create_cmpdreg_scientist(self.code, self.name)
        elif self.type == AdditionalScientistType.ASSAY:
            resp = client.create_assay_scientist(self.code, self.name)
        self.id = resp['id']
        return self

    def as_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'ignored': self.ignored,
            'type': self.type.name
        }

class AdditionalCompoundScientist(AdditionalScientist):
    """Additional Compound Scientist class."""

    def __init__(self, id=None, code=None, name=None, ignored=None):
        super().__init__(AdditionalScientistType.COMPOUND, id, code, name, ignored)

class AdditionalAssayScientist(AdditionalScientist):
    """Additional Assay Scientist class."""

    def __init__(self, id=None, code=None, name=None, ignored=None):
        super().__init__(AdditionalScientistType.ASSAY, id, code, name, ignored)


