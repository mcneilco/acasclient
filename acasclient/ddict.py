from __future__ import unicode_literals
from typing import Any, Dict

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class DDict(object):

    def __init__(self, code_type, code_kind, code_origin):
        self.code_type = code_type
        self.code_kind = code_kind
        self.code_origin = code_origin
        self.values = None

    def get_values(self):
        raise NotImplementedError()

    def check_value(self, value):
        if value in self.valid_values:
            return True
        else:
            return False


class ACASDDict(DDict):

    CODE_ORIGIN = 'ACAS DDict'

    def __init__(self, code_type, code_kind):
        super(ACASDDict, self).__init__(code_type, code_kind, self.CODE_ORIGIN)

    def get_values(self, client):
        valid_codetables = client.get_ddict_values_by_type_and_kind(
            self.code_type, self.code_kind)
        self.valid_values = [val_dict['code'] for val_dict in valid_codetables]

class ACASLsThingDDict(DDict):

    CODE_ORIGIN = 'ACAS LsThing'

    def __init__(self, thing_type, thing_kind):
        super(ACASLsThingDDict, self).__init__(thing_type, thing_kind, self.CODE_ORIGIN)
    
    def get_values(self, client):
        valid_codetables = client.get_ls_things_by_type_and_kind(self.code_type, self.code_kind, format='codetable')
        self.valid_values = [val_dict['code'] for val_dict in valid_codetables]
    