from __future__ import unicode_literals
from .validation import validation_result

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class DDict(object):
    """The DDict class is meant as a generic interface for any implementation of a Data Dictionary that
    can be referenced by an ACAS CodeValue.
    Any classes implementing this interface must implement the get_values() method.
    """

    def __init__(self, code_type, code_kind, code_origin):
        self.code_type = code_type
        self.code_kind = code_kind
        self.code_origin = code_origin
        self.valid_values = None

    def get_values(self):
        raise NotImplementedError()

    @validation_result
    def check_value(self, value):
        """Check if the value is within `self.valid_values` for the DDict."""
        if value not in self.valid_values:
            return False, f"Invalid 'code':'{value}' provided for the given 'code_type':'{self.code_type}' and 'code_kind':'{self.code_kind}'"


class ACASDDict(DDict):
    """DDict implementation for built-in ACAS DDicts """

    CODE_ORIGIN = 'ACAS DDict'

    def __init__(self, code_type, code_kind):
        super(ACASDDict, self).__init__(code_type, code_kind, self.CODE_ORIGIN)

    def get_values(self, client):
        """Get the valid values for the DDict."""
        valid_codetables = client.get_ddict_values_by_type_and_kind(
            self.code_type, self.code_kind)
        self.valid_values = [val_dict['code'] for val_dict in valid_codetables]
        if self.valid_values == []:
            raise ValueError(f"Invalid 'code_type':'{self.code_type}' or "
                    f"'code_kind':'{self.code_kind}' provided")

class ACASLsThingDDict(DDict):
    """DDict implementation for referencing ACAS LsThings"""

    CODE_ORIGIN = 'ACAS LsThing'

    def __init__(self, thing_type, thing_kind):
        super(ACASLsThingDDict, self).__init__(thing_type, thing_kind, self.CODE_ORIGIN)
    
    def get_values(self, client):
        """Get the valid values for the DDict."""
        valid_codetables = client.get_ls_things_by_type_and_kind(self.code_type, self.code_kind, format='codetable')
        self.valid_values = [val_dict['code'] for val_dict in valid_codetables]