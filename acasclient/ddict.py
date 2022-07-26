from __future__ import unicode_literals
from .validation import validation_result

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class DDict(object):
    """The DDict class is meant as a generic interface for any implementation of a Data Dictionary that
    can be referenced by an ACAS CodeValue.
    Any classes implementing this interface must implement the update_valid_values() method.
    The `update_valid_values` method must also be called before calling `check_value`
    """

    EMPTY_DICTIONARY_MESSAGE = "The Data Dictionary you've tried to reference is currently empty. No valid values found for Code Type: {code_type}, Code Kind: {code_kind}, Code Origin: {code_origin}"
    MISSING_VALUE_MESSAGE = "'{code}' is not yet in the database as a valid '{code_kind}'. Please double-check the spelling and correct your data if you expect this to match an existing term. If this is a novel valid term, please contact your administrator to add it to the following dictionary: Code Type: {code_type}, Code Kind: {code_kind}, Code Origin: {code_origin}"

    def __init__(self, code_type, code_kind, code_origin):
        self.code_type = code_type
        self.code_kind = code_kind
        self.code_origin = code_origin
        self.valid_values = None

    def update_valid_values(self, client):
        raise NotImplementedError()
    
    def raise_empty_dict_error(self):
        msg = self.EMPTY_DICTIONARY_MESSAGE.format(code_type=self.code_type, code_kind=self.code_kind, code_origin=self.code_origin)
        raise ValueError(msg)

    @validation_result
    def check_value(self, value):
        """Check if the value is within `self.valid_values` for the DDict."""
        if not self.valid_values:
            self.raise_empty_dict_error()
        if value not in self.valid_values:
            msg = self.MISSING_VALUE_MESSAGE.format(code=value, code_kind=self.code_kind, code_origin=self.code_origin, code_type=self.code_type)
            return False, msg


class ACASDDict(DDict):
    """DDict implementation for built-in ACAS DDicts """

    CODE_ORIGIN = 'ACAS DDict'

    def __init__(self, code_type, code_kind):
        super(ACASDDict, self).__init__(code_type, code_kind, self.CODE_ORIGIN)

    def update_valid_values(self, client):
        """Get the valid values for the DDict."""
        valid_codetables = client.get_ddict_values_by_type_and_kind(
            self.code_type, self.code_kind)
        self.valid_values = [val_dict['code'] for val_dict in valid_codetables]
        if not self.valid_values:
            self.raise_empty_dict_error()


class ACASLsThingDDict(DDict):
    """DDict implementation for referencing ACAS LsThings"""

    CODE_ORIGIN = 'ACAS LsThing'

    def __init__(self, thing_type, thing_kind):
        super(ACASLsThingDDict, self).__init__(thing_type, thing_kind, self.CODE_ORIGIN)

    def update_valid_values(self, client):
        """Get the valid values for the DDict."""
        valid_codetables = client.get_ls_things_by_type_and_kind(self.code_type, self.code_kind, format='codetable')
        self.valid_values = [val_dict['code'] for val_dict in valid_codetables]
        if not self.valid_values:
            self.raise_empty_dict_error()
